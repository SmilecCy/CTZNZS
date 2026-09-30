# -*- coding: utf-8 -*-
"""阶段三验证脚本：搜索工具 + LLM 生成题目。

用法（在项目根目录）::

    python scripts/verify_stage3.py

【这个脚本做什么】

    验证两条链路：
      A. 搜索工具（search_tool）
         - 未配 API Key 时返回空列表（不抛异常）
         - 配了 Key 时调真 API 拿结果（可选）
         - 每次调用都写审计日志

      B. 题目生成（generator）
         - 用假 LLM 走完整流程（建课程、生成题、入库、查回）
         - 题库命中时不调 LLM
         - force_generate 跳过题库优先

【为什么用假 LLM】

    真调 API 有成本、依赖网络、结果不稳定。
    验证脚本用假 LLM 跑通流程，确保代码逻辑正确。
    真调 API 的可选测试放在脚本最后。

【假 LLM 必须实现的接口】

    chat(messages, temperature, json_mode) -> LLMResponse
    chat_with_tools(messages, tools, tool_executor, ...) -> LLMResponse

    我们的 generator 会调这两个方法，所以假 LLM 都要实现。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app.database import (  # noqa: E402
    connection as db_mysql,
    courses as course,
    knowledge_points as knowledge_point,
    questions as question_bank_mysql,
    redis as db_redis,
)
from app.ai import generator, search_tool  # noqa: E402
from app.ai.llm_client import LLMResponse, LLMUsage  # noqa: E402


# ==============================================================
# 测试常量
# ==============================================================
TEST_COURSE_PREFIX = "测试阶段三_"


# ==============================================================
# 假 LLM
# ==============================================================
class FakeLLM:
    """假 LLM 客户端。

    【实现的接口】
        - chat(): 普通调用
        - chat_with_tools(): 带工具调用

    两个都实现，因为 generator 会根据"是否启用搜索"
    走不同的调用路径。
    """

    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or {
            "questions": [
                {
                    "question": "第1题：请简述测试知识点。",
                    "reference_answer": "参考答案正文。",
                    "scoring_points": ["要点一", "要点二"],
                    "knowledge_tags": ["测试知识点"],
                    "difficulty": "中",
                    "source": "chunk_test_001",
                }
            ]
        }
        self.model = "fake-llm"
        self.chat_calls = 0
        self.tool_calls = 0

    def _make_response(self) -> LLMResponse:
        """构造 LLMResponse。"""
        content = json.dumps(self.payload, ensure_ascii=False)
        return LLMResponse(
            content=content,
            usage=LLMUsage(
                model=self.model,
                prompt_tokens=300,
                completion_tokens=100,
                latency_ms=20,
            ),
        )

    def chat(self, messages, temperature=None, json_mode=None):
        """普通调用。"""
        self.chat_calls += 1
        return self._make_response()

    def chat_with_tools(self, messages, tools, tool_executor, max_iterations=3, temperature=None):
        """带工具调用。

        【本假实现的行为】
            模拟"LLM 决定不调工具"直接返回答案。
            真实 LLM 可能会调工具，但验证脚本里我们不想真的调搜索 API，
            所以让假 LLM 直接返回。
        """
        self.tool_calls += 1
        return self._make_response()


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


def _cleanup() -> None:
    """清理测试数据。"""
    try:
        with db_mysql.connection() as conn:
            with conn.cursor() as cur:
                # 查测试课程
                cur.execute(
                    "SELECT id FROM courses WHERE name LIKE %s",
                    (f"{TEST_COURSE_PREFIX}%",),
                )
                ids = [row["id"] for row in cur.fetchall()]
                if not ids:
                    return

                placeholders = ", ".join(["%s"] * len(ids))

                # 删题目（外键 CASCADE 会连带，但显式删更清晰）
                cur.execute(
                    f"DELETE FROM question_bank WHERE course_id IN ({placeholders})",
                    ids,
                )
                # 删知识点
                cur.execute(
                    f"DELETE FROM knowledge_points WHERE course_id IN ({placeholders})",
                    ids,
                )
                # 删课程
                cur.execute(
                    f"DELETE FROM courses WHERE id IN ({placeholders})",
                    ids,
                )

        from app.database import cache
        cache.invalidate_course_list()
    except Exception as exc:  # noqa: BLE001
        print(f"  [警告] 清理失败（可忽略）：{exc}")


# ==============================================================
# 检查项
# ==============================================================
def check_connections() -> bool:
    """检查 MySQL / Redis。"""
    _section("1. 数据库连通性")

    mysql = db_mysql.health_check()
    if mysql["ok"]:
        _ok(f"MySQL 连通（{mysql['version']}）")
    else:
        _fail(f"MySQL 连不上：{mysql['error']}")
        return False

    redis = db_redis.health_check()
    if redis["ok"]:
        _ok(f"Redis 连通（{redis['version']}）")
    else:
        _fail(f"Redis 连不上：{redis['error']}")
        return False

    return True


def check_search_tool_not_configured() -> bool:
    """测试：未配置 API Key 时搜索的行为。"""
    _section("2. 搜索工具（未配置 Key 的行为）")

    configured = search_tool.is_configured()
    if configured:
        _ok("BOCHA_API_KEY 已配置（跳过'未配置'的测试）")
        return True

    # 未配置时，search 应返回空列表，不抛异常
    results = search_tool.search(
        query="测试查询",
        top_k=3,
        purpose="verify_test",
    )

    if results == []:
        _ok("未配置 Key 时返回空列表（不抛异常）")
    else:
        _fail(f"期望空列表，实际 {len(results)} 条")
        return False

    # 验证审计日志写了（失败也记）
    row = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n FROM search_call_log WHERE purpose = %s",
        ("verify_test",),
    )
    if row and int(row["n"]) > 0:
        _ok(f"审计日志已记录（{int(row['n'])} 条）")
    else:
        _fail("审计日志没有记录")
        return False

    return True


def check_search_tool_real() -> bool:
    """测试：真调博查 API（可选）。"""
    _section("3. 搜索工具（真实调用，可选）")

    if not search_tool.is_configured():
        _ok("未配置 BOCHA_API_KEY，跳过真实调用测试")
        _ok("（想测试真实搜索：在 .env 里填 BOCHA_API_KEY）")
        return True

    results = search_tool.search(
        query="商法 归责原则 简答题",
        top_k=3,
        purpose="verify_real",
    )

    if not results:
        _fail("真实搜索没返回结果（可能是网络或配额问题）")
        return False

    _ok(f"真实搜索返回 {len(results)} 条结果")
    for i, r in enumerate(results[:2], start=1):
        title = r.get("title", "")[:40]
        _ok(f"  [{i}] {title}")

    return True


def check_generator_from_bank() -> bool:
    """测试：题库命中时不调 LLM。"""
    _section("4. 出题：题库命中路径")

    try:
        # 建测试课程
        course_id = course.create(name=f"{TEST_COURSE_PREFIX}命中测试")
        _ok(f"建课程：id={course_id}")

        # 手动往题库塞一道题
        qid = question_bank_mysql.insert_question(
            course_id=course_id,
            knowledge_point="测试知识点_命中",
            knowledge_point_id=None,
            question_type="简答",
            difficulty="中",
            payload={
                "question": "题库里的题：请简述测试。",
                "reference_answer": "参考答案",
                "scoring_points": ["要点1", "要点2"],
            },
            source="generated",
            source_ref="test_chunk_1",
            prompt_version="0.1",
            model_version="fake",
        )
        _ok(f"往题库塞了 1 道题：id={qid}")

        # 调 generator（用假 LLM，如果调了会记到 chat_calls）
        fake_llm = FakeLLM()
        result = generator.get_questions(
            course_id=course_id,
            knowledge_point="测试知识点_命中",
            question_type="简答",
            difficulty="中",
            count=1,
            llm=fake_llm,
        )

        # 验证：命中题库，不调 LLM
        if result["source_summary"]["from_bank"] != 1:
            _fail(f"from_bank 应为 1，实际 {result['source_summary']['from_bank']}")
            return False
        _ok("from_bank = 1")

        if fake_llm.chat_calls != 0:
            _fail(f"命中题库时不该调 LLM，实际调了 {fake_llm.chat_calls} 次")
            return False
        _ok("LLM 没被调用")

        # 验证 usage_count 加了
        q = question_bank_mysql.get_question(qid)
        if q["usage_count"] != 1:
            _fail(f"usage_count 应为 1，实际 {q['usage_count']}")
            return False
        _ok("usage_count 已更新")

        return True

    except Exception as exc:  # noqa: BLE001
        _fail(f"异常：{type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return False


def check_generator_generate_new() -> bool:
    """测试：题库未命中时调 LLM 生成。"""
    _section("5. 出题：LLM 生成路径")

    try:
        # 建新课程（题库是空的）
        course_id = course.create(name=f"{TEST_COURSE_PREFIX}生成测试")
        _ok(f"建课程：id={course_id}")

        fake_llm = FakeLLM()

        result = generator.get_questions(
            course_id=course_id,
            knowledge_point="测试知识点_生成",
            question_type="简答",
            difficulty="中",
            count=1,
            llm=fake_llm,
        )

        # 验证：调了 LLM，生成了题
        if fake_llm.chat_calls != 1:
            _fail(f"期望调 LLM 1 次，实际 {fake_llm.chat_calls} 次")
            return False
        _ok(f"LLM 被调用 {fake_llm.chat_calls} 次")

        if result["source_summary"]["from_llm"] != 1:
            _fail(f"from_llm 应为 1，实际 {result['source_summary']['from_llm']}")
            return False
        _ok("from_llm = 1")

        # 验证入库
        if question_bank_mysql.count_questions(course_id) != 1:
            _fail("生成的题没入库")
            return False
        _ok("生成的题已入库")

        return True

    except Exception as exc:  # noqa: BLE001
        _fail(f"异常：{type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return False


def check_force_generate() -> bool:
    """测试：force_generate 跳过题库优先。"""
    _section("6. 出题：force_generate 跳过题库")

    try:
        # 建课程，先塞一道题
        course_id = course.create(name=f"{TEST_COURSE_PREFIX}强制生成测试")
        qid = question_bank_mysql.insert_question(
            course_id=course_id,
            knowledge_point="测试知识点_强制",
            knowledge_point_id=None,
            question_type="简答",
            difficulty="中",
            payload={
                "question": "题库里的题",
                "reference_answer": "答案",
                "scoring_points": ["点1"],
            },
            source="generated",
            source_ref="chunk",
            prompt_version="0.1",
            model_version="fake",
        )

        fake_llm = FakeLLM()
        result = generator.get_questions(
            course_id=course_id,
            knowledge_point="测试知识点_强制",
            question_type="简答",
            difficulty="中",
            count=1,
            llm=fake_llm,
            force_generate=True,
        )

        # 验证：跳过了查库，直接生成
        if result["source_summary"]["from_bank"] != 0:
            _fail(f"force_generate 时 from_bank 应为 0，实际 {result['source_summary']['from_bank']}")
            return False
        _ok("from_bank = 0（正确跳过了题库）")

        if fake_llm.chat_calls != 1:
            _fail(f"期望调 LLM 1 次，实际 {fake_llm.chat_calls} 次")
            return False
        _ok("LLM 被调用")

        return True

    except Exception as exc:  # noqa: BLE001
        _fail(f"异常：{type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return False


def check_bank_stats() -> bool:
    """测试：题库统计。"""
    _section("7. 题库统计")

    try:
        course_id = course.create(name=f"{TEST_COURSE_PREFIX}统计测试")

        # 塞几道不同类型的题
        for qtype, diff in [("简答", "易"), ("简答", "中"), ("选择", "中")]:
            payload = {
                "question": f"测试题-{qtype}-{diff}",
                "reference_answer": "答案",
                "scoring_points": ["点1"],
            }
            if qtype == "选择":
                payload = {
                    "question": f"测试题-{qtype}-{diff}",
                    "options": ["A", "B", "C", "D"],
                    "correct_index": 0,
                    "explanation": "解析",
                    "reference_answer": "A",
                    "scoring_points": [],
                }
            question_bank_mysql.insert_question(
                course_id=course_id,
                knowledge_point="测试知识点_统计",
                knowledge_point_id=None,
                question_type=qtype,
                difficulty=diff,
                payload=payload,
                source="generated",
                source_ref="chunk",
                prompt_version="0.1",
                model_version="fake",
            )

        stats = question_bank_mysql.bank_stats(course_id)

        if stats["total"] != 3:
            _fail(f"总数应为 3，实际 {stats['total']}")
            return False
        _ok(f"总数：{stats['total']}")

        if stats["by_type"] != {"简答": 2, "选择": 1}:
            _fail(f"by_type 不对：{stats['by_type']}")
            return False
        _ok(f"by_type：{stats['by_type']}")

        return True

    except Exception as exc:  # noqa: BLE001
        _fail(f"异常：{type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return False


def check_feedback() -> bool:
    """测试：反馈记录。"""
    _section("8. 反馈记录")

    try:
        course_id = course.create(name=f"{TEST_COURSE_PREFIX}反馈测试")
        qid = question_bank_mysql.insert_question(
            course_id=course_id,
            knowledge_point="测试点",
            knowledge_point_id=None,
            question_type="简答",
            difficulty="中",
            payload={
                "question": "题",
                "reference_answer": "答案",
                "scoring_points": ["点1"],
            },
            source="generated",
            source_ref="chunk",
            prompt_version="0.1",
            model_version="fake",
        )

        # 好评
        result = question_bank_mysql.record_feedback(qid, "good")
        if result["quality_score"] != 1.0:
            _fail(f"好评后质量分应为 1.0，实际 {result['quality_score']}")
            return False
        _ok("好评 +1")

        # 差评
        result = question_bank_mysql.record_feedback(qid, "bad")
        if result["quality_score"] != 0.0:
            _fail(f"差评后质量分应为 0.0，实际 {result['quality_score']}")
            return False
        _ok("差评 -1")

        return True

    except Exception as exc:  # noqa: BLE001
        _fail(f"异常：{type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================
# 主流程
# ==============================================================
def main() -> int:
    """入口。"""
    print("=" * 60)
    print("阶段三验证脚本")
    print("=" * 60)

    _cleanup()

    if not check_connections():
        return 1

    try:
        # 搜索工具
        if not check_search_tool_not_configured():
            return 1
        if not check_search_tool_real():
            return 1

        # 出题
        if not check_generator_from_bank():
            return 1
        if not check_generator_generate_new():
            return 1
        if not check_force_generate():
            return 1

        # 题库管理
        if not check_bank_stats():
            return 1
        if not check_feedback():
            return 1

    finally:
        _section("清理测试数据")
        _cleanup()
        _ok("清理完成")

    _section("结论")
    print("  阶段三全部通过。")
    print()
    print("  说明：")
    print("    - 出题流程用的是假 LLM，不产生费用")
    print("    - 搜索用真 API（如果配了 BOCHA_API_KEY）")
    print("    - 没配 Key 时会自动跳过真实搜索测试")
    print()
    print("  下一步：进入阶段四（FastAPI 接口层）")

    return 0


if __name__ == "__main__":
    sys.exit(main())