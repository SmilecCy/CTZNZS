# -*- coding: utf-8 -*-
"""缓存原语：读写、失效、草稿。

【设计原则：写时删缓存，不更新缓存】

    数据变了的时候，有两种做法：
      A. 更新缓存（把新值写进去）
      B. 删除缓存（让下次读取时重建）

    我们选 B。原因：
      1. 更新缓存要保证"缓存里的值"和"数据库里的值"完全一致，
         一旦某处漏更新就会长期不一致（脏数据）。
      2. 删除缓存更简单：删了就删了，下次读会从数据库重建。
      3. "删缓存失败"比"更新缓存失败"后果轻——前者只是多查一次数据库，
         后者是长期错误。

【缓存必须带 TTL】

    禁止无 TTL 的永久缓存。原因：
      - 忘了删缓存 → 永久脏数据
      - 内存泄漏 → Redis 被撑爆

    本项目所有缓存 TTL 最长 24 小时（作答草稿）。
"""

from __future__ import annotations

import json
from typing import Any

from app.database import redis as db_redis


# ==============================================================
# 内部工具
# ==============================================================
def _safe_json_dumps(value: Any) -> str:
    """把任意值序列化成 JSON 字符串。

    【为什么要单独封一个函数】
        MySQL 返回的行里，时间字段是 Python 的 datetime 对象。
        json.dumps 默认不认识 datetime，会抛 TypeError。
        加 default=str 后，datetime 会被转成 "2026-09-22 10:30:45"。

        Decimal 类型同理（DECIMAL 字段会返回 Decimal 对象）。

    【为什么用 default=str 而不是自定义 encoder】
        default=str 简单粗暴，能处理几乎所有不可序列化的类型。
        自定义 encoder 要写一堆 isinstance 判断，还得维护。
        缓存是"可重建"的数据，精度损失无所谓——时间精确到秒足够。

    Args:
        value: 要序列化的值。

    Returns:
        JSON 字符串。
    """
    return json.dumps(value, ensure_ascii=False, default=str)


# ==============================================================
# 基础读写
# ==============================================================
def set(key: str, value: Any, ttl: int = 600) -> None:
    """写缓存。

    Args:
        key: 缓存键。
        value: 值。会被 JSON 序列化，所以可以是 dict / list / str / int。
        ttl: 过期时间（秒）。默认 600 秒（10 分钟）。

    【为什么统一用 JSON 序列化】
        统一之后，读的时候不用担心"这个值是字符串还是数字"。
        Redis 存的是字符串，JSON 是最通用的中间格式。
    """
    client = db_redis.get_client()
    payload = _safe_json_dumps(value)
    client.setex(key, ttl, payload)


def get(key: str, default: Any = None) -> Any:
    """读缓存。

    Args:
        key: 缓存键。
        default: 缓存不存在或反序列化失败时返回的默认值。

    Returns:
        缓存的值；不存在时返回 default。
    """
    client = db_redis.get_client()
    raw = client.get(key)
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # 【为什么容错而不是抛异常】
        # 缓存里的脏数据不该让整个请求崩掉。
        # 反序列化失败就当缓存不存在，让调用方去数据库重建。
        return default


def delete(*keys: str) -> int:
    """删除一个或多个键。

    Returns:
        实际删除的键数。
    """
    if not keys:
        return 0
    return int(db_redis.get_client().delete(*keys))


def delete_pattern(pattern: str) -> int:
    """按模式批量删除。

    【为什么要小心用】
        KEYS 命令会阻塞 Redis（它要遍历整个键空间）。
        生产环境应该用 SCAN，但个人项目数据量小，KEYS 够用。

        如果将来键数上万，改成 SCAN 循环。

    Args:
        pattern: 匹配模式。例如 "q:bank:1:*"。

    Returns:
        删除的键数。
    """
    client = db_redis.get_client()
    keys = list(client.scan_iter(match=pattern, count=100))
    if not keys:
        return 0
    return int(client.delete(*keys))


def exists(key: str) -> bool:
    """检查键是否存在。"""
    return bool(db_redis.get_client().exists(key))


# ==============================================================
# 业务专用：缓存键构造
# ==============================================================
# 【为什么集中在这里构造键】
#   如果散在各 service 里，很容易出现 "q:bank:1:xxx" 和 "qbank:1:xxx"
#   两种拼法。集中之后，改名只需改一处，失效时也不会漏。
def course_list_key() -> str:
    """课程列表缓存键。"""
    return "course:list"


def knowledge_points_key(course_id: int) -> str:
    """某课程的知识点列表缓存键。"""
    return f"kp:course:{course_id}"


def question_bank_key(
    course_id: int,
    knowledge_point: str,
    question_type: str,
    difficulty: str,
) -> str:
    """题库查询缓存键。

    四个维度拼成的键，对应出题请求的四个参数。
    """
    # 知识点名可能含特殊字符，简单替换掉冒号避免键冲突
    kp = knowledge_point.replace(":", "_")
    return f"q:bank:{course_id}:{kp}:{question_type}:{difficulty}"


def draft_key(user_id: int, paper_id: int | str) -> str:
    """作答草稿缓存键。"""
    return f"draft:{user_id}:{paper_id}"


def jwt_blacklist_key(jti: str) -> str:
    """JWT 黑名单缓存键。"""
    return f"session:blacklist:{jti}"


def rate_limit_key(user_id: int, minute: str) -> str:
    """限流计数键。"""
    return f"rate:{user_id}:{minute}"


# ==============================================================
# 业务专用：失效
# ==============================================================
def invalidate_course_list() -> None:
    """课程列表变化时调用（增、删、改、合并）。"""
    delete(course_list_key())


def invalidate_knowledge_points(course_id: int) -> None:
    """知识点变化时调用。"""
    delete(knowledge_points_key(course_id))


def invalidate_question_bank(course_id: int) -> None:
    """题库变化时调用（新增、废弃、恢复、反馈）。

    【为什么要按模式删】
        题库缓存是按"课程+知识点+题型+难度"四维键存的，
        一道题的变化可能影响多个键。全删掉最安全。
    """
    delete_pattern(f"q:bank:{course_id}:*")