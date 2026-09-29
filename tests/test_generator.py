# -*- coding: utf-8 -*-
"""出题引擎的单元测试。

【测试目标】

    1. 题库命中时不调 LLM
    2. 题库未命中时调 LLM 并入库
    3. force_generate 跳过题库优先
    4. 生成的题目格式规范化（缺字段、类型错、越界）
    5. 坏题只跳过不连坐
    6. 参数校验（非法题型、难度、count）

【测试策略】

    用假 LLM（返回预设 JSON），不真调 API。
    用真实 MySQL（temp_db fixture 提供）。
"""

from __future__ import annotations

import json

import pytest

from app.database import courses as course, questions as question_bank_mysql; from app.ai import generator
from app.ai.llm_client import LLMResponse, LLMUsage


# ==============================================================
# 假 LLM
# ==============================================================
class FakeLLM:
    """假 LLM，返回预设的题目。"""

    def __init__(self, questions: list[dict]) -> None:
        """构造假 LLM。

        Args:
            questions: 要返回的题目列表。
        """
        self.questions = questions
        self.chat_calls = 0
        self.tool_calls = 0
        self.model = "fake"

    def _make_response(self) -> LLMResponse:
        payload = {"questions": self.questions}
        content = json.dumps(payload, ensure_ascii=False)
        return LLMResponse(
            content=content,
            usage=LLMUsage(model=self.model, prompt_tokens=100, completion_tokens=50),
        )

    def chat(self, messages, temperature=None, json_mode=None):
        self.chat_calls += 1
        return self._make_response()

    def chat_with_tools(self, messages, tools, tool_executor, **kwargs):
        self.tool_calls += 1
        return self._make_response()


def _make_course(name: str = "测试课程_生成器") -> int:
    """建一个测试课程。"""
    return course.create(name=name)


def _make_short_question(stem: str = "请简述测试。") -> dict:
    """造一道合法的简答题。"""
    return {
        "question": stem,
        "reference_answer": "参考答案",
        "scoring_points": ["要点1", "要点2"],
        "knowledge_tags": ["测试知识点"],
        "difficulty": "中",
        "source": "chunk_001",
    }


def _make_choice_question(stem: str = "以下哪个正确？") -> dict:
    """造一道合法的选择题。"""
    return {
        "question": stem,
        "options": ["A选项", "B选项", "C选项", "D选项"],
        "correct_index": 1,
        "explanation": "解析",
        "knowledge_tags": ["测试知识点"],
        "difficulty": "中",
        "source": "chunk_002",
    }


# ==============================================================
# 题库命中
# ==============================================================
def test_bank_hit_no_llm_call(temp_db) -> None:
    """题库命中时，不调 LLM。"""
    course_id = _make_course("测试_命中不调")

    # 塞一道题
    question_bank_mysql.insert_question(
        course_id=course_id,
        knowledge_point="测试知识点",
        knowledge_point_id=None,
        question_type="简答",
        difficulty="中",
        payload={
            "question": "库内题",
            "reference_answer": "答案",
            "scoring_points": ["点1"],
        },
        source="generated",
        source_ref="chunk_x",
        prompt_version="0.1",
        model_version="fake",
    )

    fake = FakeLLM([])
    result = generator.get_questions(
        course_id=course_id,
        knowledge_point="测试知识点",
        question_type="简答",
        difficulty="中",
        count=1,
        llm=fake,
    )

    assert result["source_summary"]["from_bank"] == 1
    assert result["source_summary"]["from_llm"] == 0
    assert fake.chat_calls == 0


def test_bank_hit_increments_usage(temp_db) -> None:
    """题库命中时，usage_count 加 1。"""
    course_id = _make_course("测试_计数")

    qid = question_bank_mysql.insert_question(
        course_id=course_id,
        knowledge_point="测试知识点",
        knowledge_point_id=None,
        question_type="简答",
        difficulty="中",
        payload={"question": "题", "reference_answer": "答", "scoring_points": ["点"]},
        source="generated",
        source_ref="chunk",
        prompt_version="0.1",
        model_version="fake",
    )

    generator.get_questions(
        course_id=course_id,
        knowledge_point="测试知识点",
        question_type="简答",
        difficulty="中",
        count=1,
        llm=FakeLLM([]),
    )

    row = question_bank_mysql.get_question(qid)
    assert row["usage_count"] == 1


