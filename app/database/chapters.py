# -*- coding: utf-8 -*-
"""章节服务：章节 CRUD、章节树构建。

【章节 vs 知识点】
    章节是课程的结构骨架（一级节点，node_type='chapter'），
    知识点是章节下的具体内容（二级节点，node_type='knowledge'）。
    两者共用 knowledge_points 表，通过 node_type 区分。

【多级支持】
    章节通过 parent_id 支持多级（章→节→小节），
    知识点始终挂在某个章节下（parent_id 指向章节 id）。
"""

from __future__ import annotations

from typing import Any

from app.database import connection as db_mysql


# ==============================================================
# 异常
# ==============================================================
class ChapterError(RuntimeError):
    """章节操作的统一异常基类。"""


class ChapterNotFoundError(ChapterError):
    """章节不存在。"""


# ==============================================================
# 建
# ==============================================================
def create_chapter(
    course_id: int,
    name: str,
    parent_id: int | None = None,
    summary: str = "",
    sort_order: int = 0,
) -> int:
    """新建一个章节。

    Args:
        course_id: 所属课程 id。
        name: 章节名。
        parent_id: 父章节 id。None 表示顶级章节。
        summary: 章节摘要。
        sort_order: 排序权重。

    Returns:
        新章节的 id。

    Raises:
        ChapterError: 参数不合法或同名。
    """
    name = (name or "").strip()
    if not name:
        raise ChapterError("章节名不能为空")

    existing = get_chapter_by_name(course_id, name)
    if existing is not None:
        raise ChapterError(f"章节「{name}」已存在（id={existing['id']}）")

    chapter_id = db_mysql.insert_returning_id(
        "INSERT INTO knowledge_points "
        "(course_id, node_type, parent_id, name, summary, sort_order) "
        "VALUES (%s, 'chapter', %s, %s, %s, %s)",
        (course_id, parent_id, name, summary, sort_order),
    )
    return chapter_id


def bulk_create_chapters(
    course_id: int,
    chapters: list[dict[str, Any]],
    parent_id: int | None = None,
) -> list[int]:
    """批量建章节（含子章节）。

    Args:
        course_id: 所属课程。
        chapters: 章节列表，每项 {"title": str, "summary": str, "children": [...]}。
        parent_id: 父章节 id。

    Returns:
        新建的章节 id 列表。
    """
    ids: list[int] = []
    for idx, ch in enumerate(chapters):
        title = (ch.get("title") or "").strip()
        if not title:
            continue
        summary = (ch.get("summary") or "").strip()

        # 重名则跳过
        existing = _get_by_course_and_name_quiet(course_id, title)
        if existing is not None:
            ch_id = int(existing["id"])
        else:
            ch_id = db_mysql.insert_returning_id(
                "INSERT INTO knowledge_points "
                "(course_id, node_type, parent_id, name, summary, sort_order) "
                "VALUES (%s, 'chapter', %s, %s, %s, %s)",
                (course_id, parent_id, title, summary, idx),
            )
        ids.append(ch_id)

        # 递归创建子章节
        children = ch.get("children") or []
        if children:
            bulk_create_chapters(course_id, children, parent_id=ch_id)

    return ids


# ==============================================================
# 查
# ==============================================================
def get_chapter_by_id(chapter_id: int) -> dict[str, Any] | None:
    """按 id 查章节。"""
    return db_mysql.fetch_one(
        "SELECT id, course_id, parent_id, node_type, name, summary, "
        "sort_order, created_at "
        "FROM knowledge_points WHERE id = %s AND node_type = 'chapter'",
        (chapter_id,),
    )


def get_chapter_by_name(course_id: int, name: str) -> dict[str, Any] | None:
    """按课程+名字查章节。"""
    return db_mysql.fetch_one(
        "SELECT id, course_id, parent_id, node_type, name, summary, "
        "sort_order, created_at "
        "FROM knowledge_points WHERE course_id = %s AND name = %s AND node_type = 'chapter'",
        (course_id, (name or "").strip()),
    )


def _get_by_course_and_name_quiet(course_id: int, name: str) -> dict[str, Any] | None:
    """查重（不报错版本），用于批量建。"""
    return db_mysql.fetch_one(
        "SELECT id FROM knowledge_points "
        "WHERE course_id = %s AND name = %s AND node_type = 'chapter'",
        (course_id, (name or "").strip()),
    )


def list_chapters(course_id: int) -> list[dict[str, Any]]:
    """列出某课程的所有章节（扁平列表）。"""
    return db_mysql.fetch_all(
        "SELECT id, course_id, parent_id, node_type, name, summary, "
        "sort_order, created_at "
        "FROM knowledge_points WHERE course_id = %s AND node_type = 'chapter' "
        "ORDER BY sort_order, id",
        (course_id,),
    )


