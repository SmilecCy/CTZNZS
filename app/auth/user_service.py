# -*- coding: utf-8 -*-
"""用户服务：学生账号与管理员账号的 CRUD。

【这个模块做什么】

    1. 学生账号：注册、查、改、禁用
    2. 管理员账号：查、改密码、改显示名
    3. 登录校验（学生+管理员共用一个入口）

【为什么学生和管理员分开】

    权限模型不同：
      - 学生：只能看自己的数据
      - 管理员：能看全部

    分开表（users / admin_users）从物理上隔离，
    避免"学生把自己改成管理员"这类漏洞。
"""

from __future__ import annotations

from typing import Any

from app.auth import auth_service
from app.database import connection as db_mysql


# ==============================================================
# 异常
# ==============================================================
class UserError(RuntimeError):
    """用户操作的统一异常基类。"""


class UserNotFoundError(UserError):
    """用户不存在。"""


class UsernameExistsError(UserError):
    """用户名已存在。"""


class InvalidCredentialsError(UserError):
    """用户名或密码不对。

    【为什么叫 InvalidCredentials 而不是 PasswordError】
        出于安全考虑，登录失败时不告诉用户"是用户名错还是密码错"——
        否则攻击者能据此枚举出哪些用户名存在。
        统一报"用户名或密码不对"。
    """


# ==============================================================
# 学生账号
# ==============================================================
def register_user(
    username: str,
    password: str,
    display_name: str = "",
    email: str = "",
) -> int:
    """注册学生账号。

    Args:
        username: 用户名（唯一）。
        password: 明文密码（会被哈希）。
        display_name: 显示名。
        email: 邮箱。

    Returns:
        新用户 id。

    Raises:
        UserError: 参数不合法。
        UsernameExistsError: 用户名已存在。
    """
    username = (username or "").strip()
    if not username:
        raise UserError("用户名不能为空")
    if len(username) < 3:
        raise UserError("用户名至少 3 个字符")
    if len(username) > 50:
        raise UserError("用户名最多 50 个字符")

    if not password or len(password) < 6:
        raise UserError("密码至少 6 个字符")

    # 查重
    existing = get_user_by_username(username)
    if existing is not None:
        raise UsernameExistsError(f"用户名「{username}」已被占用")

    password_hash = auth_service.hash_password(password)

    return db_mysql.insert_returning_id(
        "INSERT INTO users (username, password_hash, display_name, email) "
        "VALUES (%s, %s, %s, %s)",
        (username, password_hash, display_name or username, email),
    )


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    """按 id 查学生。"""
    return db_mysql.fetch_one(
        "SELECT id, username, display_name, email, is_active, "
        "created_at, last_login_at "
        "FROM users WHERE id = %s",
        (user_id,),
    )


def get_user_by_username(username: str) -> dict[str, Any] | None:
    """按用户名查学生（含密码哈希，登录用）。"""
    return db_mysql.fetch_one(
        "SELECT * FROM users WHERE username = %s",
        ((username or "").strip(),),
    )


def update_user(
    user_id: int,
    display_name: str | None = None,
    email: str | None = None,
) -> bool:
    """改学生信息。

    Returns:
        是否成功。

    Raises:
        UserNotFoundError: 用户不存在。
    """
    user = get_user_by_id(user_id)
    if user is None:
        raise UserNotFoundError(f"用户 id={user_id} 不存在")

    sets: list[str] = []
    params: list[Any] = []

    if display_name is not None:
        sets.append("display_name = %s")
        params.append(display_name.strip())
    if email is not None:
        sets.append("email = %s")
        params.append(email.strip())

    if not sets:
        return True

    params.append(user_id)
    db_mysql.execute(
        f"UPDATE users SET {', '.join(sets)} WHERE id = %s",
        tuple(params),
    )
    return True


