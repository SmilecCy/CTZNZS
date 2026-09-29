# -*- coding: utf-8 -*-
"""错题集（MySQL 版）。

【这个模块做什么】

    1. 收录错题（同题去重，累加错次）
    2. 查询错题（多维度筛选）
    3. 修改掌握状态
    4. 复习记录
    5. 统计

【三条设计原则】

    1. **同一道题答错多次只保留一条**
       错题集的价值在于"哪些知识点我还没拿下"，
       同一道题出现五遍只会把清单撑爆。

    2. **掌握度由用户点，不自动判定**
       重做之后系统只如实展示结果，是否算"已掌握"由用户说了算。

    3. **但重新答错会把状态打回"待复习"**
       这与第 2 条不矛盾：系统不判断"你自认为掌握了吗"，
       但"你又错了一次"是客观事实。
"""

from __future__ import annotations

import json
from typing import Any

from app.database import connection as db_mysql


# ==============================================================
# 常量
# ==============================================================
MASTERY_UNMASTERED = "unmastered"
MASTERY_MASTERED = "mastered"

MASTERY_LABELS = {
    MASTERY_UNMASTERED: "待复习",
    MASTERY_MASTERED: "已掌握",
}

# 错误原因标签
ERROR_TAGS = (
    "概念混淆",
    "记忆遗漏",
    "审题失误",
    "表述不完整",
    "完全不会",
)

# 排序白名单
ORDER_OPTIONS = {
    "最近答错": "COALESCE(last_wrong_at, created_at) DESC, id DESC",
    "错得最多": "wrong_count DESC, id DESC",
    "最近复习": "COALESCE(last_reviewed, created_at) DESC, id DESC",
    "按知识点": "knowledge_point ASC, id ASC",
}


# ==============================================================
# 收录
# ==============================================================
def record_wrong(
    user_id: int,
    course_id: int,
    question: dict,
    user_answer: str = "",
    knowledge_point: str | None = None,
    error_tags: list[str] | None = None,
) -> int:
    """把一道题收进错题集（同题去重）。

    Args:
        user_id: 学生 id。
        course_id: 课程 id。
        question: 题目 dict（含 id / question / ...）。
        user_answer: 学员作答。
        knowledge_point: 知识点；缺省时取第一个 knowledge_tag。
        error_tags: 错误原因标签。

    Returns:
        错题条目 id（已存在时返回被更新那条的 id）。
    """
    bank_id = question.get("id")
    tags_json = _dump_tags(error_tags)
    kp = knowledge_point or (question.get("knowledge_tags") or [None])[0]

    # 题目快照：只保留题目本体，不存运行期标注
    payload = {
        "question": question.get("question", ""),
        "question_type": question.get("question_type"),
        "options": question.get("options"),
        "correct_index": question.get("correct_index"),
        "reference_answer": question.get("reference_answer"),
        "scoring_points": question.get("scoring_points"),
        "explanation": question.get("explanation"),
        "knowledge_tags": question.get("knowledge_tags"),
        "difficulty": question.get("difficulty"),
    }
    question_json = json.dumps(payload, ensure_ascii=False, default=str)

    # 查有没有已存在的（同课程 + 同题库 id）
    existing = None
    if bank_id is not None:
        existing = db_mysql.fetch_one(
            "SELECT id FROM wrong_questions "
            "WHERE user_id = %s AND course_id = %s AND question_bank_id = %s",
            (user_id, course_id, int(bank_id)),
        )

    if existing is not None:
        # 又错了一次：错次 +1、状态打回待复习
        db_mysql.execute(
            "UPDATE wrong_questions SET "
            "user_answer = %s, "
            "wrong_count = wrong_count + 1, "
            "last_wrong_at = CURRENT_TIMESTAMP, "
            "last_result = 'wrong', "
            "mastery_status = %s, "
            "last_mastered_at = NULL, "
            "error_tags = COALESCE(%s, error_tags) "
            "WHERE id = %s",
            (user_answer, MASTERY_UNMASTERED, tags_json, int(existing["id"])),
        )
        return int(existing["id"])

    # 新收录
    new_id = db_mysql.insert_returning_id(
        "INSERT INTO wrong_questions "
        "(user_id, course_id, question_bank_id, knowledge_point, question_type, "
        "question_json, user_answer, error_tags, wrong_count, last_result, "
        "last_wrong_at, mastery_status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, 'wrong', CURRENT_TIMESTAMP, %s)",
        (
            user_id,
            course_id,
            int(bank_id) if bank_id is not None else None,
            kp,
            question.get("question_type"),
            question_json,
            user_answer,
            tags_json,
            MASTERY_UNMASTERED,
        ),
    )
    return new_id


