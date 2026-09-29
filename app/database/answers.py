# -*- coding: utf-8 -*-
"""作答记录（MySQL 版）。

【这个模块做什么】

    1. 写入作答流水（答对答错都记）
    2. 查询某学生的作答历史

【与 wrong_book_mysql 的关系】

    answer_records：全量流水。每次作答写一条，答对答错都写。
    wrong_questions：学习状态。答错时才写，同题去重。

    两者并存——流水账用于统计，学习状态用于复习。
"""

from __future__ import annotations

import json
from typing import Any

from app.database import connection as db_mysql


def record_answer(
    user_id: int,
    course_id: int,
    question: dict,
    user_answer: str,
    is_correct: bool | None,
    score: float | None = None,
    graded_by: str = "auto",
) -> int:
    """写入一条作答记录。

    Args:
        user_id: 学生 id。
        course_id: 课程 id。
        question: 题目 dict（含 id / question / ...）。
        user_answer: 学生的作答。
        is_correct: 是否正确；None 表示没判出对错。
        score: 得分比例 0.0~1.0。
        graded_by: 判分方式（auto / llm / manual）。

    Returns:
        作答记录 id。
    """
    question_snapshot = json.dumps(
        {
            "question": question.get("question", ""),
            "question_type": question.get("question_type"),
            "options": question.get("options"),
            "correct_index": question.get("correct_index"),
            "reference_answer": question.get("reference_answer"),
            "scoring_points": question.get("scoring_points"),
        },
        ensure_ascii=False,
        default=str,
    )

    return db_mysql.insert_returning_id(
        "INSERT INTO answer_records "
        "(user_id, course_id, question_id, question_type, user_answer, "
        "is_correct, score, question_snapshot, graded_by) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            user_id,
            course_id,
            question.get("id"),
            question.get("question_type"),
            user_answer,
            None if is_correct is None else int(is_correct),
            score,
            question_snapshot,
            graded_by,
        ),
    )


def list_answers(
    user_id: int,
    course_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """查询作答历史。"""
    sql = "SELECT * FROM answer_records WHERE user_id = %s"
    params: list[Any] = [user_id]

    if course_id is not None:
        sql += " AND course_id = %s"
        params.append(course_id)

    sql += " ORDER BY id DESC LIMIT %s"
    params.append(int(limit))

    return db_mysql.fetch_all(sql, tuple(params))


def answer_stats(user_id: int, course_id: int) -> dict[str, Any]:
    """作答统计。"""
    row = db_mysql.fetch_one(
        "SELECT "
        "COUNT(*) AS total, "
        "COALESCE(SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END), 0) AS correct, "
        "COALESCE(SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END), 0) AS wrong, "
        "COALESCE(SUM(CASE WHEN is_correct IS NULL THEN 1 ELSE 0 END), 0) AS unknown "
        "FROM answer_records WHERE user_id = %s AND course_id = %s",
        (user_id, course_id),
    )

    return {
        "total": int(row["total"]) if row else 0,
        "correct": int(row["correct"]) if row else 0,
        "wrong": int(row["wrong"]) if row else 0,
        "unknown": int(row["unknown"]) if row else 0,
    }