# ==============================================================
# 未命中：调 LLM
# ==============================================================
def test_generate_new_question(temp_db) -> None:
    """题库没有时，调 LLM 生成并入库。"""
    course_id = _make_course("测试_生成新题")
    fake = FakeLLM([_make_short_question()])

    result = generator.get_questions(
        course_id=course_id,
        knowledge_point="测试知识点",
        question_type="简答",
        difficulty="中",
        count=1,
        llm=fake,
    )

    assert fake.chat_calls == 1
    assert result["source_summary"]["from_llm"] == 1
    assert question_bank_mysql.count_questions(course_id) == 1


def test_generated_question_is_stored(temp_db) -> None:
    """生成的题真的写到了数据库。"""
    course_id = _make_course("测试_入库")
    fake = FakeLLM([_make_short_question("入库测试题")])

    result = generator.get_questions(
        course_id=course_id,
        knowledge_point="测试知识点",
        question_type="简答",
        difficulty="中",
        count=1,
        llm=fake,
    )

    qid = result["questions"][0]["id"]
    row = question_bank_mysql.get_question(qid)
    assert row is not None
    assert row["payload"]["question"] == "入库测试题"
    assert row["status"] == "active"


# ==============================================================
# force_generate
# ==============================================================
def test_force_generate_skips_bank(temp_db) -> None:
    """force_generate=True 时跳过题库。"""
    course_id = _make_course("测试_强制")

    # 先塞一道题
    question_bank_mysql.insert_question(
        course_id=course_id,
        knowledge_point="测试知识点",
        knowledge_point_id=None,
        question_type="简答",
        difficulty="中",
        payload={"question": "库内题", "reference_answer": "答", "scoring_points": ["点"]},
        source="generated",
        source_ref="chunk",
        prompt_version="0.1",
        model_version="fake",
    )

    fake = FakeLLM([_make_short_question("新生成的题")])
    result = generator.get_questions(
        course_id=course_id,
        knowledge_point="测试知识点",
        question_type="简答",
        difficulty="中",
        count=1,
        llm=fake,
        force_generate=True,
    )

    # 应该跳过题库直接生成
    assert result["source_summary"]["from_bank"] == 0
    assert result["source_summary"]["from_llm"] == 1
    assert fake.chat_calls == 1


# ==============================================================
# 题目规范化
# ==============================================================
def test_normalize_short_answer(temp_db) -> None:
    """规范化简答题。"""
    result = generator.normalize_question(
        raw={
            "question": "题干",
            "reference_answer": "答案",
            "scoring_points": ["点1", "点2"],
            "difficulty": "难",
        },
        question_type="简答",
        knowledge_point="测试",
        difficulty="中",
        default_source_ref="chunk_x",
    )

    # 难度以请求的为准（中），不是模型自报的（难）
    assert result["difficulty"] == "中"
    assert result["question"] == "题干"
    assert result["reference_answer"] == "答案"
    assert result["source_ref"] == "chunk_x"


def test_normalize_choice_question(temp_db) -> None:
    """规范化选择题。"""
    result = generator.normalize_question(
        raw={
            "question": "题干",
            "options": ["A", "B", "C"],
            "correct_index": 2,
        },
        question_type="选择",
        knowledge_point="测试",
        difficulty="中",
        default_source_ref="chunk_x",
    )

    assert result["correct_index"] == 2
    assert result["reference_answer"] == "C"   # 正确答案是第 3 个选项
    assert len(result["options"]) == 3


def test_normalize_missing_stem_raises(temp_db) -> None:
    """缺题干：抛 ValueError。"""
    with pytest.raises(ValueError, match="question"):
        generator.normalize_question(
            raw={"reference_answer": "答案"},
            question_type="简答",
            knowledge_point="测试",
            difficulty="中",
            default_source_ref="x",
        )


