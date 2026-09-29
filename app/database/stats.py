# -*- coding: utf-8 -*-
"""学习统计服务：总览、趋势、知识点掌握度。

【数据来源】
    - 作答记录（answer_records）：每次作答流水
    - 错题集（wrong_questions）：当前错题状态
    - 题库（question_bank）：题目总数
"""

from __future__ import annotations

from typing import Any

from app.database import connection as db_mysql


def get_overview(user_id: int, course_id: int) -> dict[str, Any]:
    """获取学习统计总览。

    Returns:
        {
            "total_answered": int,     # 总作答数
            "total_correct": int,      # 正确数
            "accuracy": float,         # 正确率 0.00~1.00
            "wrong_count": int,        # 当前错题数
            "mastered_count": int,     # 已掌握错题数
            "total_questions": int,    # 课程题库总数
            "study_days": int,         # 累计学习天数
        }
    """
    # 作答统计
    stats = db_mysql.fetch_one(
        "SELECT "
        "  COUNT(*) AS total_answered, "
        "  SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS total_correct "
        "FROM answer_records "
        "WHERE user_id = %s AND course_id = %s",
        (user_id, course_id),
    )

    total_answered = int(stats["total_answered"]) if stats else 0
    total_correct = int(stats["total_correct"]) if stats else 0
    accuracy = round(total_correct / total_answered, 4) if total_answered > 0 else 0.0

    # 错题统计
    wrong = db_mysql.fetch_one(
        "SELECT "
        "  COUNT(*) AS wrong_count, "
        "  SUM(CASE WHEN mastery_status = 'mastered' THEN 1 ELSE 0 END) AS mastered_count "
        "FROM wrong_questions "
        "WHERE user_id = %s AND course_id = %s",
        (user_id, course_id),
    )
    wrong_count = int(wrong["wrong_count"]) if wrong else 0
    mastered_count = int(wrong["mastered_count"]) if wrong else 0

    # 题库总数
    bank = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n FROM question_bank WHERE course_id = %s AND is_active = 1",
        (course_id,),
    )
    total_questions = int(bank["n"]) if bank else 0

    # 学习天数（按作答日期去重）
    days_row = db_mysql.fetch_one(
        "SELECT COUNT(DISTINCT DATE(created_at)) AS n "
        "FROM answer_records WHERE user_id = %s AND course_id = %s",
        (user_id, course_id),
    )
    study_days = int(days_row["n"]) if days_row else 0

    return {
        "total_answered": total_answered,
        "total_correct": total_correct,
        "accuracy": accuracy,
        "wrong_count": wrong_count,
        "mastered_count": mastered_count,
        "total_questions": total_questions,
        "study_days": study_days,
    }


def get_trend(
    user_id: int,
    course_id: int,
    days: int = 30,
) -> list[dict[str, Any]]:
    """获取正确率趋势（最近 N 天）。

    Returns:
        按天排列的列表，每项 {"date": "2024-01-15", "accuracy": 0.85, "count": 20}
    """
    return db_mysql.fetch_all(
        "SELECT "
        "  DATE(created_at) AS date, "
        "  COUNT(*) AS count, "
        "  ROUND(SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) / COUNT(*), 4) AS accuracy "
        "FROM answer_records "
        "WHERE user_id = %s AND course_id = %s "
        "  AND created_at >= DATE_SUB(CURDATE(), INTERVAL %s DAY) "
        "GROUP BY DATE(created_at) "
        "ORDER BY date ASC",
        (user_id, course_id, days),
    )


def get_knowledge_point_mastery(
    user_id: int,
    course_id: int,
) -> list[dict[str, Any]]:
    """获取知识点掌握度。

    Returns:
        按知识点排列的列表，每项:
        {
            "knowledge_point": str,
            "total": int,        # 该知识点总作答数
            "correct": int,      # 正确数
            "accuracy": float,   # 正确率
        }
    """
    return db_mysql.fetch_all(
        "SELECT "
        "  ar.knowledge_point, "
        "  COUNT(*) AS total, "
        "  SUM(CASE WHEN ar.is_correct = 1 THEN 1 ELSE 0 END) AS correct, "
        "  ROUND(SUM(CASE WHEN ar.is_correct = 1 THEN 1 ELSE 0 END) / COUNT(*), 4) AS accuracy "
        "FROM answer_records ar "
        "WHERE ar.user_id = %s AND ar.course_id = %s "
        "  AND ar.knowledge_point IS NOT NULL AND ar.knowledge_point != '' "
        "GROUP BY ar.knowledge_point "
        "ORDER BY accuracy ASC",
        (user_id, course_id),
    )