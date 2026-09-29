# -*- coding: utf-8 -*-
"""笔记服务：题目笔记的增删改查。

【设计原则】
    每道题每个用户最多一条笔记（UNIQUE KEY 保证）。
    如果需要多条笔记，可以在前端拼接或换行。
    简化后端逻辑，让数据一致性强。
"""

from __future__ import annotations

from app.database import connection as db_mysql


def save_note(user_id: int, question_id: int, content: str) -> bool:
    """保存/更新笔记。

    如果已存在则更新，不存在则新建。

    Args:
        user_id: 用户 id。
        question_id: 题目 id。
        content: 笔记内容。

    Returns:
        是否成功。
    """
    content = content.strip()
    if not content:
        return delete_note(user_id, question_id)

    db_mysql.execute(
        "INSERT INTO question_notes (user_id, question_id, content) "
        "VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE content = VALUES(content)",
        (user_id, question_id, content),
    )
    return True


def get_note(user_id: int, question_id: int) -> str | None:
    """读取某题的笔记。

    Args:
        user_id: 用户 id。
        question_id: 题目 id。

    Returns:
        笔记文本，没有则返回 None。
    """
    row = db_mysql.fetch_one(
        "SELECT content FROM question_notes WHERE user_id = %s AND question_id = %s",
        (user_id, question_id),
    )
    return row["content"] if row else None


def delete_note(user_id: int, question_id: int) -> bool:
    """删除笔记。

    Args:
        user_id: 用户 id。
        question_id: 题目 id。

    Returns:
        是否成功。
    """
    db_mysql.execute(
        "DELETE FROM question_notes WHERE user_id = %s AND question_id = %s",
        (user_id, question_id),
    )
    return True