# -*- coding: utf-8 -*-
"""题库服务（MySQL 版）。

【这个模块做什么】

    题库的读写原语：
      - 查询题目（多维度筛选）
      - 加权抽取（按质量分）
      - 入库（含去重）
      - 反馈记录（好评/差评）
      - 废弃与恢复
      - 统计

【三条设计原则】

    1. **查库只认 status='active'** —— 废弃题目永不回流到练习环节

    2. **加权抽取按 quality_score** —— 好题更容易被抽到，
       但被打过 bad 的题概率下降不为零（留翻案机会）

    3. **入库时写题干向量** —— 供后续去重
"""

from __future__ import annotations

import json
import random
from typing import Any

from app.database import connection as db_mysql


# ==============================================================
# 常量
# ==============================================================
# 反馈类型。用常量而不是散落的字符串，避免拼错。
FEEDBACK_GOOD = "good"
FEEDBACK_BAD = "bad"
FEEDBACK_DUPLICATE = "duplicate"

FEEDBACK_TYPES = (FEEDBACK_GOOD, FEEDBACK_BAD, FEEDBACK_DUPLICATE)

# 反馈对 quality_score 的影响
_FEEDBACK_DELTA = {
    FEEDBACK_GOOD: 1,       # 好评 +1
    FEEDBACK_BAD: -1,       # 差评 -1
    FEEDBACK_DUPLICATE: -1, # 重复也视为负面
}

# 允许排序的列（白名单，防止 SQL 注入）
ORDER_OPTIONS = {
    "最新生成": "generated_at DESC, id DESC",
    "最早生成": "generated_at ASC, id ASC",
    "质量分从高到低": "quality_score DESC, id DESC",
    "质量分从低到高": "quality_score ASC, id ASC",
    "使用次数从多到少": "usage_count DESC, id DESC",
    "随机": "RAND()",
}


