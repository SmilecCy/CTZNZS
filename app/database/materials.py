# -*- coding: utf-8 -*-
"""资料记录服务：materials 表的 CRUD。

【为什么要单独一个 service】

    资料表既要记录"文件本身的信息"（文件名、类型、页数、chunk 数），
    也要记录"LLM 识别出的归属信息"（建议课程名、建议知识点、置信度、状态）。

    这两类信息生命周期不同：
      - 文件信息：上传后基本不变
      - 识别信息：可能被人工修正

    集中在一个 service 里，是为了：
      1. 识别状态的流转（pending → suggested → confirmed / rejected）只在这里
      2. 人工确认时该更新哪些字段，一目了然
"""

from __future__ import annotations

import json
from typing import Any

from app.database import connection as db_mysql


# ==============================================================
# 状态常量
# ==============================================================
# 用常量而不是散落的字符串，避免拼错。
# 比如写 "sugested"（漏了一个 g）不会报错，只会静默失效。
STATUS_PENDING = "pending"        # 刚上传，还没识别
STATUS_SUGGESTED = "suggested"    # LLM 已给出建议，等人工确认
STATUS_CONFIRMED = "confirmed"    # 人工已确认归属
STATUS_REJECTED = "rejected"      # 人工拒绝了识别结果（保留记录，供排查）


# ==============================================================
# 建
# ==============================================================
def create(
    source_file: str,
    kind: str,
    upload_type: str = "supplement",
    chunk_count: int = 0,
    page_count: int = 0,
    ocr_used: bool = False,
    course_id: int | None = None,
    markdown_path: str | None = None,
) -> int:
    """登记一份新资料。

    Args:
        source_file: 原始文件名（含扩展名）。唯一。
        kind: 文件类型（pdf / docx / image / text）。
        upload_type: 上传类型（textbook / supplement）。
        chunk_count: 切分出的 chunk 数。
        page_count: 页数。
        ocr_used: 是否走了 OCR。
        course_id: 所属课程 id。传了会触发 textbook_course_id 生成列校验。
        markdown_path: 教材 MD 落盘路径。仅 textbook 类型有值。

    Returns:
        新资料的 id。

    Raises:
        ValueError: 同名资料已存在；或教材唯一性冲突。
    """
    existing = get_by_file(source_file)
    if existing is not None:
        raise ValueError(f"资料「{source_file}」已存在（id={existing['id']}）")

    if upload_type == "textbook" and course_id is not None:
        dup = get_textbook_by_course(course_id)
        if dup is not None:
            raise ValueError(
                f"课程 id={course_id} 已有教材「{dup['source_file']}」"
                f"（id={dup['id']}）。每门课程只能有一份教材，请先删除现有教材再上传。"
            )

    return db_mysql.insert_returning_id(
        "INSERT INTO materials "
        "(source_file, kind, upload_type, chunk_count, page_count, ocr_used, "
        "course_id, markdown_path, detection_status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (source_file, kind, upload_type, chunk_count, page_count, int(ocr_used),
         course_id, markdown_path, STATUS_PENDING),
    )


def upsert(
    source_file: str,
    kind: str,
    upload_type: str = "supplement",
    chunk_count: int = 0,
    page_count: int = 0,
    ocr_used: bool = False,
    course_id: int | None = None,
    markdown_path: str | None = None,
) -> int:
    """登记资料；已存在就更新。

    【用途】重新解析同一份文件时用。
        不重复建记录，只更新 chunk_count 等。

    Returns:
        资料 id。
    """
    existing = get_by_file(source_file)
    if existing is None:
        return create(source_file, kind, upload_type, chunk_count, page_count,
                      ocr_used, course_id=course_id, markdown_path=markdown_path)

    db_mysql.execute(
        "UPDATE materials SET kind = %s, chunk_count = %s, page_count = %s, "
        "ocr_used = %s, course_id = COALESCE(%s, course_id), "
        "markdown_path = COALESCE(%s, markdown_path), "
        "parsed_at = CURRENT_TIMESTAMP WHERE id = %s",
        (kind, chunk_count, page_count, int(ocr_used),
         course_id, markdown_path, existing["id"]),
    )
    return int(existing["id"])


# ==============================================================
# 查
# ==============================================================
def get_by_id(material_id: int) -> dict[str, Any] | None:
    """按 id 查资料。"""
    row = db_mysql.fetch_one(
        "SELECT * FROM materials WHERE id = %s",
        (material_id,),
    )
    return _decorate(row) if row else None


def get_by_file(source_file: str) -> dict[str, Any] | None:
    """按文件名查资料。"""
    row = db_mysql.fetch_one(
        "SELECT * FROM materials WHERE source_file = %s",
        (source_file,),
    )
    return _decorate(row) if row else None


