# -*- coding: utf-8 -*-
"""资料分类：用 LLM 识别资料属于哪门课、有哪些知识点。

【这个模块做什么】

    输入：一份资料的文本内容
    输出：{course_name, knowledge_points, confidence, reasoning}

    并把结果写入 materials 表的 detected_* 字段，
    状态置为 suggested，等人工确认。

【三条硬约束（来自框架）】

    1. **只给前 3 个 chunk，不给全文** —— 省 token。
       文件名 + 文档标题 + 前 1500 字足够判断归属了。
       给全文的话，一份 200 页的 PDF 会消耗大量 token，成本高且没必要。

    2. **识别结果只作建议，不直接落 course_id** —— 必须经人工确认。
       LLM 判断错的概率不低（尤其是资料标题混乱时），
       直接落库会导致课程被错误创建。

    3. **识别失败不阻断上传** —— LLM 不可用时资料仍正常入库，
       只是 detection_status 保持 pending，等人工处理。

【与 course / knowledge_point 服务的关系】

    本模块**不直接建课程、不直接建知识点**。
    它只负责"识别 + 写 detected_* 字段"。
    真正建课程/知识点是人工确认之后的事（在 API 层做）。
"""

from __future__ import annotations

from typing import Any

from app.prompts import load_rendered, prompt_version
from app.database import courses as course, connection as db_mysql, knowledge_points as knowledge_point, materials as material_store
from app.ai.llm_client import LLMClient, LLMError, LLMResponseError


# ==============================================================
# 常量
# ==============================================================
CLASSIFY_PROMPT = "m0_all_classify_material_v0.1"

# 送给 LLM 的样本文本长度上限。
# 为什么是 1500：约等于 3 个 chunk（每个 chunk 500 字），
# 足够判断课程归属，又不会太费 token。
SAMPLE_TEXT_LIMIT = 1500


