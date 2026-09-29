# -*- coding: utf-8 -*-
"""题目生成引擎：题库优先 + LLM 生成 + 搜索兜底。

【这个模块做什么】

    输入：课程 id + 知识点 + 题型 + 难度 + 数量
    输出：{questions, source_summary, warnings}

    流程（三步）：
      1. 查题库（命中充足就不调 LLM）
      2. 未命中：检索资料上下文
      3. 调 LLM 生成（资料不足时带搜索工具）

【为什么要"题库优先"】

    这是整个项目的核心设计：
      - 成本可控：日常出题不调 LLM
      - 结果可复现：同样的请求返回同一批题
      - 速度快：读数据库 vs 等模型 5 秒
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.config import DEDUP_MAX_RETRY, DIFFICULTIES, QUESTION_TYPES, TOP_K
from app.prompts import load_rendered, prompt_version
from app.database import connection as db_mysql, questions as question_bank_mysql
from app.pipeline import indexer
from app.ai import llm_client, search_tool


# ==============================================================
# 常量
# ==============================================================
SIMILARITY_THRESHOLD = 0.6
DEDUP_THRESHOLD = 0.9

# 向量能力不可用时统一按"没有上下文"处理。
# 两个异常分别来自向量库缺失与向量模型缺失，它们在业务语义上是同一件事。
VECTOR_UNAVAILABLE = (
    indexer.VectorStoreUnavailableError,
)


# ==============================================================
# 异常
# ==============================================================
class InsufficientMaterialError(ValueError):
    """资料不足，拒绝出题。"""


# ==============================================================
# 结果结构
# ==============================================================
@dataclass
class GenResult:
    """一次出题请求的完整结果。"""

    questions: list[dict[str, Any]] = field(default_factory=list)
    from_bank: int = 0
    from_llm: int = 0
    from_search: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "questions": self.questions,
            "source_summary": {
                "from_bank": self.from_bank,
                "from_llm": self.from_llm,
                "from_search": self.from_search,
            },
            "warnings": self.warnings,
        }


# ==============================================================
# 提示词路由
# ==============================================================
_PROMPT_BY_COURSE_TYPE: dict[tuple[str, str], str] = {
    ("tort", "简答"): "m2_tort_short_answer_v0.1",
    ("xigai", "简答"): "m2_xigai_short_answer_v0.1",
    ("tort", "选择"): "m2_all_choice_v0.1",
    ("xigai", "选择"): "m2_all_choice_v0.1",
}


def resolve_prompt(course_name: str, question_type: str) -> str:
    """按课程名 + 题型选提示词。"""
    name_lower = (course_name or "").lower()

    if "商法" in course_name or "侵权" in course_name or "tort" in name_lower:
        course_key = "tort"
    elif "习概" in course_name or "习近平" in course_name or "xigai" in name_lower:
        course_key = "xigai"
    else:
        course_key = "tort"

    if question_type == "选择":
        return _PROMPT_BY_COURSE_TYPE[("tort", "选择")]

    key = (course_key, question_type)
    if key not in _PROMPT_BY_COURSE_TYPE:
        raise KeyError(f"课程 {course_name!r} 的题型 {question_type!r} 未配置提示词")
    return _PROMPT_BY_COURSE_TYPE[key]


# ==============================================================
# 主流程
# ==============================================================
def get_questions(
    course_id: int,
    knowledge_point: str,
    question_type: str,
    difficulty: str,
    count: int = 1,
    knowledge_point_id: int | None = None,
    llm: Any = None,
    force_generate: bool = False,
    bank_ratio: float = 0.7,
) -> dict[str, Any]:
    """出题主入口。

    Args:
        bank_ratio: 题库占比，默认 0.7（即 70% 题库 + 30% LLM）。
                    设为 1.0 则走旧逻辑（题库够就全题库）。
    """
    if question_type not in QUESTION_TYPES:
        raise ValueError(f"未知题型：{question_type!r}")
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"未知难度：{difficulty!r}")
    if count <= 0:
        raise ValueError(f"count 必须为正整数，收到 {count}")
    bank_ratio = max(0.0, min(1.0, bank_ratio))

    result = GenResult()

    # ---------- 第一步：查题库 ----------
    if not force_generate:
        candidates = question_bank_mysql.query_questions(
            course_id=course_id,
            knowledge_point=knowledge_point,
            question_type=question_type,
            difficulty=difficulty,
            order_by="随机",
            limit=max(count * 3, count),
        )
        # 题库应取数量：按比例，至少取全部候选
        bank_target = int(count * bank_ratio) if bank_ratio < 1.0 else count
        picked = question_bank_mysql.sample_questions(candidates, bank_target)

        for row in picked:
            question_bank_mysql.increment_usage(row["id"])
            result.questions.append(_row_to_question(row))
        result.from_bank = len(picked)

        # bank_ratio < 1.0：一定要留出 LLM 的份额
        if bank_ratio < 1.0:
            need = count - len(picked)
        else:
            # 旧逻辑：题库够就返回
            if len(picked) >= count:
                return result.to_dict()
            need = count - len(picked)
    else:
        need = count

    # ---------- 第二步：检索资料上下文 ----------
    # 调 indexer.search 取上下文，用于 LLM 出题时提供参考资料。
    #
    # 【为什么不限定 course】
    #   目前只有一门课，跨课程检索没问题。
    #   而且上传资料时没显式指定课程 key，
    #   向量库里的 chunk 都是 course="unknown"。
    #   限定 course 反而查不到任何东西。
    #   多课程场景下，改回传 course=str(course_id)，
    #   同时修上传流程（把 course_id 存进 chunk）。
    try:
        hits = indexer.search(
            query=f"{knowledge_point} {question_type}",
            top_k=TOP_K,
        )
    except VECTOR_UNAVAILABLE:
        hits = []

    context_text, default_source = _format_context(hits)

    # 相似度：有 hits 时取最高分
    best_similarity = max((h.get("similarity", 0.0) for h in hits), default=0.0)

    # 决定是否启用搜索工具
    use_search = best_similarity < SIMILARITY_THRESHOLD
    if use_search and not search_tool.is_configured():
        result.warnings.append(
            f"最高相似度仅 {best_similarity:.2f}（低于阈值 {SIMILARITY_THRESHOLD}），"
            f"本应触发搜索补充，但未配置 BOCHA_API_KEY，本次仅基于已有资料生成。"
        )
        use_search = False

    # ---------- 第三步：调 LLM 生成 ----------
    course_name = _get_course_name(course_id)
    prompt_name = resolve_prompt(course_name, question_type) if not use_search else "m2_all_search_and_generate_v0.1"

    client = llm if llm is not None else llm_client.LLMClient()

    # 构造提示词
    try:
        if use_search:
            prompt = load_rendered(
                prompt_name,
                course_name=course_name,
                knowledge_point=knowledge_point,
                question_type=question_type,
                difficulty=difficulty,
                count=str(need),
                retrieved_context=context_text or "（暂无资料）",
            )
        else:
            prompt = load_rendered(
                prompt_name,
                retrieved_context=context_text or "（暂无资料）",
                course_name=course_name,
                knowledge_point=knowledge_point,
                difficulty=difficulty,
                count=str(need),
            )
    except Exception as exc:
        result.warnings.append(f"提示词渲染失败：{exc}")
        return result.to_dict()

    pv = prompt_version(prompt_name)

    # 调 LLM
    try:
        if use_search:
            generated = _call_llm_with_search(
                client=client,
                prompt=prompt,
                course_name=course_name,
                knowledge_point=knowledge_point,
                course_id=course_id,
                question_type=question_type,
            )
        else:
            generated = _call_llm_plain(
                client=client,
                prompt=prompt,
                question_type=question_type,
                knowledge_point=knowledge_point,
                difficulty=difficulty,
            )
    except Exception as exc:
        result.warnings.append(f"LLM 调用失败：{type(exc).__name__}: {exc}")
        return result.to_dict()

    # 入库
    missing = need
    attempt = 0
    while missing > 0 and attempt <= DEDUP_MAX_RETRY:
        batch = generated[:missing] if len(generated) > missing else generated
        for item in batch:
            try:
                normalized = normalize_question(
                    raw=item,
                    question_type=question_type,
                    knowledge_point=knowledge_point,
                    difficulty=difficulty,
                    default_source_ref=default_source,
                )
            except ValueError as exc:
                result.warnings.append(f"题目格式不合格，已跳过：{exc}")
                continue

            qid = question_bank_mysql.insert_question(
                course_id=course_id,
                knowledge_point=knowledge_point,
                knowledge_point_id=knowledge_point_id,
                question_type=question_type,
                difficulty=normalized["difficulty"],
                payload=normalized,
                source="web_search" if use_search else "generated",
                source_ref=normalized["source_ref"],
                prompt_version=pv,
                model_version=getattr(client, "model", None),
            )
            normalized["id"] = qid
            normalized["from"] = "search" if use_search else "llm"
            normalized["course_id"] = course_id
            result.questions.append(normalized)

            if use_search:
                result.from_search += 1
            else:
                result.from_llm += 1

            missing -= 1

        attempt += 1
        if missing <= 0:
            break
        if attempt > DEDUP_MAX_RETRY:
            break

    if missing > 0:
        result.warnings.append(f"仍有 {missing} 道题未生成成功")

    return result.to_dict()


# ==============================================================
# LLM 调用
# ==============================================================
def _call_llm_plain(
    client: Any,
    prompt: str,
    question_type: str,
    knowledge_point: str,
    difficulty: str,
) -> list[dict[str, Any]]:
    """普通调用（无工具）。"""
    response = client.chat([
        {"role": "system", "content": "你是严谨的学科命题专家，只输出合法 JSON。"},
        {"role": "user", "content": prompt},
    ])

    payload = llm_client.extract_json(response.content)

    if isinstance(payload, dict) and payload.get("insufficient"):
        return []

    raw_items = payload.get("questions") if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        raise llm_client.LLMResponseError("模型返回里找不到 questions 数组")

    return raw_items


def _call_llm_with_search(
    client: Any,
    prompt: str,
    course_name: str,
    knowledge_point: str,
    course_id: int,
    question_type: str,
) -> list[dict[str, Any]]:
    """带搜索工具的调用。"""
    tools = [
        llm_client.build_tool_definition(
            name="search_web",
            description=(
                "搜索网络资料。当你发现已有资料不足以回答时调用。"
                "适合搜索课程知识点的常考题目、真题、参考答案。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，例如：商法 归责原则 简答题 真题",
                    },
                },
                "required": ["query"],
            },
        )
    ]

    def execute_tool(name: str, arguments: dict[str, Any]) -> str:
        if name != "search_web":
            return f"未知工具：{name}"

        query = arguments.get("query", "").strip()
        if not query:
            return "错误：query 参数为空"

        results = search_tool.search(
            query=query,
            top_k=5,
            purpose="supplement_material",
            course_id=course_id,
            knowledge_point=knowledge_point,
        )

        if not results:
            return "搜索没有返回结果。"

        parts: list[str] = []
        for i, r in enumerate(results, start=1):
            parts.append(
                f"[结果{i}]\n标题：{r['title']}\n链接：{r['url']}\n摘要：{r['snippet']}"
            )
        return "\n\n".join(parts)

    response = client.chat_with_tools(
        messages=[
            {"role": "system", "content": "你是严谨的学科命题专家，只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ],
        tools=tools,
        tool_executor=execute_tool,
        max_iterations=3,
    )

    payload = llm_client.extract_json(response.content)

    if isinstance(payload, dict) and payload.get("insufficient"):
        return []

    raw_items = payload.get("questions") if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        raise llm_client.LLMResponseError("模型返回里找不到 questions 数组")

    return raw_items


# ==============================================================
# 题目规范化
# ==============================================================
def normalize_question(
    raw: dict[str, Any],
    question_type: str,
    knowledge_point: str,
    difficulty: str,
    default_source_ref: str,
) -> dict[str, Any]:
    """把模型返回的题目校验并规范成统一的内部结构。"""
    if not isinstance(raw, dict):
        raise ValueError(f"题目不是 JSON 对象：{type(raw).__name__}")

    stem = str(raw.get("question") or raw.get("题干") or "").strip()
    if not stem:
        raise ValueError("题目缺少 question 字段")

    raw_difficulty = str(raw.get("difficulty") or "").strip()
    if difficulty in DIFFICULTIES:
        final_difficulty = difficulty
    elif raw_difficulty in DIFFICULTIES:
        final_difficulty = raw_difficulty
    else:
        final_difficulty = difficulty

    tags = _clean_str_list(
        raw.get("knowledge_tags") or raw.get("tags"),
        [knowledge_point],
    )

    source_ref = str(raw.get("source") or "").strip() or default_source_ref

    base: dict[str, Any] = {
        "question": stem,
        "question_type": question_type,
        "knowledge_tags": tags,
        "difficulty": final_difficulty,
        "source_ref": source_ref,
    }

    if question_type == "选择":
        options = raw.get("options")
        if not isinstance(options, list) or len(options) < 2:
            raise ValueError("选择题缺少合法的 options")
        options = [str(o).strip() for o in options]

        try:
            correct_index = int(raw.get("correct_index"))
        except (TypeError, ValueError) as exc:
            raise ValueError("选择题缺少合法的 correct_index") from exc

        if not 0 <= correct_index < len(options):
            raise ValueError(f"correct_index={correct_index} 越界")

        base.update({
            "options": options,
            "correct_index": correct_index,
            "explanation": str(raw.get("explanation") or "").strip(),
            "reference_answer": options[correct_index],
            "scoring_points": [],
        })
    else:
        base.update({
            "options": None,
            "correct_index": None,
            "explanation": str(raw.get("explanation") or "").strip(),
            "reference_answer": str(
                raw.get("reference_answer") or raw.get("答案") or ""
            ).strip(),
            "scoring_points": _clean_str_list(
                raw.get("scoring_points") or raw.get("评分要点"), []
            ),
        })
        if not base["reference_answer"]:
            raise ValueError("简答题缺少 reference_answer")
        if not base["scoring_points"]:
            raise ValueError("简答题缺少 scoring_points")

    return base


# ==============================================================
# 内部工具
# ==============================================================
def _clean_str_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace("；", ";").replace("、", ";").split(";")]
    elif isinstance(value, list):
        parts = [str(p).strip() for p in value]
    else:
        return list(fallback)

    cleaned = [p for p in parts if p]
    return cleaned or list(fallback)


def _format_context(hits: list[dict[str, Any]]) -> tuple[str, str]:
    """把检索结果拼成提示词用的上下文文本。"""
    if not hits:
        return "", ""

    blocks: list[str] = []
    for i, hit in enumerate(hits, start=1):
        chunk_id = str(hit.get("id", ""))
        text = hit.get("text", "").strip()
        blocks.append(f"[片段{i}]（chunk_id={chunk_id}）\n{text}")

    default_source = str(hits[0].get("id", "")) if hits else ""
    return "\n\n".join(blocks), default_source


def _get_course_name(course_id: int) -> str:
    """取课程名。"""
    row = db_mysql.fetch_one(
        "SELECT name FROM courses WHERE id = %s",
        (course_id,),
    )
    return str(row["name"]) if row else "未知课程"


def _row_to_question(row: dict[str, Any]) -> dict[str, Any]:
    """把题库行转成与 LLM 生成题一致的对外结构。"""
    payload = dict(row.get("payload") or {})
    payload.update({
        "id": row["id"],
        "course_id": row.get("course_id"),
        "question_type": row.get("question_type"),
        "difficulty": row.get("difficulty"),
        "source_ref": row.get("source_ref"),
        "from": "bank",
        "quality_score": row.get("quality_score"),
        "usage_count": row.get("usage_count"),
    })
    return payload