def list_all(
    course_id: int | None = None,
    detection_status: str | None = None,
    upload_type: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """列出资料。

    Args:
        course_id: 限定课程；None 表示不限。
        detection_status: 限定识别状态；None 表示不限。
        upload_type: 限定上传类型（textbook / supplement）；None 表示不限。
        limit: 条数上限。

    Returns:
        资料列表。
    """
    sql = "SELECT * FROM materials WHERE 1=1"
    params: list[Any] = []

    if course_id is not None:
        sql += " AND course_id = %s"
        params.append(course_id)

    if detection_status is not None:
        sql += " AND detection_status = %s"
        params.append(detection_status)

    if upload_type is not None:
        sql += " AND upload_type = %s"
        params.append(upload_type)

    sql += " ORDER BY uploaded_at DESC"

    if limit:
        sql += " LIMIT %s"
        params.append(int(limit))

    rows = db_mysql.fetch_all(sql, tuple(params))
    return [_decorate(r) for r in rows]


def list_pending_classification() -> list[dict[str, Any]]:
    """列出待人工确认分类的资料。

    【用途】后台管理页要展示"哪些资料还没确认归属"，
        让管理员能尽快处理。

    Returns:
        状态为 pending 或 suggested 的资料列表。
    """
    rows = db_mysql.fetch_all(
        "SELECT * FROM materials "
        "WHERE detection_status IN (%s, %s) "
        "ORDER BY uploaded_at DESC",
        (STATUS_PENDING, STATUS_SUGGESTED),
    )
    return [_decorate(r) for r in rows]


def get_textbook_by_course(course_id: int) -> dict[str, Any] | None:
    """查某课程的教材。

    【用途】上传教材前检查是否已有教材（教材唯一性校验）。

    Args:
        course_id: 课程 id。

    Returns:
        教材资料字典；不存在返回 None。
    """
    row = db_mysql.fetch_one(
        "SELECT * FROM materials WHERE course_id = %s AND upload_type = 'textbook'",
        (course_id,),
    )
    return _decorate(row) if row else None


def check_textbook_exists(course_id: int) -> bool:
    """检查某课程是否已有教材。

    Args:
        course_id: 课程 id。

    Returns:
        True 表示已有教材。
    """
    return get_textbook_by_course(course_id) is not None


def update_markdown_path(material_id: int, markdown_path: str) -> bool:
    """更新资料的 markdown_path。

    【用途】教材解析完成后，把 MD 落盘路径写回数据库。

    Args:
        material_id: 资料 id。
        markdown_path: MD 文件的绝对路径或相对路径。

    Returns:
        是否成功。
    """
    affected = db_mysql.execute(
        "UPDATE materials SET markdown_path = %s WHERE id = %s",
        (markdown_path, material_id),
    )
    return affected > 0


# ==============================================================
# 改：识别结果
# ==============================================================
def save_detection(
    material_id: int,
    course_name: str,
    confidence: float,
    knowledge_points: list[dict[str, Any]],
    reasoning: str = "",
) -> bool:
    """保存 LLM 识别的结果。

    【注意】这个方法**只写 detected_* 字段**，不设置 course_id。
        course_id 要等人工确认后才写（见 confirm_classification）。
        这是"识别只作建议"这条铁律的落点。

    Args:
        material_id: 资料 id。
        course_name: LLM 建议的课程名。
        confidence: 置信度 0.00~1.00。
        knowledge_points: 建议的知识点列表，每项形如 {"name": "...", "confidence": 0.9}。
        reasoning: LLM 的判断理由。

    Returns:
        是否保存成功。

    Raises:
        ValueError: 资料不存在。
    """
    if get_by_id(material_id) is None:
        raise ValueError(f"资料 id={material_id} 不存在")

    # 知识点列表转成 JSON 字符串存 TEXT 字段
    kp_json = json.dumps(knowledge_points, ensure_ascii=False)

    db_mysql.execute(
        "UPDATE materials SET "
        "detected_course_name = %s, "
        "detected_knowledge_points = %s, "
        "detection_confidence = %s, "
        "detection_reasoning = %s, "
        "detection_status = %s, "
        "detection_at = CURRENT_TIMESTAMP "
        "WHERE id = %s",
        (course_name, kp_json, confidence, reasoning, STATUS_SUGGESTED, material_id),
    )
    return True


def confirm_classification(
    material_id: int,
    course_id: int,
    confirmed_by: str = "",
) -> bool:
    """人工确认资料归属。

    【这个方法做了什么】
        1. 把 materials.course_id 设成指定的课程
        2. detection_status 改成 confirmed
        3. 在 material_course_map 表里记录关联

    【为什么还要写 material_course_map】
        materials.course_id 是"资料当前归属的课程"，
        material_course_map 是"历史归属记录"（谁在什么时候确认的）。
        两者职责不同：
          - materials.course_id 用于查询（快）
          - material_course_map 用于审计（追溯）

    Args:
        material_id: 资料 id。
        course_id: 确认归属的课程 id。
        confirmed_by: 确认人（管理员用户名）。

    Returns:
        是否成功。

    Raises:
        ValueError: 资料不存在。
    """
    material = get_by_id(material_id)
    if material is None:
        raise ValueError(f"资料 id={material_id} 不存在")

    # 更新 materials 表
    db_mysql.execute(
        "UPDATE materials SET course_id = %s, detection_status = %s WHERE id = %s",
        (course_id, STATUS_CONFIRMED, material_id),
    )

    # 写 material_course_map。
    # 【用 ON DUPLICATE KEY UPDATE】material_id 有唯一约束。
    # 如果这份资料之前确认过，这次是改归属，应该更新而不是插入。
    db_mysql.execute(
        "INSERT INTO material_course_map (material_id, course_id, confirmed_by) "
        "VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE "
        "course_id = VALUES(course_id), "
        "confirmed_by = VALUES(confirmed_by), "
        "confirmed_at = CURRENT_TIMESTAMP",
        (material_id, course_id, confirmed_by),
    )

    return True


def reject_classification(material_id: int) -> bool:
    """人工拒绝识别结果。

    【什么时候用】LLM 识别得完全不对，管理员不想用这个建议。
        标记为 rejected 后，这份资料不会出现在"待确认"列表里。

    Args:
        material_id: 资料 id。

    Returns:
        是否成功。
    """
    db_mysql.execute(
        "UPDATE materials SET detection_status = %s WHERE id = %s",
        (STATUS_REJECTED, material_id),
    )
    return True


def reset_detection(material_id: int) -> bool:
    """清除识别结果，回到 pending 状态。

    【什么时候用】管理员想重新识别（比如换了提示词版本）。

    Returns:
        是否成功。
    """
    db_mysql.execute(
        "UPDATE materials SET "
        "detected_course_name = NULL, "
        "detected_knowledge_points = NULL, "
        "detection_confidence = NULL, "
        "detection_reasoning = NULL, "
        "detection_status = %s, "
        "detection_at = NULL "
        "WHERE id = %s",
        (STATUS_PENDING, material_id),
    )
    return True


# ==============================================================
# 删
# ==============================================================
def delete(material_id: int) -> bool:
    """删除资料记录。

    【注意】这个方法只删数据库记录，不删磁盘上的原始文件。
        删文件是另一个操作（M0 模块的事）。

    Returns:
        是否删除成功。
    """
    affected = db_mysql.execute("DELETE FROM materials WHERE id = %s", (material_id,))
    return affected > 0


# ==============================================================
# 内部工具
# ==============================================================
def _decorate(row: dict[str, Any]) -> dict[str, Any]:
    """把数据库行整理成对外结构。

    主要是把 detected_knowledge_points 这个 JSON 字符串
    解析成 Python 列表，让调用方不用自己解析。
    """
    row = dict(row)

    # 解析知识点 JSON
    raw_kp = row.get("detected_knowledge_points")
    if raw_kp:
        try:
            parsed = json.loads(raw_kp)
            row["detected_knowledge_points"] = (
                parsed if isinstance(parsed, list) else []
            )
        except (json.JSONDecodeError, TypeError):
            # 解析失败不抛异常，返回空列表。
            # 理由：脏数据不该让整个页面崩掉。
            row["detected_knowledge_points"] = []
    else:
        row["detected_knowledge_points"] = []

    return row
# ==============================================================
# 删除
# ==============================================================
def get_delete_preview(material_id: int) -> dict:
    """删除前的预览：告诉用户会删什么、不会删什么。

    【为什么需要预览】
        删除是破坏性操作。用户点"删除"前应该知道：
          - 有多少 chunk 会被清
          - 有多少题会变成"孤儿"（题目还在，但来源已删）
          - 有没有正在跑的任务（有的话不能删）

    Returns:
        {
          "material_id": int,
          "source_file": str,
          "chunk_count": int,
          "question_count": int,
          "running_tasks": int,
          "can_delete": bool,
          "block_reason": str | None,
        }
    """
    from app.database import connection as db_mysql

    material = get_by_id(material_id)
    if material is None:
        return {
            "material_id": material_id,
            "source_file": "",
            "chunk_count": 0,
            "question_count": 0,
            "running_tasks": 0,
            "can_delete": False,
            "block_reason": "资料不存在",
        }

    source_file = material["source_file"]

    # 1. 统计有多少题来自这份资料
    #    题目入库时把 chunk_id（含文件 slug 前缀）写进了 source_ref
    #    所以按 "slug_%" 匹配
    from app.pipeline.chunker import slugify
    prefix = slugify(source_file)

    row = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n FROM question_bank "
        "WHERE status = 'active' AND source_ref LIKE %s",
        (f"{prefix}_%",),
    )
    question_count = int(row["n"]) if row else 0

    # 2. 查有没有正在跑的任务
    task_row = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n FROM parse_tasks "
        "WHERE source_file = %s AND status IN ('pending', 'running')",
        (source_file,),
    )
    running_tasks = int(task_row["n"]) if task_row else 0

    can_delete = running_tasks == 0
    block_reason = None
    if running_tasks > 0:
        block_reason = f"有 {running_tasks} 个解析任务正在执行，请等它跑完或暂停后再删除"

    return {
        "material_id": material_id,
        "source_file": source_file,
        "chunk_count": material.get("chunk_count") or 0,
        "question_count": question_count,
        "running_tasks": running_tasks,
        "can_delete": can_delete,
        "block_reason": block_reason,
    }


