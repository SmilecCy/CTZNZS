# -*- coding: utf-8 -*-
"""阶段四验证脚本：FastAPI 接口层。

用法::

    # 先启动服务（另开一个 PowerShell）
    python scripts/run_api.py

    # 再跑验证脚本
    python scripts/verify_stage4.py

【这个脚本做什么】

    用 httpx 调真实的 HTTP 接口，验证：
      1. /health 通
      2. 学生注册
      3. 学生登录
      4. 查课程列表（要登录）
      5. 未登录访问 /api/user/courses → 401
      6. 学生访问 /api/admin/* → 403
      7. 管理员登录
      8. 管理员访问后台接口 → 通过
      9. 登出后 token 失效
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import httpx  # noqa: E402


# ==============================================================
# 配置
# ==============================================================
BASE_URL = "http://localhost:8000"


# ==============================================================
# 辅助
# ==============================================================
def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _section(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


# ==============================================================
# 检查
# ==============================================================
def check_health() -> bool:
    """健康检查。"""
    _section("1. 健康检查")

    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code != 200:
            _fail(f"状态码 {r.status_code}")
            return False

        data = r.json()
        if data.get("status") != "ok":
            _fail(f"状态不是 ok：{data}")
            return False

        _ok(f"MySQL：{data['mysql']['version']}")
        _ok(f"Redis：{data['redis']['version']}")
        return True
    except httpx.ConnectError:
        _fail("连不上服务，请先启动 python scripts/run_api.py")
        return False


def check_register() -> tuple[str, str] | None:
    """学生注册。"""
    _section("2. 学生注册")

    # 用时间戳做用户名，避免重复
    username = f"test_student_{int(time.time())}"
    password = "test123456"

    try:
        r = httpx.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "username": username,
                "password": password,
                "display_name": "测试学生",
            },
            timeout=10,
        )

        if r.status_code not in (200, 201):
            _fail(f"状态码 {r.status_code}：{r.text[:200]}")
            return None

        data = r.json()
        if "access_token" not in data:
            _fail(f"返回里没有 token：{data}")
            return None

        _ok(f"注册成功，用户名：{username}")
        _ok(f"获得 token：{data['access_token'][:40]}...")
        return username, data["access_token"]

    except Exception as exc:  # noqa: BLE001
        _fail(f"异常：{type(exc).__name__}: {exc}")
        return None


def check_login() -> tuple[str, str] | None:
    """学生登录。"""
    _section("3. 学生登录")

    username = f"test_login_{int(time.time())}"

    # 先注册
    httpx.post(
        f"{BASE_URL}/api/auth/register",
        json={"username": username, "password": "pass123456"},
        timeout=10,
    )

    # 再登录
    try:
        r = httpx.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": username, "password": "pass123456", "role": "user"},
            timeout=10,
        )

        if r.status_code != 200:
            _fail(f"登录失败：{r.status_code} {r.text[:200]}")
            return None

        token = r.json()["access_token"]
        _ok(f"登录成功：{username}")
        return username, token

    except Exception as exc:  # noqa: BLE001
        _fail(f"异常：{exc}")
        return None


def check_unauthorized() -> bool:
    """未登录访问受保护接口。"""
    _section("4. 未登录访问（应返回 401）")

    try:
        r = httpx.get(f"{BASE_URL}/api/user/courses", timeout=5)
        if r.status_code == 401:
            _ok("返回 401（正确）")
            return True
        else:
            _fail(f"期望 401，实际 {r.status_code}")
            return False
    except Exception as exc:  # noqa: BLE001
        _fail(f"异常：{exc}")
        return False


def check_user_access(token: str) -> bool:
    """学生访问用户接口。"""
    _section("5. 学生访问用户接口")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = httpx.get(f"{BASE_URL}/api/user/courses", headers=headers, timeout=5)
        if r.status_code != 200:
            _fail(f"状态码 {r.status_code}：{r.text[:200]}")
            return False

        courses = r.json()
        _ok(f"课程数：{len(courses)}")

        return True
    except Exception as exc:  # noqa: BLE001
        _fail(f"异常：{exc}")
        return False


def check_student_forbidden_from_admin(token: str) -> bool:
    """学生访问后台接口 → 403。"""
    _section("6. 学生访问后台接口（应返回 403）")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = httpx.get(f"{BASE_URL}/api/admin/dashboard", headers=headers, timeout=5)
        if r.status_code == 403:
            _ok("返回 403（正确）")
            return True
        else:
            _fail(f"期望 403，实际 {r.status_code}")
            return False
    except Exception as exc:  # noqa: BLE001
        _fail(f"异常：{exc}")
        return False


def check_admin_login() -> str | None:
    """管理员登录。"""
    _section("7. 管理员登录")

    try:
        r = httpx.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "admin", "password": "admin123", "role": "admin"},
            timeout=10,
        )

        if r.status_code != 200:
            _fail(f"管理员登录失败：{r.status_code} {r.text[:200]}")
            _fail("检查数据库里有没有 admin 用户（012_seed_admin.sql 应该建了）")
            return None

        token = r.json()["access_token"]
        _ok("管理员登录成功")
        return token

    except Exception as exc:  # noqa: BLE001
        _fail(f"异常：{exc}")
        return None


def check_admin_access(token: str) -> bool:
    """管理员访问后台接口。"""
    _section("8. 管理员访问后台接口")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = httpx.get(f"{BASE_URL}/api/admin/dashboard", headers=headers, timeout=5)
        if r.status_code != 200:
            _fail(f"状态码 {r.status_code}：{r.text[:200]}")
            return False

        data = r.json()
        _ok(f"课程数：{data['course_count']}")
        _ok(f"资料数：{data['material_count']}")
        _ok(f"待分类：{data['pending_classification_count']}")
        _ok(f"题库：{data['question_count']}")
        _ok(f"今日 LLM 调用：{data['llm_calls_today']}")

        return True
    except Exception as exc:  # noqa: BLE001
        _fail(f"异常：{exc}")
        return False


def check_logout(token: str) -> bool:
    """登出后 token 失效。"""
    _section("9. 登出后 token 失效")

    headers = {"Authorization": f"Bearer {token}"}

    # 先确认能访问
    r = httpx.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=5)
    if r.status_code != 200:
        _fail(f"登出前访问失败：{r.status_code}")
        return False
    _ok("登出前能正常访问")

    # 登出
    r = httpx.post(f"{BASE_URL}/api/auth/logout", headers=headers, timeout=5)
    if r.status_code != 200:
        _fail(f"登出失败：{r.status_code}")
        return False
    _ok("登出成功")

    # 再访问应失败
    r = httpx.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=5)
    if r.status_code == 401:
        _ok("登出后访问返回 401（正确）")
        return True
    else:
        _fail(f"登出后期望 401，实际 {r.status_code}")
        return False


# ==============================================================
# 主流程
# ==============================================================
def main() -> int:
    """入口。"""
    print("=" * 60)
    print("阶段四验证脚本")
    print("=" * 60)
    print(f"目标：{BASE_URL}")
    print()
    print("提示：请确保已启动服务（python scripts/run_api.py）")

    # 1. 健康检查
    if not check_health():
        return 1

    # 2. 注册
    register_result = check_register()
    if register_result is None:
        return 1
    username, token = register_result

    # 3. 登录
    login_result = check_login()
    if login_result is None:
        return 1
    login_username, login_token = login_result

    # 4. 未登录
    if not check_unauthorized():
        return 1

    # 5. 学生访问
    if not check_user_access(login_token):
        return 1

    # 6. 学生访问后台（应 403）
    if not check_student_forbidden_from_admin(login_token):
        return 1

    # 7. 管理员登录
    admin_token = check_admin_login()
    if admin_token is None:
        return 1

    # 8. 管理员访问
    if not check_admin_access(admin_token):
        return 1

    # 9. 登出
    if not check_logout(admin_token):
        return 1

    # 结论
    _section("结论")
    print("  阶段四全部通过。")
    print()
    print("  API 文档：http://localhost:8000/docs")
    print("  下一步：进入阶段五（React 用户端）")
    return 0


if __name__ == "__main__":
    sys.exit(main())