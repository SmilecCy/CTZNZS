# -*- coding: utf-8 -*-
"""阶段 5.2.1 验证脚本：后端补接口。

用法::

    # 先启动服务（另一个 PowerShell 窗口）
    python scripts/run_api.py

    # 再跑本脚本
    python scripts/verify_stage5_2_1.py

【验证内容】

    1. 学生注册并登录
    2. 出题（题库优先 + 生成）
    3. 作答选择题 → 判分 + 错题自动收录
    4. 作答简答题 → LLM 判分
    5. 错题集列表、统计
    6. 标记掌握状态、记录复习
    7. 删除错题
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import httpx  # noqa: E402


BASE_URL = "http://localhost:5174"


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
# 准备：建一个测试课程 + 题目
# ==============================================================
def setup_data() -> tuple[int, int, int] | None:
    """建课程、知识点、题目（直接用 service 层，不走 HTTP）。

    Returns:
        (course_id, choice_question_id, short_question_id)
    """
    _section("准备测试数据")

    from app.database import courses as course, knowledge_points as knowledge_point, questions as question_bank_mysql

    try:
        # 建课程（可能已存在）
        existing = course.get_by_name("测试_5.2.1")
        if existing:
            course_id = existing["id"]
            _ok(f"复用课程：id={course_id}")
        else:
            course_id = course.create(name="测试_5.2.1", display_name="阶段5.2.1测试")
            _ok(f"建课程：id={course_id}")

        # 建知识点
        knowledge_point.bulk_create(course_id, ["测试知识点"])
        _ok("知识点已就绪")

        # 建一道选择题
        choice_payload = {
            "question": "以下哪个是测试选择题的题干？",
            "options": ["选项A", "选项B", "选项C", "选项D"],
            "correct_index": 1,
            "explanation": "B 是正确答案，因为测试。",
            "reference_answer": "选项B",
            "scoring_points": [],
        }
        choice_id = question_bank_mysql.insert_question(
            course_id=course_id,
            knowledge_point="测试知识点",
            knowledge_point_id=None,
            question_type="选择",
            difficulty="中",
            payload=choice_payload,
            source="generated",
            source_ref="test",
            prompt_version="0.1",
            model_version="fake",
        )
        _ok(f"建选择题：id={choice_id}")

        # 建一道简答题
        short_payload = {
            "question": "请简述测试知识点的三个要点。",
            "reference_answer": "要点1：xxx。要点2：yyy。要点3：zzz。",
            "scoring_points": ["要点1的说明", "要点2的说明", "要点3的说明"],
            "explanation": "",
        }
        short_id = question_bank_mysql.insert_question(
            course_id=course_id,
            knowledge_point="测试知识点",
            knowledge_point_id=None,
            question_type="简答",
            difficulty="中",
            payload=short_payload,
            source="generated",
            source_ref="test",
            prompt_version="0.1",
            model_version="fake",
        )
        _ok(f"建简答题：id={short_id}")

        return course_id, choice_id, short_id

    except Exception as exc:
        _fail(f"准备数据失败：{type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return None


# ==============================================================
# 登录
# ==============================================================
def login_student() -> tuple[str, int] | None:
    """注册并登录一个学生，返回 (token, user_id)。"""
    _section("学生注册并登录")

    username = f"test_52_{int(time.time())}"
    password = "test123456"

    try:
        r = httpx.post(
            f"{BASE_URL}/api/auth/register",
            json={"username": username, "password": password},
            timeout=10,
        )
        if r.status_code not in (200, 201):
            _fail(f"注册失败：{r.status_code} {r.text[:200]}")
            return None

        data = r.json()
        token = data["access_token"]
        user_id = data["user"]["id"]
        _ok(f"注册成功：{username} (id={user_id})")
        return token, user_id

    except Exception as exc:
        _fail(f"异常：{exc}")
        return None


# ==============================================================
# 出题
# ==============================================================
def test_get_questions(token: str, course_id: int) -> bool:
    """出题（题库优先）。"""
    _section("出题")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = httpx.post(
            f"{BASE_URL}/api/user/questions",
            json={
                "course_id": course_id,
                "knowledge_point": "测试知识点",
                "question_type": "选择",
                "difficulty": "中",
                "count": 1,
            },
            headers=headers,
            timeout=30,
        )
        if r.status_code != 200:
            _fail(f"出题失败：{r.status_code} {r.text[:200]}")
            return False

        data = r.json()
        _ok(f"出题成功，返回 {len(data['questions'])} 道")
        _ok(f"来源：{data['source_summary']}")
        return True

    except Exception as exc:
        _fail(f"异常：{exc}")
        return False


# ==============================================================
# 作答
# ==============================================================
def test_answer_choice(token: str, course_id: int, question_id: int) -> bool:
    """作答选择题（故意答错）。"""
    _section("作答选择题（答错 → 自动收录错题）")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        # 故意答错：选 A（正确答案是 B）
        r = httpx.post(
            f"{BASE_URL}/api/user/answers",
            json={
                "question_id": question_id,
                "user_answer": "0",   # 索引 0 = A
                "course_id": course_id,
                "knowledge_point": "测试知识点",
            },
            headers=headers,
            timeout=10,
        )
        if r.status_code != 200:
            _fail(f"作答失败：{r.status_code} {r.text[:200]}")
            return False

        data = r.json()
        _ok(f"判分结果：is_correct={data['is_correct']}, score={data['score']}")
        _ok(f"错题已收录：{data['wrong_recorded']}")

        if data["is_correct"] is not False:
            _fail("期望答错，但判成对了")
            return False

        if not data["wrong_recorded"]:
            _fail("期望自动收录错题，但没有")
            return False

        return True

    except Exception as exc:
        _fail(f"异常：{exc}")
        return False


def test_answer_short(token: str, course_id: int, question_id: int) -> bool:
    """作答简答题（调 LLM 判分）。"""
    _section("作答简答题（LLM 判分）")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = httpx.post(
            f"{BASE_URL}/api/user/answers",
            json={
                "question_id": question_id,
                "user_answer": "要点1是xxx，要点2是yyy，但没说要点3。",
                "course_id": course_id,
                "knowledge_point": "测试知识点",
            },
            headers=headers,
            timeout=60,   # LLM 判分比较慢
        )
        if r.status_code != 200:
            _fail(f"作答失败：{r.status_code} {r.text[:300]}")
            return False

        data = r.json()
        _ok(f"判分结果：is_correct={data['is_correct']}, score={data['score']}")
        _ok(f"批改意见：{data['comment'][:50]}...")
        _ok(f"逐要点判定数：{len(data.get('point_results', []))}")

        if data.get("error"):
            _fail(f"判分出错：{data['error']}")
            return False

        return True

    except Exception as exc:
        _fail(f"异常：{exc}")
        return False


# ==============================================================
# 错题集
# ==============================================================
def test_wrong_book(token: str, course_id: int) -> int | None:
    """错题集列表、统计、标记掌握。"""
    _section("错题集")

    headers = {"Authorization": f"Bearer {token}"}

    # 列表
    try:
        r = httpx.get(
            f"{BASE_URL}/api/user/wrong-questions",
            params={"course_id": course_id},
            headers=headers,
            timeout=10,
        )
        if r.status_code != 200:
            _fail(f"列表失败：{r.status_code}")
            return None

        entries = r.json()
        _ok(f"错题数：{len(entries)}")

        if not entries:
            _fail("期望有错题，但列表为空")
            return None

        first_id = entries[0]["id"]
        _ok(f"第一条错题 id={first_id}, 状态={entries[0]['mastery_label']}")

    except Exception as exc:
        _fail(f"异常：{exc}")
        return None

    # 统计
    try:
        r = httpx.get(
            f"{BASE_URL}/api/user/wrong-questions/stats",
            params={"course_id": course_id},
            headers=headers,
            timeout=10,
        )
        if r.status_code != 200:
            _fail(f"统计失败：{r.status_code}")
            return None

        stats = r.json()
        _ok(f"总数：{stats['total']}, 待复习：{stats['unmastered']}, 已掌握：{stats['mastered']}")

    except Exception as exc:
        _fail(f"异常：{exc}")
        return None

    # 标记掌握
    try:
        r = httpx.patch(
            f"{BASE_URL}/api/user/wrong-questions/{first_id}",
            json={"mastered": True},
            headers=headers,
            timeout=10,
        )
        if r.status_code != 200:
            _fail(f"标记掌握失败：{r.status_code} {r.text[:200]}")
            return None

        _ok("标记已掌握成功")

    except Exception as exc:
        _fail(f"异常：{exc}")
        return None

    # 记录复习
    try:
        r = httpx.post(
            f"{BASE_URL}/api/user/wrong-questions/{first_id}/review",
            json={"correct": True},
            headers=headers,
            timeout=10,
        )
        if r.status_code != 200:
            _fail(f"记录复习失败：{r.status_code}")
            return None

        _ok("记录复习成功")

    except Exception as exc:
        _fail(f"异常：{exc}")
        return None

    return first_id


def test_delete_wrong(token: str, entry_id: int) -> bool:
    """删除错题。"""
    _section("删除错题")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = httpx.delete(
            f"{BASE_URL}/api/user/wrong-questions/{entry_id}",
            headers=headers,
            timeout=10,
        )
        if r.status_code != 200:
            _fail(f"删除失败：{r.status_code} {r.text[:200]}")
            return False

        _ok("删除成功")
        return True

    except Exception as exc:
        _fail(f"异常：{exc}")
        return False


# ==============================================================
# 主流程
# ==============================================================
def main() -> int:
    print("=" * 60)
    print("阶段 5.2.1 验证脚本")
    print("=" * 60)
    print(f"目标：{BASE_URL}")
    print()
    print("提示：请确保已启动服务（python scripts/run_api.py）")

    # 检查服务
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code != 200:
            _fail(f"服务不正常：{r.status_code}")
            return 1
        _ok("服务正常")
    except httpx.ConnectError:
        _fail("连不上服务，请先启动 python scripts/run_api.py")
        return 1

    # 准备数据
    setup_result = setup_data()
    if setup_result is None:
        return 1
    course_id, choice_id, short_id = setup_result

    # 登录
    login_result = login_student()
    if login_result is None:
        return 1
    token, user_id = login_result

    # 出题
    if not test_get_questions(token, course_id):
        return 1

    # 作答选择题
    if not test_answer_choice(token, course_id, choice_id):
        return 1

    # 作答简答题（会真的调 LLM）
    print()
    print("注意：接下来会调用一次 DeepSeek API（简答题判分）")
    print("按 Enter 继续，或 Ctrl+C 跳过")
    try:
        input()
    except EOFError:
        pass   # 非交互场景，直接继续

    if not test_answer_short(token, course_id, short_id):
        return 1

    # 错题集
    entry_id = test_wrong_book(token, course_id)
    if entry_id is None:
        return 1

    # 删除
    if not test_delete_wrong(token, entry_id):
        return 1

    # 结论
    _section("结论")
    print("  阶段 5.2.1 全部通过。")
    print()
    print("  下一步：阶段 5.2.2（前端重写练习页和错题集）")
    return 0


if __name__ == "__main__":
    sys.exit(main())