def delete_material(material_id: int, delete_file: bool = True) -> dict:
    """删除一份资料。

    【做什么】
        1. 从 FAISS 向量库删除所有 chunk
        2. 从磁盘删除原文件
        3. 从 parse_tasks 删除任务记录
        4. 从 materials 删除资料记录（级联删 material_course_map）

    【不删什么】
        - 从这份资料出的题（question_bank）：题目已独立存在，
          可能有学生答过，进过错题集。删资料不等于撤回题目。
          如果要清理题目，到"题库浏览"页手动废弃。
        - 学生的错题（wrong_questions）：同理由。
        - llm_call_log：成本审计要留痕。

    【为什么先删向量再删数据库记录】
        如果先删数据库记录，`materials` 没了，
        但 FAISS 里还有 chunk——这就成了孤儿。
        反过来的话：如果 FAISS 删除失败，数据库记录还在，
        用户看到"资料还在"可以重试，比"资料没了但向量还在"容易处理。

    Args:
        material_id: 资料 id。
        delete_file: 是否删除磁盘上的原文件。默认 True。

    Returns:
        {
          "ok": bool,
          "source_file": str,
          "deleted_chunks": int,
          "deleted_file": bool,
          "deleted_tasks": int,
          "warnings": [str],
          "error": str | None,
        }
    """
    from pathlib import Path

    from app.config import UPLOAD_DIR
    from app.database import connection as db_mysql
    from app.pipeline import indexer

    warnings: list[str] = []

    material = get_by_id(material_id)
    if material is None:
        return {
            "ok": False,
            "source_file": "",
            "deleted_chunks": 0,
            "deleted_file": False,
            "deleted_tasks": 0,
            "warnings": [],
            "error": f"资料 id={material_id} 不存在",
        }

    source_file = material["source_file"]

    # 检查有没有正在跑的任务
    preview = get_delete_preview(material_id)
    if not preview["can_delete"]:
        return {
            "ok": False,
            "source_file": source_file,
            "deleted_chunks": 0,
            "deleted_file": False,
            "deleted_tasks": 0,
            "warnings": [],
            "error": preview["block_reason"] or "无法删除",
        }

    # ---------- 1. 从 FAISS 删除所有 chunk ----------
    deleted_chunks = 0
    try:
        deleted_chunks = indexer.delete_by_source(source_file)
    except Exception as exc:
        # 向量库不可用（索引损坏、FAISS 未安装等）
        # 不阻断删除——数据库和磁盘还能删。
        warnings.append(f"向量库删除失败（不影响其他清理）：{exc}")

    # ---------- 2. 从磁盘删除原文件 ----------
    deleted_file = False
    if delete_file:
        file_path = UPLOAD_DIR / source_file
        try:
            if file_path.is_file():
                file_path.unlink()
                deleted_file = True
        except Exception as exc:
            warnings.append(f"删除原文件失败：{exc}")

    # ---------- 3. 删除 parse_tasks 记录 ----------
    deleted_tasks = 0
    try:
        deleted_tasks = db_mysql.execute(
            "DELETE FROM parse_tasks WHERE source_file = %s",
            (source_file,),
        )
    except Exception as exc:
        warnings.append(f"删除任务记录失败：{exc}")

    # ---------- 4. 删除 materials 记录 ----------
    # material_course_map 是外键级联删除
    try:
        db_mysql.execute(
            "DELETE FROM materials WHERE id = %s",
            (material_id,),
        )
    except Exception as exc:
        return {
            "ok": False,
            "source_file": source_file,
            "deleted_chunks": deleted_chunks,
            "deleted_file": deleted_file,
            "deleted_tasks": deleted_tasks,
            "warnings": warnings,
            "error": f"删除资料记录失败：{exc}",
        }

    return {
        "ok": True,
        "source_file": source_file,
        "deleted_chunks": deleted_chunks,
        "deleted_file": deleted_file,
        "deleted_tasks": deleted_tasks,
        "warnings": warnings,
        "error": None,
    }