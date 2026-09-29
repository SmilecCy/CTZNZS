# -*- coding: utf-8 -*-
"""Redis 客户端。

【为什么单独一个模块】
    与 db_mysql.py 同理：连接只建一次，配置集中一处。

【为什么从 config 读，不自己 os.getenv】
    与 db_mysql.py 同一个坑：
      db_redis 直接用 os.getenv("REDIS_PORT", "6379")，
      但它不 import app.config。
      .env 的加载发生在 config 顶层（load_dotenv）。
      于是独立 import db_redis 时，.env 没加载，
      端口用了默认 6379，而实际服务在 9991 上。

    现在改成从 config 读常量，依赖关系显式。

【Redis 在本项目里的角色】
    只存**可重建**的数据。任何 Redis 数据的丢失，
    都必须能从 MySQL 重建。这是硬约束。

    存什么：
      - 课程列表缓存（MySQL 里也有，缓存只是加速）
      - 题目列表缓存（同上）
      - 作答草稿（丢了学生重做，不致命）
      - JWT 黑名单（丢了登出的 token 还能用，但过期后自然失效）
"""

from __future__ import annotations

import redis

from app.config import (
    REDIS_DB,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
)


# ==============================================================
# 客户端：进程级单例
# ==============================================================
_CLIENT: redis.Redis | None = None


def _build_client() -> redis.Redis:
    """构造 Redis 客户端。

    【为什么用连接池】
        redis-py 的 Redis 类自带连接池（内部维护），
        所以这里不需要像 MySQL 那样手动建 PooledDB。
    """
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        # 空字符串要转 None——redis-py 把空串当成"要密码"，会报错。
        password=REDIS_PASSWORD or None,
        db=REDIS_DB,
        # 解码为字符串，不返回 bytes。
        # 否则每次读出来都要 .decode()，很烦。
        decode_responses=True,
        # 连接超时。Redis 连不上时快速失败，不卡住整个请求。
        socket_connect_timeout=3,
        socket_timeout=3,
        # 健康检查间隔（秒）。定期 ping，防止拿到死连接。
        health_check_interval=30,
    )


def get_client() -> redis.Redis:
    """获取（惰性创建）Redis 客户端。"""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = _build_client()
    return _CLIENT


# ==============================================================
# 对外接口
# ==============================================================
def health_check() -> dict:
    """健康检查：确认 Redis 能连上。

    与 db_mysql.health_check 同理，**永不抛异常**。

    Returns:
        {"ok": True, "version": "7.x.x"} 或 {"ok": False, "error": "..."}
    """
    try:
        client = get_client()
        info = client.info("server")
        return {"ok": True, "version": info.get("redis_version", "unknown")}
    except Exception as exc:  # noqa: BLE001 - 见 docstring
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def ping() -> bool:
    """简单 ping，返回 True / False。

    比 health_check 轻量，适合高频调用。
    """
    try:
        return bool(get_client().ping())
    except Exception:  # noqa: BLE001
        return False


def reset_client() -> None:
    """丢弃缓存的客户端。

    【什么时候用】
        客户端进入坏状态时（比如 Redis 重启后连接失效），
        清掉缓存让下次调用重建。
    """
    global _CLIENT
    _CLIENT = None