def test_normalize_missing_answer_raises(temp_db) -> None:
    """简答题缺答案：抛 ValueError。"""
    with pytest.raises(ValueError, match="reference_answer"):
        generator.normalize_question(
            raw={"question": "题干", "scoring_points": ["点"]},
            question_type="简答",
            knowledge_point="测试",
            difficulty="中",
            default_source_ref="x",
        )


def test_normalize_choice_index_out_of_range(temp_db) -> None:
    """选择题的 correct_index 越界：抛 ValueError。"""
    with pytest.raises(ValueError, match="correct_index"):
        generator.normalize_question(
            raw={
                "question": "题干",
                "options": ["A", "B"],
                "correct_index": 5,
            },
            question_type="选择",
            knowledge_point="测试",
            difficulty="中",
            default_source_ref="x",
        )


def test_normalize_choice_missing_options_raises(temp_db) -> None:
    """选择题缺选项：抛 ValueError。"""
    with pytest.raises(ValueError, match="options"):
        generator.normalize_question(
            raw={"question": "题干", "correct_index": 0},
            question_type="选择",
            knowledge_point="测试",
            difficulty="中",
            default_source_ref="x",
        )


def test_scoring_points_from_string(temp_db) -> None:
    """评分要点从字符串转列表。"""
    result = generator.normalize_question(
        raw={
            "question": "题干",
            "reference_answer": "答案",
            "scoring_points": "点1；点2；点3",
        },
        question_type="简答",
        knowledge_point="测试",
        difficulty="中",
        default_source_ref="x",
    )
    assert result["scoring_points"] == ["点1", "点2", "点3"]


def test_bad_question_skipped_not_fatal(temp_db) -> None:
    """一批题里混入坏题：跳过它，好题正常入库。"""
    course_id = _make_course("测试_坏题")

    # 3 道题，中间一道是坏的（缺题干）
    fake = FakeLLM([
        _make_short_question("好题1"),
        {"question": "", "reference_answer": "答案"},   # 坏题：题干为空
        _make_short_question("好题2"),
    ])

    result = generator.get_questions(
        course_id=course_id,
        knowledge_point="测试知识点",
        question_type="简答",
        difficulty="中",
        count=1,
        llm=fake,
    )

    # 至少有一道好题入库了
    assert result["source_summary"]["from_llm"] >= 1
    assert question_bank_mysql.count_questions(course_id) >= 1


# ==============================================================
# 参数校验
# ==============================================================
def test_invalid_question_type(temp_db) -> None:
    """非法题型：抛 ValueError。"""
    course_id = _make_course("测试_非法")
    with pytest.raises(ValueError, match="未知题型"):
        generator.get_questions(
            course_id=course_id,
            knowledge_point="测试",
            question_type="判断",   # 不支持的题型
            difficulty="中",
            count=1,
            llm=FakeLLM([]),
        )


def test_invalid_difficulty(temp_db) -> None:
    """非法难度：抛 ValueError。"""
    course_id = _make_course("测试_非法难度")
    with pytest.raises(ValueError, match="未知难度"):
        generator.get_questions(
            course_id=course_id,
            knowledge_point="测试",
            question_type="简答",
            difficulty="地狱",
            count=1,
            llm=FakeLLM([]),
        )


def test_invalid_count(temp_db) -> None:
    """count <= 0：抛 ValueError。"""
    course_id = _make_course("测试_非法count")
    with pytest.raises(ValueError, match="count"):
        generator.get_questions(
            course_id=course_id,
            knowledge_point="测试",
            question_type="简答",
            difficulty="中",
            count=0,
            llm=FakeLLM([]),
        )


# ==============================================================
# 提示词路由
# ==============================================================
def test_resolve_prompt_by_course_name(temp_db) -> None:
    """按课程名选提示词模板。"""
    assert generator.resolve_prompt("商法", "简答") == "m2_tort_short_answer_v0.1"
    assert generator.resolve_prompt("习概", "简答") == "m2_xigai_short_answer_v0.1"
    assert generator.resolve_prompt("商法", "选择") == "m2_all_choice_v0.1"
    assert generator.resolve_prompt("习概", "选择") == "m2_all_choice_v0.1"