def get_chapter_tree(course_id: int) -> list[dict[str, Any]]:
    """构建章节树。

    Returns:
        章节树列表，每项含 children 递归子节点。
    """
    flat = list_chapters(course_id)
    # 构建 id → node 映射
    node_map: dict[int, dict[str, Any]] = {}
    for row in flat:
        row["children"] = []
        node_map[int(row["id"])] = row

    roots: list[dict[str, Any]] = []
    for row in flat:
        pid = row.get("parent_id")
        if pid is not None and pid in node_map:
            node_map[int(pid)]["children"].append(row)
        else:
            roots.append(row)

    return roots


def count_chapters(course_id: int) -> int:
    """统计某课程的章节数。"""
    row = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n FROM knowledge_points "
        "WHERE course_id = %s AND node_type = 'chapter'",
        (course_id,),
    )
    return int(row["n"]) if row else 0


# ==============================================================
# 改
# ==============================================================
def update_chapter(
    chapter_id: int,
    name: str | None = None,
    summary: str | None = None,
    sort_order: int | None = None,
) -> bool:
    """修改章节。

    Args:
        chapter_id: 章节 id。
        name: 新名字；None 表示不改。
        summary: 新摘要；None 表示不改。
        sort_order: 新排序；None 表示不改。

    Returns:
        是否成功。
    """
    ch = get_chapter_by_id(chapter_id)
    if ch is None:
        raise ChapterNotFoundError(f"章节 id={chapter_id} 不存在")

    sets: list[str] = []
    params: list[Any] = []

    if name is not None:
        sets.append("name = %s")
        params.append(name.strip())
    if summary is not None:
        sets.append("summary = %s")
        params.append(summary)
    if sort_order is not None:
        sets.append("sort_order = %s")
        params.append(sort_order)

    if not sets:
        return True

    params.append(chapter_id)
    db_mysql.execute(
        f"UPDATE knowledge_points SET {', '.join(sets)} WHERE id = %s",
        tuple(params),
    )
    return True


# ==============================================================
# 删
# ==============================================================
def delete_chapter(chapter_id: int, cascade: bool = False) -> bool:
    """删除章节。

    Args:
        chapter_id: 章节 id。
        cascade: 是否级联删除子章节。默认 False，会先检查有没有子节点。

    Returns:
        是否成功。

    Raises:
        ChapterError: 有子章节且 cascade=False。
    """
    ch = get_chapter_by_id(chapter_id)
    if ch is None:
        raise ChapterNotFoundError(f"章节 id={chapter_id} 不存在")

    if not cascade:
        children = db_mysql.fetch_all(
            "SELECT COUNT(*) AS n FROM knowledge_points "
            "WHERE parent_id = %s AND node_type = 'chapter'",
            (chapter_id,),
        )
        if children and int(children[0]["n"]) > 0:
            raise ChapterError(
                f"章节「{ch['name']}」下还有子章节，请先删除子章节或使用级联删除"
            )

    db_mysql.execute(
        "DELETE FROM knowledge_points WHERE id = %s",
        (chapter_id,),
    )
    return True


def delete_all_chapters(course_id: int) -> int:
    """删除某课程的所有章节。

    Returns:
        删除的章节数。
    """
    row = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n FROM knowledge_points "
        "WHERE course_id = %s AND node_type = 'chapter'",
        (course_id,),
    )
    count = int(row["n"]) if row else 0

    db_mysql.execute(
        "DELETE FROM knowledge_points WHERE course_id = %s AND node_type = 'chapter'",
        (course_id,),
    )
    return count


# ==============================================================
# 知识点挂载（按章节查知识点）
# ==============================================================
def list_knowledge_points_by_chapter(chapter_id: int) -> list[dict[str, Any]]:
    """列出某章节下的所有知识点。"""
    return db_mysql.fetch_all(
        "SELECT id, course_id, name, description "
        "FROM knowledge_points WHERE parent_id = %s AND node_type = 'knowledge' "
        "ORDER BY sort_order, id",
        (chapter_id,),
    )


def count_questions_by_chapter(chapter_id: int) -> int:
    """统计某章节下的题目数。"""
    # 先拿到章节下所有知识点的名字，再到题库里 count
    row = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n FROM question_bank qb "
        "JOIN knowledge_points kp ON qb.knowledge_point_id = kp.id "
        "WHERE kp.parent_id = %s",
        (chapter_id,),
    )
    return int(row["n"]) if row else 0


def clear_questions_by_chapter(chapter_id: int) -> int:
    """废弃某章节下的所有题目。返回废弃数。"""
    return db_mysql.execute(
        "UPDATE question_bank qb "
        "JOIN knowledge_points kp ON qb.knowledge_point_id = kp.id "
        "SET qb.status = 'deprecated' "
        "WHERE kp.parent_id = %s AND qb.status = 'active'",
        (chapter_id,),
    )