def change_user_password(user_id: int, old_password: str, new_password: str) -> bool:
    """改学生密码（要验证旧密码）。

    Raises:
        UserNotFoundError: 用户不存在。
        InvalidCredentialsError: 旧密码不对。
        UserError: 新密码不合法。
    """
    user = get_user_by_username_by_id(user_id)
    if user is None:
        raise UserNotFoundError(f"用户 id={user_id} 不存在")

    if not auth_service.verify_password(old_password, user["password_hash"]):
        raise InvalidCredentialsError("原密码不正确")

    if not new_password or len(new_password) < 6:
        raise UserError("新密码至少 6 个字符")

    new_hash = auth_service.hash_password(new_password)
    db_mysql.execute(
        "UPDATE users SET password_hash = %s WHERE id = %s",
        (new_hash, user_id),
    )
    return True


def get_user_by_username_by_id(user_id: int) -> dict[str, Any] | None:
    """按 id 查学生（含密码哈希）。"""
    return db_mysql.fetch_one(
        "SELECT * FROM users WHERE id = %s",
        (user_id,),
    )


def disable_user(user_id: int) -> bool:
    """禁用学生账号（软删除）。

    Returns:
        是否成功。
    """
    affected = db_mysql.execute(
        "UPDATE users SET is_active = 0 WHERE id = %s",
        (user_id,),
    )
    return affected > 0


def list_users(limit: int = 100) -> list[dict[str, Any]]:
    """列出所有学生。"""
    return db_mysql.fetch_all(
        "SELECT id, username, display_name, email, is_active, created_at, last_login_at "
        "FROM users ORDER BY id DESC LIMIT %s",
        (int(limit),),
    )


# ==============================================================
# 管理员账号
# ==============================================================
def get_admin_by_username(username: str) -> dict[str, Any] | None:
    """按用户名查管理员（含密码哈希）。"""
    return db_mysql.fetch_one(
        "SELECT * FROM admin_users WHERE username = %s",
        ((username or "").strip(),),
    )


def get_admin_by_id(admin_id: int) -> dict[str, Any] | None:
    """按 id 查管理员。"""
    return db_mysql.fetch_one(
        "SELECT id, username, display_name, is_active, must_change_password, "
        "created_at, last_login_at "
        "FROM admin_users WHERE id = %s",
        (admin_id,),
    )


def change_admin_password(admin_id: int, old_password: str, new_password: str) -> bool:
    """改管理员密码。

    【与改学生密码的区别】
        改完之后 must_change_password 会被置 0。
        这个标记是"初始账号强制改密"用的——
        初始管理员账号的 must_change_password 是 1，改过一次后变 0。
    """
    admin = db_mysql.fetch_one(
        "SELECT * FROM admin_users WHERE id = %s",
        (admin_id,),
    )
    if admin is None:
        raise UserNotFoundError(f"管理员 id={admin_id} 不存在")

    if not auth_service.verify_password(old_password, admin["password_hash"]):
        raise InvalidCredentialsError("原密码不正确")

    if not new_password or len(new_password) < 6:
        raise UserError("新密码至少 6 个字符")

    new_hash = auth_service.hash_password(new_password)
    db_mysql.execute(
        "UPDATE admin_users SET password_hash = %s, must_change_password = 0 WHERE id = %s",
        (new_hash, admin_id),
    )
    return True


# ==============================================================
# 统一登录
# ==============================================================
def authenticate(username: str, password: str, role: str = "user") -> dict[str, Any]:
    """统一登录入口。

    Args:
        username: 用户名。
        password: 明文密码。
        role: "user" 或 "admin"。

    Returns:
        登录成功的用户信息（不含密码哈希）。

    Raises:
        InvalidCredentialsError: 用户名或密码错。
        UserError: 账号被禁用。
    """
    if role == "admin":
        user = get_admin_by_username(username)
        table = "admin_users"
    else:
        user = get_user_by_username(username)
        table = "users"

    if user is None:
        # 统一报错，不区分"用户名不存在"和"密码错"
        raise InvalidCredentialsError("用户名或密码不正确")

    if not auth_service.verify_password(password, user["password_hash"]):
        raise InvalidCredentialsError("用户名或密码不正确")

    if not user.get("is_active"):
        raise UserError("账号已被禁用，请联系管理员")

    # 更新最近登录时间
    db_mysql.execute(
        f"UPDATE {table} SET last_login_at = CURRENT_TIMESTAMP WHERE id = %s",
        (user["id"],),
    )

    # 去掉敏感字段
    result = dict(user)
    result.pop("password_hash", None)
    return result