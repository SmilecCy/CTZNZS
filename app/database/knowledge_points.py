# -*- coding: utf-8 -*-
"""知识点服务：CRUD、批量建、按课程查。

【为什么知识点单独一个 service】

    知识点有两个特殊之处：
      1. 它由资料识别自动生成（LLM 从资料里抽出来），
         所以"批量建"是主要用法，不是"逐个手动建"。
      2. 它支持多级（parent_id），虽然当前只用一级，
         但表结构支持，代码要预留。

【删除策略】

    知识点是**硬删除**（直接 DELETE）。
    理由：知识点不像课程那样关联一堆业务数据。
    删了之后，引用它的题目会 knowledge_point_id = NULL（外键 SET NULL），
    但题目还在，只是变成"未分类"状态。
"""

from __future__ import annotations

from typing import Any

from app.database import cache, connection as db_mysql


# ==============================================================
# 异常
# ==============================================================
class KnowledgePointError(RuntimeError):
    """知识点操作的统一异常基类。"""


class KnowledgePointNotFoundError(KnowledgePointError):
    """知识点不存在。"""


# ==============================================================
# 建
# ==============================================================
def create(
    course_id: int,
    name: str,
    description: str = "",
    parent_id: int | None = None,
    source_material_id: int | None = None,
    sort_order: int = 0,
) -> int:
    """新建一个知识点。

    Args:
        course_id: 所属课程 id。
        name: 知识点名。
        description: 说明。
        parent_id: 父知识点 id。None 表示一级知识点。
        source_material_id: 这个知识点从哪份资料抽出来的。
        sort_order: 排序权重，数字小的排前面。

    Returns:
        新知识点的 id。

    Raises:
        KnowledgePointError: 参数不合法。
    """
    name = (name or "").strip()
    if not name:
        raise KnowledgePointError("知识点名不能为空")

    # 先查重（同一课程下同名知识点不允许重复）
    existing = get_by_name(course_id, name)
    if existing is not None:
        # 已存在就返回它的 id，不报错。
        # 【为什么这样设计】批量建的时候，资料里同一知识点可能出现多次，
        # 报错会导致整批失败，而实际上"已经存在"就是想要的结果。
        return int(existing["id"])

    kp_id = db_mysql.insert_returning_id(
        "INSERT INTO knowledge_points "
        "(course_id, name, description, parent_id, source_material_id, sort_order) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (course_id, name, description, parent_id, source_material_id, sort_order),
    )

    # 该课程的知识点列表变了，清缓存
    cache.invalidate_knowledge_points(course_id)

    return kp_id


def bulk_create(
    course_id: int,
    names: list[str],
    source_material_id: int | None = None,
) -> list[int]:
    """批量建知识点。

    【为什么单独一个函数】
        资料识别会一次返回一批知识点名（比如 8 个）。
        逐个调 create 也行，但每次都清一次缓存没必要。
        批量处理能少清几次缓存。

    Args:
        course_id: 所属课程。
        names: 知识点名列表。
        source_material_id: 来源资料 id。

    Returns:
        新建/已存在的知识点 id 列表，与输入顺序对应。
        名字重复的会复用已有的，不重复建。
    """
    # 先把该课程现有的知识点全查出来，避免每次循环都查一次数据库
    existing = {
        row["name"]: row["id"]
        for row in db_mysql.fetch_all(
            "SELECT id, name FROM knowledge_points WHERE course_id = %s",
            (course_id,),
        )
    }

    ids: list[int] = []
    created_any = False

    for idx, raw_name in enumerate(names):
        name = (raw_name or "").strip()
        if not name:
            continue

        if name in existing:
            # 已存在，复用
            ids.append(int(existing[name]))
            continue

        # 不存在，新建
        kp_id = db_mysql.insert_returning_id(
            "INSERT INTO knowledge_points "
            "(course_id, name, source_material_id, sort_order) "
            "VALUES (%s, %s, %s, %s)",
            (course_id, name, source_material_id, idx),
        )
        ids.append(kp_id)
        existing[name] = kp_id
        created_any = True

    # 只有真的新建了才清缓存
    if created_any:
        cache.invalidate_knowledge_points(course_id)

    return ids


# ==============================================================
# 查
# ==============================================================
def get_by_id(kp_id: int) -> dict[str, Any] | None:
    """按 id 查知识点。"""
    return db_mysql.fetch_one(
        "SELECT id, course_id, parent_id, name, description, "
        "source_material_id, sort_order, created_at "
        "FROM knowledge_points WHERE id = %s",
        (kp_id,),
    )


def get_by_name(course_id: int, name: str) -> dict[str, Any] | None:
    """按课程+名字查知识点。

    【为什么需要】建知识点时先查重，避免同名。
    """
    return db_mysql.fetch_one(
        "SELECT id, course_id, parent_id, name, description, "
        "source_material_id, sort_order, created_at "
        "FROM knowledge_points WHERE course_id = %s AND name = %s",
        (course_id, (name or "").strip()),
    )


