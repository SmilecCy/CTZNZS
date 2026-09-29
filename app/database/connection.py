# -*- coding: utf-8 -*-
"""MySQL 连接池。

【为什么单独一个模块，而不是散在各 service 里】

    所有 service 都从这一个地方拿连接，好处：
      1. 连接池只建一次，不重复创建
      2. 连接配置集中在一处（从 config 读，不自己 os.getenv）
      3. 将来要换驱动（pymysql → asyncmy）只改这一个文件

【为什么从 config 读，不自己 os.getenv】

    这是踩过的坑：
      db_mysql 直接用 os.getenv("MYSQL_PORT", "3306")，
      但它不 import app.config。
      而 .env 的加载发生在 app.config 的顶层（load_dotenv）。
      于是 db_mysql 独立被 import 时，.env 根本没加载，
      端口用了默认值 3306，而实际服务在 9999 上——
      报错是 WinError 10061，看起来像"没启动 MySQL"，
      实际是读错了端口，非常难排查。

    现在改成从 config 读常量：
      · 加载时机由 config 保证
      · 依赖关系显式
      · 一处配置，全项目一致
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import pymysql
from dbutils.pooled_db import PooledDB
from pymysql.cursors import DictCursor

from app.config import (
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_POOL_SIZE,
    MYSQL_PORT,
    MYSQL_USER,
)


# ==============================================================
# 连接池：进程级单例
# ==============================================================
_POOL: PooledDB | None = None


def _build_pool() -> PooledDB:
    """构造连接池。只在第一次调用时执行。"""
    return PooledDB(
        creator=pymysql,
        mincached=2,
        maxcached=MYSQL_POOL_SIZE,
        maxconnections=MYSQL_POOL_SIZE,
        blocking=True,
        # 从池里取连接时先 ping 一下。
        # MySQL 会主动断开空闲连接（默认 8 小时），
        # 不 ping 的话拿到的是死连接。
        #   0 = 不检测
        #   1 = 每次取连接时 ping
        #   2 = 每次取连接时重建
        #   7 = 每次取连接时 ping，空闲超过 7 秒则重建
        ping=1,
        # ---------- 连接参数 ----------
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
        connect_timeout=5,
    )


def _get_pool() -> PooledDB:
    """获取（惰性创建）连接池。"""
    global _POOL
    if _POOL is None:
        _POOL = _build_pool()
    return _POOL


# ==============================================================
# 对外接口
# ==============================================================
@contextmanager
def connection() -> Iterator[pymysql.connections.Connection]:
    """从池里取一个连接，用完归还。

    用法::

        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT ...")
                rows = cur.fetchall()
        # 退出 with 时自动 commit
    """
    pool = _get_pool()
    conn = pool.connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute(sql: str, params: tuple | dict | None = None) -> int:
    """执行一条写操作（INSERT / UPDATE / DELETE），返回影响行数。"""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.rowcount


def insert_returning_id(sql: str, params: tuple | dict | None = None) -> int:
    """执行 INSERT 并返回新插入行的自增 id。"""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return int(cur.lastrowid or 0)


def fetch_one(sql: str, params: tuple | dict | None = None) -> dict[str, Any] | None:
    """查一行，返回字典。查不到返回 None。"""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()  # type: ignore[return-value]


def fetch_all(sql: str, params: tuple | dict | None = None) -> list[dict[str, Any]]:
    """查多行，返回字典列表。查不到返回空列表。"""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return list(cur.fetchall())  # type: ignore[arg-type]


def health_check() -> dict:
    """健康检查。**永不抛异常**。"""
    try:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION() AS v")
                row = cur.fetchone()
        return {"ok": True, "version": (row or {}).get("v", "unknown")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def reset_pool() -> None:
    """丢弃缓存的连接池。"""
    global _POOL
    _POOL = None