# ==============================================================
# 查询
# ==============================================================
def list_wrong(
    user_id: int,
    course_id: int,
    knowledge_point: str | None = None,
    question_type: str | None = None,
    mastery_status: str | None = None,
    order_by: str = "最近答错",
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """按条件查询错题。"""
    sql = "SELECT * FROM wrong_questions WHERE user_id = %s AND course_id = %s"
    params: list[Any] = [user_id, course_id]

    if knowledge_point:
        sql += " AND knowledge_point = %s"
        params.append(knowledge_point)
    if question_type:
        sql += " AND question_type = %s"
        params.append(question_type)
    if mastery_status:
        sql += " AND mastery_status = %s"
        params.append(mastery_status)

    order_clause = ORDER_OPTIONS.get(order_by, ORDER_OPTIONS["最近答错"])
    sql += f" ORDER BY {order_clause}"

    if limit:
        sql += " LIMIT %s OFFSET %s"
        params.extend([int(limit), max(int(offset), 0)])

    rows = db_mysql.fetch_all(sql, tuple(params))
    return [_decorate(r) for r in rows]


def get_wrong(entry_id: int, user_id: int) -> dict[str, Any] | None:
    """按 id 查错题（带 user_id 校验，防止越权访问）。"""
    row = db_mysql.fetch_one(
        "SELECT * FROM wrong_questions WHERE id = %s AND user_id = %s",
        (entry_id, user_id),
    )
    return _decorate(row) if row else None


def count_wrong(
    user_id: int,
    course_id: int,
    mastery_status: str | None = None,
) -> int:
    """统计错题数。"""
    sql = "SELECT COUNT(*) AS n FROM wrong_questions WHERE user_id = %s AND course_id = %s"
    params: list[Any] = [user_id, course_id]

    if mastery_status:
        sql += " AND mastery_status = %s"
        params.append(mastery_status)

    row = db_mysql.fetch_one(sql, tuple(params))
    return int(row["n"]) if row else 0


# ==============================================================
# 修改
# ==============================================================
def set_mastery(entry_id: int, user_id: int, mastered: bool) -> bool:
    """标记掌握状态。"""
    status_value = MASTERY_MASTERED if mastered else MASTERY_UNMASTERED
    stamp = "CURRENT_TIMESTAMP" if mastered else "NULL"

    affected = db_mysql.execute(
        f"UPDATE wrong_questions SET mastery_status = %s, last_mastered_at = {stamp} "
        f"WHERE id = %s AND user_id = %s",
        (status_value, entry_id, user_id),
    )
    return affected > 0


def record_review(entry_id: int, user_id: int, correct: bool | None = None) -> dict | None:
    """记录一次复习。

    Args:
        entry_id: 错题 id。
        user_id: 学生 id（权限校验）。
        correct: 这次重做的结果；None 表示"复习了但没判出对错"。

    Returns:
        更新后的统计；条目不存在时返回 None。

    【注意】correct=None 时 last_result 保留旧值——
        "没判出对错"不等于"上次对错作废"。
    """
    if get_wrong(entry_id, user_id) is None:
        return None

    result = None if correct is None else ("right" if correct else "wrong")

    db_mysql.execute(
        "UPDATE wrong_questions SET "
        "review_count = review_count + 1, "
        "correct_count = correct_count + %s, "
        "last_result = COALESCE(%s, last_result), "
        "last_reviewed = CURRENT_TIMESTAMP "
        "WHERE id = %s AND user_id = %s",
        (1 if correct else 0, result, entry_id, user_id),
    )

    return db_mysql.fetch_one(
        "SELECT review_count, correct_count, last_result FROM wrong_questions "
        "WHERE id = %s",
        (entry_id,),
    )


def remove_wrong(entry_id: int, user_id: int) -> bool:
    """删除一条错题。"""
    affected = db_mysql.execute(
        "DELETE FROM wrong_questions WHERE id = %s AND user_id = %s",
        (entry_id, user_id),
    )
    return affected > 0


# ==============================================================
# 统计
# ==============================================================
def wrong_stats(user_id: int, course_id: int) -> dict[str, Any]:
    """错题集总览。"""
    row = db_mysql.fetch_one(
        "SELECT "
        "COUNT(*) AS total, "
        "COALESCE(SUM(CASE WHEN mastery_status = %s THEN 1 ELSE 0 END), 0) AS unmastered, "
        "COALESCE(SUM(CASE WHEN mastery_status = %s THEN 1 ELSE 0 END), 0) AS mastered, "
        "COALESCE(SUM(CASE WHEN review_count = 0 THEN 1 ELSE 0 END), 0) AS never_reviewed "
        "FROM wrong_questions WHERE user_id = %s AND course_id = %s",
        (MASTERY_UNMASTERED, MASTERY_MASTERED, user_id, course_id),
    )

    grouped = db_mysql.fetch_all(
        "SELECT knowledge_point AS kp, COUNT(*) AS n "
        "FROM wrong_questions WHERE user_id = %s AND course_id = %s "
        "GROUP BY knowledge_point ORDER BY n DESC",
        (user_id, course_id),
    )

    return {
        "total": int(row["total"]) if row else 0,
        "unmastered": int(row["unmastered"]) if row else 0,
        "mastered": int(row["mastered"]) if row else 0,
        "never_reviewed": int(row["never_reviewed"]) if row else 0,
        "by_knowledge_point": {
            (r["kp"] or "未归类"): int(r["n"]) for r in grouped
        },
    }


# ==============================================================
# 内部工具
# ==============================================================
def _dump_tags(tags: list[str] | None) -> str | None:
    """把标签列表序列化；空列表存 None。"""
    cleaned = [str(t).strip() for t in (tags or []) if str(t).strip()]
    return json.dumps(cleaned, ensure_ascii=False) if cleaned else None


def _load_tags(raw: Any) -> list[str]:
    """解析标签。"""
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return [str(raw)]
    return [str(x) for x in parsed] if isinstance(parsed, list) else [str(parsed)]


def _load_payload(raw: str | None) -> dict:
    """解析题目 JSON。"""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"question": str(raw), "_parse_error": True}
    return parsed if isinstance(parsed, dict) else {"question": str(parsed)}


def _decorate(row: dict) -> dict:
    """整理数据库行。"""
    row = dict(row)
    row["payload"] = _load_payload(row.get("question_json"))
    row["error_tags"] = _load_tags(row.get("error_tags"))
    row["mastery_label"] = MASTERY_LABELS.get(row.get("mastery_status"), "待复习")
    return row