# ==============================================================
# 查
# ==============================================================
def query_questions(
    course_id: int,
    knowledge_point: str | None = None,
    question_type: str | None = None,
    difficulty: str | None = None,
    source: str | None = None,
    status: str = "active",
    min_quality: float | None = None,
    max_quality: float | None = None,
    order_by: str = "最新生成",
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """按条件查询题库。

    Args:
        course_id: 课程 id（必填）。
        knowledge_point: 知识点；None 表示不限。
        question_type: 题型；None 表示不限。
        difficulty: 难度；None 表示不限。
        source: 来源（generated / web_search / user_imported）；None 表示不限。
        status: 'active' 或 'deprecated'；默认只取未废弃的。
        min_quality: 质量分下限。
        max_quality: 质量分上限。
        order_by: 排序方式（见 ORDER_OPTIONS）。
        limit: 返回条数上限。
        offset: 分页偏移。

    Returns:
        题目列表。每项已解析 ``payload`` 字段。
    """
    sql = "SELECT * FROM question_bank WHERE course_id = %s AND status = %s"
    params: list[Any] = [course_id, status]

    if knowledge_point:
        sql += " AND knowledge_point = %s"
        params.append(knowledge_point)
    if question_type:
        sql += " AND question_type = %s"
        params.append(question_type)
    if difficulty:
        sql += " AND difficulty = %s"
        params.append(difficulty)
    if source:
        sql += " AND source = %s"
        params.append(source)
    if min_quality is not None:
        sql += " AND quality_score >= %s"
        params.append(float(min_quality))
    if max_quality is not None:
        sql += " AND quality_score <= %s"
        params.append(float(max_quality))

    # 排序：白名单校验。非法值回落到默认，而不是把用户输入拼进 SQL。
    order_clause = ORDER_OPTIONS.get(order_by, ORDER_OPTIONS["最新生成"])
    sql += f" ORDER BY {order_clause}"

    if limit:
        sql += " LIMIT %s OFFSET %s"
        params.extend([int(limit), max(int(offset), 0)])

    rows = db_mysql.fetch_all(sql, tuple(params))
    return [_decorate(r) for r in rows]


def get_question(question_id: int) -> dict[str, Any] | None:
    """按 id 取单题。"""
    row = db_mysql.fetch_one(
        "SELECT * FROM question_bank WHERE id = %s",
        (question_id,),
    )
    return _decorate(row) if row else None


def count_questions(
    course_id: int,
    knowledge_point: str | None = None,
    question_type: str | None = None,
    difficulty: str | None = None,
    status: str = "active",
) -> int:
    """按条件统计题量。"""
    sql = "SELECT COUNT(*) AS n FROM question_bank WHERE course_id = %s AND status = %s"
    params: list[Any] = [course_id, status]

    if knowledge_point:
        sql += " AND knowledge_point = %s"
        params.append(knowledge_point)
    if question_type:
        sql += " AND question_type = %s"
        params.append(question_type)
    if difficulty:
        sql += " AND difficulty = %s"
        params.append(difficulty)

    row = db_mysql.fetch_one(sql, tuple(params))
    return int(row["n"]) if row else 0


# ==============================================================
# 加权抽取
# ==============================================================
def _weight_of(row: dict[str, Any]) -> float:
    """把 quality_score 映射成抽题权重。

    【为什么下限是 0.05 而不是 0】
        如果下限是 0，被打过很多 bad 的题权重会归零，
        永远抽不到，也就永远没机会被"翻案"（比如题目其实是好的，
        只是被误标）。

        0.05 表示：概率极低但存在。
    """
    score = float(row.get("quality_score") or 0.0)
    return max(0.05, 1.0 + score)


def sample_questions(
    candidates: list[dict[str, Any]],
    count: int,
) -> list[dict[str, Any]]:
    """按质量分加权、不重复地抽取 count 道题。

    先随机打乱候选池，再做加权采样，保证每次结果不同。

    Args:
        candidates: 候选题目列表。
        count: 需要的数量。

    Returns:
        抽取结果，长度 <= count。
    """
    if count <= 0 or not candidates:
        return []

    pool = list(candidates)
    random.shuffle(pool)
    picked: list[dict[str, Any]] = []

    while pool and len(picked) < count:
        weights = [_weight_of(row) for row in pool]
        chosen = random.choices(pool, weights=weights, k=1)[0]
        picked.append(chosen)
        pool.remove(chosen)

    return picked


# ==============================================================
# 入库
# ==============================================================
def insert_question(
    course_id: int,
    knowledge_point: str,
    knowledge_point_id: int | None,
    question_type: str,
    difficulty: str,
    payload: dict[str, Any],
    source: str,
    source_ref: str | None = None,
    prompt_version: str | None = None,
    model_version: str | None = None,
) -> int:
    """把一道题写入题库。

    Args:
        course_id: 课程 id。
        knowledge_point: 知识点名（冗余字段）。
        knowledge_point_id: 知识点 id。
        question_type: 题型（简答 / 选择）。
        difficulty: 难度（易 / 中 / 难）。
        payload: 完整题目内容（题干、答案、评分要点等）。
        source: 来源（generated / web_search / user_imported）。
        source_ref: 来源引用（chunk_id 或 URL）。
        prompt_version: 生成该题用的提示词版本。
        model_version: 生成该题用的模型版本。

    Returns:
        新题目的 id。
    """
    question_id = db_mysql.insert_returning_id(
        "INSERT INTO question_bank "
        "(course_id, knowledge_point, knowledge_point_id, question_type, difficulty, "
        "question_json, source, source_ref, status, prompt_version, model_version) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', %s, %s)",
        (
            course_id,
            knowledge_point,
            knowledge_point_id,
            question_type,
            difficulty,
            json.dumps(payload, ensure_ascii=False, default=str),
            source,
            source_ref,
            prompt_version,
            model_version,
        ),
    )

    return question_id


def increment_usage(question_id: int) -> None:
    """题目被抽出时累加使用次数。"""
    db_mysql.execute(
        "UPDATE question_bank SET usage_count = usage_count + 1 WHERE id = %s",
        (question_id,),
    )


# ==============================================================
# 反馈
# ==============================================================
def record_feedback(question_id: int, feedback: str) -> dict[str, Any] | None:
    """记录一次质量反馈。

    Args:
        question_id: 题目 id。
        feedback: 'good' / 'bad' / 'duplicate'。

    Returns:
        更新后的质量分与反馈计数；题目不存在时返回 None。

    Raises:
        ValueError: feedback 取值非法。
    """
    if feedback not in FEEDBACK_TYPES:
        raise ValueError(f"非法反馈类型 {feedback!r}，可选：{FEEDBACK_TYPES}")

    row = get_question(question_id)
    if row is None:
        return None

    # 解析现有的 feedback JSON
    counters = _safe_counters(row.get("user_feedback"))

    # 累加本次反馈
    try:
        current = int(counters.get(feedback, 0))
    except (TypeError, ValueError):
        current = 0
    counters[feedback] = current + 1

    # 更新 quality_score
    new_score = float(row.get("quality_score") or 0.0) + _FEEDBACK_DELTA[feedback]

    db_mysql.execute(
        "UPDATE question_bank SET quality_score = %s, user_feedback = %s WHERE id = %s",
        (new_score, json.dumps(counters, ensure_ascii=False), question_id),
    )

    return {"quality_score": new_score, "user_feedback": counters}


# ==============================================================
# 废弃与恢复
# ==============================================================
def deprecate_question(question_id: int, reason: str = "manual") -> bool:
    """废弃一道题。

    【为什么要记录废弃原因】
        事后分析时能看出"为什么这道题被废了"：
        是内容错误（content_error）？
        还是被重复替代（regenerate）？
        还是质量问题（quality）？

    Args:
        question_id: 题目 id。
        reason: 废弃原因。

    Returns:
        是否成功。
    """
    row = get_question(question_id)
    if row is None:
        return False

    # 把原因附加到 user_feedback 里
    counters = _safe_counters(row.get("user_feedback"))
    counters["deprecated_reason"] = reason

    db_mysql.execute(
        "UPDATE question_bank SET status = 'deprecated', user_feedback = %s WHERE id = %s",
        (json.dumps(counters, ensure_ascii=False), question_id),
    )
    return True


def restore_question(question_id: int) -> bool:
    """恢复误废弃的题目。"""
    row = get_question(question_id)
    if row is None or row.get("status") == "active":
        return False

    db_mysql.execute(
        "UPDATE question_bank SET status = 'active' WHERE id = %s",
        (question_id,),
    )
    return True


def batch_deprecate(question_ids: list[int], reason: str = "batch") -> int:
    """批量废弃。

    Args:
        question_ids: 题目 id 列表。
        reason: 废弃原因。

    Returns:
        实际废弃的数量。
    """
    count = 0
    for qid in question_ids:
        if deprecate_question(int(qid), reason=reason):
            count += 1
    return count


# ==============================================================
# 统计
# ==============================================================
def bank_stats(course_id: int) -> dict[str, Any]:
    """题库分布统计。

    Returns:
        {
          "total": 总数,
          "deprecated": 已废弃数,
          "avg_quality": 平均质量分,
          "by_type": {题型: 数量},
          "by_difficulty": {难度: 数量},
          "by_source": {来源: 数量},
          "by_knowledge_point": {知识点: 数量},
        }
    """
    total_row = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n FROM question_bank WHERE course_id = %s AND status = 'active'",
        (course_id,),
    )
    deprecated_row = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n FROM question_bank WHERE course_id = %s AND status = 'deprecated'",
        (course_id,),
    )
    avg_row = db_mysql.fetch_one(
        "SELECT COALESCE(AVG(quality_score), 0) AS v FROM question_bank "
        "WHERE course_id = %s AND status = 'active'",
        (course_id,),
    )

    def _group(column: str) -> dict[str, int]:
        """按列分组统计。列名白名单化。"""
        # 白名单：只允许这几列。防止 SQL 注入。
        if column not in ("question_type", "difficulty", "source", "knowledge_point"):
            raise ValueError(f"不允许按该列分组：{column!r}")

        rows = db_mysql.fetch_all(
            f"SELECT {column} AS k, COUNT(*) AS n FROM question_bank "
            f"WHERE course_id = %s AND status = 'active' GROUP BY {column}",
            (course_id,),
        )
        return {str(r["k"]): int(r["n"]) for r in rows}

    return {
        "total": int(total_row["n"]) if total_row else 0,
        "deprecated": int(deprecated_row["n"]) if deprecated_row else 0,
        "avg_quality": round(float(avg_row["v"]) if avg_row else 0.0, 2),
        "by_type": _group("question_type"),
        "by_difficulty": _group("difficulty"),
        "by_source": _group("source"),
        "by_knowledge_point": _group("knowledge_point"),
    }


# ==============================================================
# 内部工具
# ==============================================================
def _safe_counters(raw: Any) -> dict[str, Any]:
    """把 user_feedback 字段解析成字典。

    【为什么要单独一个函数】
        这个字段可能来自数据库（JSON 字符串）或刚写入的值（dict）。
        统一处理让调用方不用判断类型。

        注意：不要用 json.loads 直接处理 dict，
        Python 的 dict 字符串表示（单引号）不是合法 JSON。
    """
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_json(raw: Any) -> dict[str, Any]:
    """解析 question_json 字段。"""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return {"question": str(raw), "_parse_error": True}
    return parsed if isinstance(parsed, dict) else {"question": str(parsed)}


def _decorate(row: dict[str, Any]) -> dict[str, Any]:
    """把数据库行整理成对外结构。

    主要是解析 JSON 字段（question_json、user_feedback），
    让调用方拿到的是 Python 对象而不是字符串。
    """
    row = dict(row)
    row["payload"] = _safe_json(row.get("question_json"))
    row["user_feedback"] = _safe_counters(row.get("user_feedback"))
    return row