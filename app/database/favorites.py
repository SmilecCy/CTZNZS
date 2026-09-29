# -*- coding: utf-8 -*-
"""收藏服务：题目收藏的增删查。

【收藏 vs 错题】
    收藏是用户主观标记"这道题值得反复看"，
    错题是系统自动记录"用户答错了"。
    两者独立，互不影响。
"""

from __future__ import annotations

from typing import Any

from app.database import connection as db_mysql


def add_favorite(user_id: int, question_id: int) -> bool:
    """收藏一道题目。

    Args:
        user_id: 用户 id。
        question_id: 题目 id。

    Returns:
        是否成功。已收藏的返回 True（幂等）。
    """
    existing = db_mysql.fetch_one(
        "SELECT id FROM question_favorites WHERE user_id = %s AND question_id = %s",
        (user_id, question_id),
    )
    if existing:
        return True

    db_mysql.execute(
        "INSERT INTO question_favorites (user_id, question_id) VALUES (%s, %s)",
        (user_id, question_id),
    )
    return True


def remove_favorite(user_id: int, question_id: int) -> bool:
    """取消收藏。

    Args:
        user_id: 用户 id。
        question_id: 题目 id。

    Returns:
        是否成功。
    """
    db_mysql.execute(
        "DELETE FROM question_favorites WHERE user_id = %s AND question_id = %s",
        (user_id, question_id),
    )
    return True


def is_favorited(user_id: int, question_id: int) -> bool:
    """检查某题是否已被收藏。"""
    row = db_mysql.fetch_one(
        "SELECT id FROM question_favorites WHERE user_id = %s AND question_id = %s",
        (user_id, question_id),
    )
    return row is not None


def list_favorites(
    user_id: int,
    course_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """列出用户的收藏题目。

    Args:
        user_id: 用户 id。
        course_id: 限定课程；None 表示不限。
        limit: 每页条数。
        offset: 偏移量。

    Returns:
        收藏列表，含题目详情。
    """
    sql = (
        "SELECT qf.id AS fav_id, qf.created_at AS fav_at, "
        "qb.id, qb.question, qb.question_type, qb.difficulty, "
        "qb.options, qb.correct_index, qb.reference_answer, "
        "qb.explanation, qb.knowledge_tags "
        "FROM question_favorites qf "
        "JOIN question_bank qb ON qf.question_id = qb.id "
        "WHERE qf.user_id = %s"
    )
    params: list[Any] = [user_id]

    if course_id is not None:
        sql += " AND qb.course_id = %s"
        params.append(course_id)

    sql += " ORDER BY qf.created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    return db_mysql.fetch_all(sql, tuple(params))


def count_favorites(user_id: int, course_id: int | None = None) -> int:
    """统计收藏数。"""
    sql = "SELECT COUNT(*) AS n FROM question_favorites WHERE user_id = %s"
    params: list[Any] = [user_id]

    if course_id is not None:
        sql += " AND question_id IN (SELECT id FROM question_bank WHERE course_id = %s)"
        params.append(course_id)

    row = db_mysql.fetch_one(sql, tuple(params))
    return int(row["n"]) if row else 0