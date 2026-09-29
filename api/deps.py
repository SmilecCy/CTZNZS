# -*- coding: utf-8 -*-
"""依赖注入：FastAPI 的 Depends() 用的公共依赖。

【依赖注入是什么】

    FastAPI 的一个特性：路由函数声明它"需要什么"，
    FastAPI 自动准备好传进去。

    例如：
        @router.get("/courses")
        def list_courses(db = Depends(get_db)):
            # db 已经被 FastAPI 准备好

    好处：路由函数不用管"怎么连数据库"、"怎么鉴权"，
    只关心自己的业务。

【这个模块提供什么】

    1. get_current_user —— 从 JWT 里取出当前登录用户
    2. require_admin —— 要求当前用户是管理员
    3. require_user —— 要求当前用户是学生
    4. get_db —— 获取数据库连接（暂时用 context manager，后面按需扩展）

【为什么认证要放这里】

    认证是"横切关注点"——几乎所有需要登录的接口都要做。
    放在这里，路由函数只需声明"我需要当前用户"。
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, HTTPException, status

from app.auth import auth_service, user_service


# ==============================================================
# 自定义异常
# ==============================================================
def _unauthorized(message: str = "未登录或登录已过期") -> HTTPException:
    """401 未授权的统一构造。

    401 = 未登录
    403 = 已登录但没权限

    这两个状态码别混，前端要按它们做不同处理：
      401 → 跳登录页
      403 → 提示"无权限"
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHORIZED", "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(message: str = "没有权限执行此操作") -> HTTPException:
    """403 禁止的统一构造。"""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "FORBIDDEN", "message": message},
    )


# ==============================================================
# 从请求头取 token
# ==============================================================
def _extract_token(authorization: str | None) -> str:
    """从 Authorization 头里抠出 token。

    头部格式：Authorization: Bearer eyJhbGciOi...

    Args:
        authorization: 请求头的值。

    Returns:
        token 字符串。

    Raises:
        HTTPException: 401，头部缺失或格式不对。
    """
    if not authorization:
        raise _unauthorized("缺少 Authorization 请求头")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise _unauthorized("Authorization 头格式应为：Bearer <token>")

    return parts[1]


# ==============================================================
# 当前用户
# ==============================================================
async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """从 JWT 里解析出当前登录用户。

    【为什么是 async】
        FastAPI 支持 async 路由，依赖也统一用 async。
        目前函数体是同步的（没 await），但保留 async 以便将来扩展。

    Args:
        authorization: FastAPI 自动从请求头里提取。

    Returns:
        用户字典：
        {
          "id": 1,
          "username": "xxx",
          "role": "user" 或 "admin",
          "display_name": "xxx",
        }

    Raises:
        HTTPException: 401，token 无效或用户不存在。
    """
    token = _extract_token(authorization)

    try:
        payload = auth_service.decode_token(token)
    except auth_service.TokenError as exc:
        raise _unauthorized(str(exc)) from exc

    user_id = payload.get("sub")
    role = payload.get("role") or "user"

    if not user_id:
        raise _unauthorized("Token 里缺少用户 id")

    # 查数据库确认用户还在（防止已删除的用户持有效 token 访问）
    if role == "admin":
        user = user_service.get_admin_by_id(int(user_id))
    else:
        user = user_service.get_user_by_id(int(user_id))

    if user is None:
        raise _unauthorized("用户不存在或已被禁用")

    if not user.get("is_active"):
        raise _unauthorized("账号已被禁用")

    # 组装统一的返回结构
    return {
        "id": int(user["id"]),
        "username": user["username"],
        "role": role,
        "display_name": user.get("display_name") or user["username"],
    }


async def require_user(
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """要求当前是学生身份。

    【用途】/api/user/* 下的所有接口都用它。

    Raises:
        HTTPException: 403，当前不是学生。
    """
    if current["role"] != "user":
        raise _forbidden("此接口仅限学生使用")
    return current


async def require_admin(
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """要求当前是管理员。

    【用途】/api/admin/* 下的所有接口都用它。

    Raises:
        HTTPException: 403，当前不是管理员。
    """
    if current["role"] != "admin":
        raise _forbidden("此接口仅限管理员使用")
    return current