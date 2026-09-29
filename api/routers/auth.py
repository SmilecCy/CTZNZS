# -*- coding: utf-8 -*-
"""认证路由：注册、登录、登出、当前用户。

【接口清单】

    POST /api/auth/register    学生注册
    POST /api/auth/login       登录（学生+管理员共用）
    POST /api/auth/logout      登出（JWT 加黑名单）
    GET  /api/auth/me          查当前登录用户

【为什么注册只给学生】

    管理员账号不开放注册。原因：
      1. 管理员权限大，泄露后果严重
      2. 管理员数量少，初始脚本建一个够用
      3. 需要新增管理员时，让现有管理员手动创建

【为什么登录不分开学生/管理员两个接口】

    登录逻辑一样（查表、验密码、签 token），
    差别只在查哪张表。用一个接口 + role 参数区分更简洁。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status

from api import deps
from api.schemas import (
    LoginRequest,
    MeResponse,
    RegisterRequest,
    SuccessResponse,
    TokenResponse,
)
from app.config import JWT_EXPIRE_MINUTES
from app.auth import auth_service, user_service


# ==============================================================
# 路由器
# ==============================================================
router = APIRouter()


# ==============================================================
# 注册
# ==============================================================
@router.post(
    "/register",
    response_model=TokenResponse,
    summary="学生注册",
    description="注册成功后直接返回 token，用户不需要再登录一次。",
)
async def register(payload: RegisterRequest) -> TokenResponse:
    """注册学生账号。

    【为什么要直接返回 token】
        注册成功后自动登录，体验更顺。
        不然用户注册完还要再输一遍密码，很烦。
    """
    try:
        user_id = user_service.register_user(
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            email=payload.email,
        )
    except user_service.UsernameExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "USERNAME_EXISTS", "message": str(exc)},
        ) from exc
    except user_service.UserError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_INPUT", "message": str(exc)},
        ) from exc

    # 签发 token
    token, _ = auth_service.create_token(user_id, payload.username, "user")

    user = user_service.get_user_by_id(user_id)

    return TokenResponse(
        access_token=token,
        expires_in=JWT_EXPIRE_MINUTES * 60,
        user={
            "id": user_id,
            "username": payload.username,
            "role": "user",
            "display_name": user.get("display_name") if user else payload.username,
        },
    )


# ==============================================================
# 登录
# ==============================================================
@router.post(
    "/login",
    response_model=TokenResponse,
    summary="登录",
    description="学生和管理员共用。通过 role 字段区分（user / admin）。",
)
async def login(payload: LoginRequest) -> TokenResponse:
    """登录。

    【返回什么】
        token + 用户信息。

    【失败为什么统一报"用户名或密码不正确"】
        不区分"用户名不存在"和"密码错"——防止攻击者枚举用户名。
        这是个常见的安全实践。
    """
    role = payload.role if payload.role in ("user", "admin") else "user"

    try:
        user = user_service.authenticate(
            username=payload.username,
            password=payload.password,
            role=role,
        )
    except user_service.InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": str(exc)},
        ) from exc
    except user_service.UserError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ACCOUNT_DISABLED", "message": str(exc)},
        ) from exc

    token, _ = auth_service.create_token(user["id"], user["username"], role)

    return TokenResponse(
        access_token=token,
        expires_in=JWT_EXPIRE_MINUTES * 60,
        user={
            "id": user["id"],
            "username": user["username"],
            "role": role,
            "display_name": user.get("display_name") or user["username"],
        },
    )


# ==============================================================
# 登出
# ==============================================================
@router.post(
    "/logout",
    response_model=SuccessResponse,
    summary="登出",
    description="把当前 token 加入黑名单，之后无法继续使用。",
)
async def logout(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> SuccessResponse:
    """登出。

    【JWT 登出的原理】
        JWT 是无状态的，服务器不保存会话。
        所以"登出"不能真的"撤销"一个 token——
        token 在过期前一直有效。

        我们用一个折衷方案：把 token 的 jti（唯一 id）加入 Redis 黑名单。
        之后每次校验 token 时都查一下黑名单。

        代价：每次请求多一次 Redis 查询。
        好处：能实现登出。
    """
    if not authorization:
        # 没登录也算登出成功（幂等）
        return SuccessResponse(message="已登出")

    # 从 Authorization 头里取 token
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return SuccessResponse(message="已登出")

    token = parts[1]

    try:
        # 解析出 jti（不解码就不知道要加入黑名单的是哪个）
        payload = auth_service.decode_token(token)
        jti = payload.get("jti")
        if jti:
            # 算出 token 还有多久过期
            remaining = auth_service.remaining_seconds(token)
            # 加入黑名单，TTL = 剩余时间
            auth_service.add_to_blacklist(jti, expire_seconds=remaining)
    except auth_service.TokenError:
        # token 本来就无效，也算登出成功
        pass

    return SuccessResponse(message="已登出")


# ==============================================================
# 当前用户
# ==============================================================
@router.get(
    "/me",
    response_model=MeResponse,
    summary="当前登录用户",
    description='前端可以用它判断"我登录了吗"、"我是谁"。',
)
async def get_me(
    current: dict = Depends(deps.get_current_user),
) -> MeResponse:
    """查当前登录用户。"""
    return MeResponse(
        id=current["id"],
        username=current["username"],
        role=current["role"],
        display_name=current["display_name"],
    )