def list_by_course(course_id: int, use_cache: bool = True) -> list[dict[str, Any]]:
    """列出某课程的所有知识点。

    Args:
        course_id: 课程 id。
        use_cache: 是否使用缓存。默认 True。
            传 False 用于"必须看到最新数据"的场景（比如后台管理页刚改完）。

    Returns:
        知识点列表，按 sort_order 排序。
    """
    if use_cache:
        cached = cache.get(cache.knowledge_points_key(course_id))
        if cached is not None:
            return cached

    rows = db_mysql.fetch_all(
        "SELECT id, course_id, parent_id, name, description, "
        "source_material_id, sort_order, created_at "
        "FROM knowledge_points WHERE course_id = %s "
        "ORDER BY sort_order, id",
        (course_id,),
    )

    if use_cache:
        cache.set(cache.knowledge_points_key(course_id), rows, ttl=600)   # 10 分钟

    return rows


def list_names(course_id: int) -> list[str]:
    """只取知识点名列表。

    【用途】提示词渲染时需要"本课程有哪些知识点"，
        只要名字，不需要完整记录。
    """
    return [row["name"] for row in list_by_course(course_id)]


def count_by_course(course_id: int) -> int:
    """统计某课程的知识点数。"""
    row = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n FROM knowledge_points WHERE course_id = %s",
        (course_id,),
    )
    return int(row["n"]) if row else 0


# ==============================================================
# 改
# ==============================================================
def update(
    kp_id: int,
    name: str | None = None,
    description: str | None = None,
    sort_order: int | None = None,
) -> bool:
    """改知识点。

    Args:
        kp_id: 知识点 id。
        name: 新名字；None 表示不改。
        description: 新描述；None 表示不改。
        sort_order: 新排序；None 表示不改。

    Returns:
        是否更新成功。

    Raises:
        KnowledgePointNotFoundError: 知识点不存在。
        KnowledgePointError: 改成的新名字与同课程下其他知识点冲突。
    """
    kp = get_by_id(kp_id)
    if kp is None:
        raise KnowledgePointNotFoundError(f"知识点 id={kp_id} 不存在")

    sets: list[str] = []
    params: list[Any] = []

    if name is not None:
        new_name = name.strip()
        if not new_name:
            raise KnowledgePointError("知识点名不能为空")

        # 改名字要查重（除非改的还是原来的名字）
        if new_name != kp["name"]:
            conflict = get_by_name(kp["course_id"], new_name)
            if conflict is not None:
                raise KnowledgePointError(
                    f"课程下已存在同名知识点「{new_name}」"
                )
        sets.append("name = %s")
        params.append(new_name)

    if description is not None:
        sets.append("description = %s")
        params.append(description)

    if sort_order is not None:
        sets.append("sort_order = %s")
        params.append(sort_order)

    if not sets:
        return True

    params.append(kp_id)
    db_mysql.execute(
        f"UPDATE knowledge_points SET {', '.join(sets)} WHERE id = %s",
        tuple(params),
    )

    cache.invalidate_knowledge_points(kp["course_id"])
    return True


# ==============================================================
# 删除（硬删除）
# ==============================================================
def delete(kp_id: int) -> bool:
    """硬删除知识点。

    【硬删除的影响】
        - 引用它的题目：knowledge_point_id 会被置 NULL（外键 SET NULL），
          题目还在，只是变成未分类。
        - 引用它的子知识点：parent_id 会被置 NULL（外键 SET NULL），
          子知识点不受影响。

    【什么时候用】
        知识点建错了（比如 LLM 抽错了一个词），直接删掉。
        或者两个知识点名不同但语义相同，删一个留一个。

    Args:
        kp_id: 知识点 id。

    Returns:
        是否删除成功（False 表示不存在）。
    """
    kp = get_by_id(kp_id)
    if kp is None:
        return False

    db_mysql.execute("DELETE FROM knowledge_points WHERE id = %s", (kp_id,))

    cache.invalidate_knowledge_points(kp["course_id"])
    return True


def delete_by_course(course_id: int) -> int:
    """删除某课程下的所有知识点。

    【用途】资料重新分类时，可能要把旧的知识点全清了重建。

    Returns:
        删除的数量。
    """
    count = db_mysql.execute(
        "DELETE FROM knowledge_points WHERE course_id = %s",
        (course_id,),
    )
    cache.invalidate_knowledge_points(course_id)
    return count


# ==============================================================
# 与资料关联
# ==============================================================
def list_by_material(material_id: int) -> list[dict[str, Any]]:
    """列出某份资料关联的知识点。

    【用途】资料分类确认页需要显示"这份资料抽出了哪些知识点"。

    Args:
        material_id: 资料 id。

    Returns:
        知识点列表。
    """
    return db_mysql.fetch_all(
        "SELECT id, course_id, name, description, source_material_id, sort_order "
        "FROM knowledge_points WHERE source_material_id = %s "
        "ORDER BY sort_order, id",
        (material_id,),
    )