# ==============================================================
# 主函数
# ==============================================================
def classify_material(
    material_id: int,
    sample_text: str,
    doc_title: str = "",
    llm: LLMClient | None = None,
) -> dict[str, Any]:
    """识别一份资料属于哪门课、有哪些知识点。

    Args:
        material_id: 资料 id（要在 materials 表里存在）。
        sample_text: 样本文本（建议传前 1500 字）。
        doc_title: 文档标题（从正文前几行提取，可选）。
        llm: 可注入的 LLM 客户端（测试用）。

    Returns:
        {
          "material_id": 资料 id,
          "course_name": 建议的课程名（可能为空字符串）,
          "course_confidence": 置信度 0.0~1.0,
          "knowledge_points": [{"name": "...", "confidence": 0.9}, ...],
          "reasoning": LLM 的判断理由,
          "success": True/False,
          "error": 失败原因（success=False 时才有）,
        }

    【重要】即使失败也不抛异常。
        失败时 success=False + error 说明原因，
        由调用方决定是否重试或转人工。
        这样上传流程不会因为 LLM 挂了而中断。
    """
    # 检查资料是否存在
    material = material_store.get_by_id(material_id)
    if material is None:
        return _failure(material_id, f"资料 id={material_id} 不存在")

    # 检查样本文本
    if not sample_text or not sample_text.strip():
        return _failure(material_id, "样本文本为空，无法识别")

    # 截断样本文本（防止传了全文进来）
    sample = sample_text.strip()[:SAMPLE_TEXT_LIMIT]

    # 查系统里已有的课程名（让 LLM 优先匹配已有课程，避免造新词）
    known_courses = _known_course_names()

    # 渲染提示词
    try:
        prompt = load_rendered(
            CLASSIFY_PROMPT,
            file_name=material["source_file"],
            doc_title=doc_title or "（无标题）",
            sample_text=sample,
            known_courses=known_courses or "（系统里还没有任何课程）",
        )
    except Exception as exc:  # noqa: BLE001 - 提示词文件缺失等情况
        return _failure(material_id, f"提示词渲染失败：{exc}")

    # 调 LLM
    client = llm if llm is not None else LLMClient()
    pv = prompt_version(CLASSIFY_PROMPT)

    try:
        payload, response = client.chat_json([
            {"role": "system", "content": "你是教学资料归档员，只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ])
    except (LLMError, LLMResponseError) as exc:
        # 记录失败的调用（成本审计要求失败也记）
        _log_llm_call(
            course_id=None,
            success=False,
            error=str(exc),
            prompt_version=pv,
        )
        return _failure(material_id, f"LLM 调用失败：{exc}")

    # 记录成功的调用
    _log_llm_call(
        course_id=None,
        success=True,
        prompt_version=pv,
        usage=response.usage,
    )

    # 解析结果
    parsed = _parse_classification_result(payload)

    # 写入数据库
    try:
        material_store.save_detection(
            material_id=material_id,
            course_name=parsed["course_name"],
            confidence=parsed["confidence"],
            knowledge_points=parsed["knowledge_points"],
            reasoning=parsed["reasoning"],
        )
    except Exception as exc:  # noqa: BLE001 - 写库失败不该让调用方崩
        return _failure(material_id, f"识别结果写库失败：{exc}")

    return {
        "material_id": material_id,
        "course_name": parsed["course_name"],
        "course_confidence": parsed["confidence"],
        "knowledge_points": parsed["knowledge_points"],
        "reasoning": parsed["reasoning"],
        "success": True,
        "error": None,
    }


def apply_suggestion(
    material_id: int,
    confirmed_by: str = "",
    create_missing_course: bool = True,
) -> dict[str, Any]:
    """把 LLM 的建议真正落地：建课程（如果不存在）、建知识点、关联资料。

    【什么时候调】
        管理员在确认页点了"接受建议"之后。

    【和 confirm_classification 的区别】
        material_store.confirm_classification 只做"关联资料到课程"这一步。
        本函数做得更多：如果课程不存在就建，知识点不存在也建。

    Args:
        material_id: 资料 id。
        confirmed_by: 确认人。
        create_missing_course: 课程不存在时是否自动创建。

    Returns:
        {
          "success": True/False,
          "course_id": 课程 id,
          "knowledge_point_ids": [...],
          "created_course": True/False（这次新建了课程）,
          "created_knowledge_points": 新建了几个知识点,
          "error": 错误原因（失败时）,
        }
    """
    material = material_store.get_by_id(material_id)
    if material is None:
        return _apply_failure(f"资料 id={material_id} 不存在")

    course_name = material.get("detected_course_name") or ""
    if not course_name.strip():
        return _apply_failure("资料没有被识别出课程名，无法应用建议")

    # ---------- 1. 处理课程 ----------
    course_id, created_course = None, False

    existing = course.get_by_name(course_name)
    if existing is not None:
        course_id = int(existing["id"])
    else:
        if not create_missing_course:
            return _apply_failure(
                f"课程「{course_name}」不存在，且未允许自动创建"
            )
        course_id = course.create(name=course_name)
        created_course = True

    # ---------- 2. 处理知识点 ----------
    kp_list = material.get("detected_knowledge_points") or []
    kp_names = [item["name"] for item in kp_list if item.get("name")]
    kp_ids = knowledge_point.bulk_create(course_id, kp_names, source_material_id=material_id)

    # ---------- 3. 关联资料到课程 ----------
    material_store.confirm_classification(
        material_id=material_id,
        course_id=course_id,
        confirmed_by=confirmed_by,
    )

    return {
        "success": True,
        "course_id": course_id,
        "knowledge_point_ids": kp_ids,
        "created_course": created_course,
        "created_knowledge_points": len(kp_ids),
        "error": None,
    }


# ==============================================================
# 内部工具
# ==============================================================
def _known_course_names() -> str:
    """取系统里现有的课程名，拼成给 LLM 看的字符串。

    【为什么要给 LLM 看现有课程名】
        让 LLM 优先匹配已有课程，而不是每次都造新词。
        比如系统里已经有"商法"，LLM 看到后就不会说"商法课程"。
    """
    rows = course.list_all()
    if not rows:
        return ""
    return "、".join(str(r["name"]) for r in rows)


def _parse_classification_result(payload: object) -> dict[str, Any]:
    """把 LLM 返回的 JSON 解析成规范结构。

    【为什么要"规范"】
        模型可能：
          - course_confidence 写成字符串 "0.9"
          - knowledge_points 里混入非 dict 的项
          - 置信度超出 0~1 范围
        这里统一处理，让上层拿到的是干净数据。

    【不抛异常】
        格式不对时返回空结果，由调用方处理。
        因为"LLM 输出不完美"是常态，不该当异常处理。
    """
    if not isinstance(payload, dict):
        return {
            "course_name": "",
            "confidence": 0.0,
            "knowledge_points": [],
            "reasoning": "",
        }

    # 课程名：可能是 str 或空
    course_name = str(payload.get("course_name") or "").strip()

    # 置信度：转成 float，限制在 0~1
    try:
        confidence = float(payload.get("course_confidence") or 0.0)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    # 知识点：过滤掉格式不对的项
    raw_kps = payload.get("knowledge_points") or []
    knowledge_points: list[dict[str, Any]] = []
    if isinstance(raw_kps, list):
        for item in raw_kps:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            try:
                kp_conf = float(item.get("confidence") or 0.0)
                kp_conf = max(0.0, min(1.0, kp_conf))
            except (TypeError, ValueError):
                kp_conf = 0.0
            knowledge_points.append({"name": name, "confidence": kp_conf})

    return {
        "course_name": course_name,
        "confidence": confidence,
        "knowledge_points": knowledge_points,
        "reasoning": str(payload.get("reasoning") or "").strip(),
    }


def _failure(material_id: int, error: str) -> dict[str, Any]:
    """构造失败结果。

    【为什么要单独一个函数】
        失败结果的字段结构要和成功结果一致，
        否则调用方每次都得判断字段在不在。
    """
    return {
        "material_id": material_id,
        "course_name": "",
        "course_confidence": 0.0,
        "knowledge_points": [],
        "reasoning": "",
        "success": False,
        "error": error,
    }


def _apply_failure(error: str) -> dict[str, Any]:
    """构造 apply_suggestion 的失败结果。"""
    return {
        "success": False,
        "course_id": None,
        "knowledge_point_ids": [],
        "created_course": False,
        "created_knowledge_points": 0,
        "error": error,
    }


def _log_llm_call(
    course_id: int | None,
    success: bool,
    prompt_version: str,
    usage: Any = None,
    error: str = "",
) -> None:
    """记录一次 LLM 调用到审计日志。

    【为什么要单独一个内部函数】
        识别场景的日志字段和出题场景不同（没有 knowledge_point、question_type），
        但共用一个表。封成函数避免每次写一长串参数。
    """
    try:
        db_mysql.execute(
            "INSERT INTO llm_call_log "
            "(purpose, course_id, prompt_version, model_version, "
            "prompt_tokens, completion_tokens, latency_ms, success, error) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                "classify_material",
                course_id,
                prompt_version,
                getattr(usage, "model", "") if usage else "",
                getattr(usage, "prompt_tokens", 0) if usage else 0,
                getattr(usage, "completion_tokens", 0) if usage else 0,
                getattr(usage, "latency_ms", 0) if usage else 0,
                int(success),
                error[:500] if error else None,
            ),
        )
    except Exception:  # noqa: BLE001 - 记日志失败不该影响主流程
        pass