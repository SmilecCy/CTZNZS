# -*- coding: utf-8 -*-
"""认证服务：密码哈希、JWT 签发与校验。

【这个模块做什么】

    1. 密码哈希（bcrypt）
    2. 密码校验
    3. JWT 签发
    4. JWT 解析与校验
    5. JWT 黑名单（登出用）

【为什么用 bcrypt 而不是 MD5/SHA256】

    MD5/SHA256 是"快速哈希"，设计目标是"算得快"。
    而密码哈希需要"算得慢"——因为攻击者拿到哈希后可以暴力破解，
    算得越快，破解越快。

    bcrypt 故意设计成慢（默认迭代 12 次，耗时约 100ms），
    让暴力破解变得不划算。同时它自动加盐（salt），
    同一个密码每次哈希结果都不同。

【为什么用 JWT 而不是 session】

    JWT 是无状态令牌：服务器不需要保存会话，用户拿 token 自证身份。
    适合前后端分离（React + FastAPI）的场景。

    代价：登出不能真正让 token 失效（因为服务器不存）。
    所以需要一个黑名单（存在 Redis 里）来标记"已登出的 token"。
    等 token 自然过期后，黑名单记录会被清理。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET
from app.database import cache


def hash_password(plain: str) -> str:
    """把明文密码哈希。

    Args:
        plain: 明文密码。

    Returns:
        bcrypt 哈希字符串（约 60 字符）。

    Raises:
        ValueError: 密码为空。
    """
    if not plain:
        raise ValueError("密码不能为空")
    return bcrypt.hashpw(
        plain.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码是否匹配哈希。

    Args:
        plain: 用户输入的明文密码。
        hashed: 数据库里存的哈希。

    Returns:
        True 表示匹配。
    """
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(
            plain.encode("utf-8"),
            hashed.encode("utf-8"),
        )
    except Exception:  # noqa: BLE001 - 哈希格式不对时不该崩
        return False


# ==============================================================
# JWT 签发
# ==============================================================
def create_token(
    user_id: int,
    username: str,
    role: str,
    expire_minutes: int | None = None,
) -> tuple[str, str]:
    """签发 JWT。

    Args:
        user_id: 用户 id。
        username: 用户名。
        role: 角色。"user"（学生）或 "admin"（管理员）。
        expire_minutes: 有效期（分钟）。None 时用配置默认值。

    Returns:
        ``(token, jti)``。
        token 是签好的 JWT 字符串。
        jti 是 JWT 的唯一 id，登出时需要用它加入黑名单。
    """
    minutes = expire_minutes if expire_minutes is not None else JWT_EXPIRE_MINUTES
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=minutes)

    # jti（JWT ID）是 token 的唯一标识。
    # 【为什么要它】登出时不知道 token 字符串本身（前端也没传），
    # 但知道 jti，就能用它标记"这个 token 已失效"。
    jti = str(uuid.uuid4())

    payload: dict[str, Any] = {
        "sub": str(user_id),   # subject，标识用户
        "username": username,
        "role": role,
        "jti": jti,
        "iat": int(now.timestamp()),      # 签发时间
        "exp": int(expire.timestamp()),   # 过期时间
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, jti


# ==============================================================
# JWT 解析与校验
# ==============================================================
class TokenError(RuntimeError):
    """Token 无效或过期时抛出。"""


def decode_token(token: str) -> dict[str, Any]:
    """解析并校验 JWT。

    【校验什么】
        1. 签名是否正确（防止伪造）
        2. 是否过期
        3. 是否在黑名单里（登出的 token）

    Args:
        token: JWT 字符串。

    Returns:
        解析后的 payload 字典。

    Raises:
        TokenError: 无效、过期或在黑名单里。
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise TokenError(f"Token 无效：{exc}") from exc

    # 检查黑名单
    jti = payload.get("jti")
    if jti and is_blacklisted(jti):
        raise TokenError("Token 已失效（已登出）")

    return payload


def get_user_id_from_token(token: str) -> int:
    """从 token 里取用户 id。

    Raises:
        TokenError: token 无效。
    """
    payload = decode_token(token)
    try:
        return int(payload["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise TokenError("Token 里没有用户 id") from exc


def get_role_from_token(token: str) -> str:
    """从 token 里取角色。"""
    payload = decode_token(token)
    return str(payload.get("role") or "user")


# ==============================================================
# 黑名单（登出用）
# ==============================================================
def add_to_blacklist(jti: str, expire_seconds: int | None = None) -> None:
    """把 jti 加入黑名单。

    【黑名单多久清理】
        token 自然过期后，黑名单记录就无意义了。
        所以 TTL 设成"token 剩余有效期"——过期后 Redis 自动删。

        如果传 expire_seconds=None，用默认的 token 有效期。
        实际使用时，调用方应该算"还剩多久过期"传进来。
    """
    ttl = expire_seconds if expire_seconds is not None else JWT_EXPIRE_MINUTES * 60
    cache.set(cache.jwt_blacklist_key(jti), {"revoked": True}, ttl=ttl)


def is_blacklisted(jti: str) -> bool:
    """检查 jti 是否在黑名单里。"""
    return cache.exists(cache.jwt_blacklist_key(jti))


# ==============================================================
# 便捷函数
# ==============================================================
def remaining_seconds(token: str) -> int:
    """算 token 还有多久过期（秒）。

    【用途】登出时把剩余时间传给 add_to_blacklist，
        让黑名单记录的 TTL 正好覆盖 token 的剩余寿命。

    Returns:
        剩余秒数。token 已过期或无效时返回 0。
    """
    try:
        payload = jwt.decode(
            token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
            options={"verify_exp": False},   # 过期也解析
        )
        exp = int(payload.get("exp") or 0)
        now = int(datetime.now(timezone.utc).timestamp())
        return max(0, exp - now)
    except Exception:  # noqa: BLE001
        return 0