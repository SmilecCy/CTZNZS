# -*- coding: utf-8 -*-
"""资料分类模块的单元测试。

【测试目标】

    1. LLM 返回正常 JSON → 正确解析并写库
    2. LLM 返回空课程名 → 写入但不报错（这是合法结果，不是异常）
    3. LLM 返回格式乱（缺字段、类型不对）→ 容错处理，不崩
    4. LLM 调用失败 → 返回 success=False，不抛异常
    5. apply_suggestion：课程不存在时建课程，知识点也建
    6. apply_suggestion：课程已存在时复用

【为什么用假 LLM】

    真调 API 会让测试依赖网络、密钥、模型输出稳定性。
    单元测试应该 100% 可复现，所以全部用假 LLM。

【如何复用 conftest 里的 temp_db】

    项目根的 conftest.py 已经定义了 temp_db fixture，
    会自动把 SQLite/MySQL 指向临时库。
    这里直接用即可，不需要自己定义。
"""

from __future__ import annotations

import json

import pytest

from app.database import courses as course, knowledge_points as knowledge_point, materials as material_store; from app.ai import material_classifier
from app.ai.llm_client import LLMError, LLMResponse, LLMUsage


# ==============================================================
# 假 LLM
# ==============================================================
class FakeLLM:
    """假 LLM 客户端，按脚本返回预设值。"""

    def __init__(self, payload: object, raise_error: bool = False) -> None:
        """构造假 LLM。

        Args:
            payload: chat_json 要返回的 JSON 对象。
            raise_error: 是否模拟调用失败（抛 LLMError）。
        """
        self.payload = payload
        self.raise_error = raise_error
        self.calls = 0
        self.model = "fake-test"

    def chat_json(self, messages, temperature=None):
        """模拟 chat_json。

        返回 (payload, LLMResponse) 两元组。
        """
        self.calls += 1

        if self.raise_error:
            raise LLMError("模拟调用失败")

        response = LLMResponse(
            content=json.dumps(self.payload, ensure_ascii=False),
            usage=LLMUsage(
                model=self.model,
                prompt_tokens=100,
                completion_tokens=50,
                latency_ms=20,
            ),
        )
        return self.payload, response


# ==============================================================
# 测试数据
# ==============================================================
def _make_material(source_file: str = "测试_商法讲义.pdf") -> int:
    """建一份测试资料，返回 id。"""
    return material_store.create(
        source_file=source_file,
        kind="pdf",
        chunk_count=10,
        page_count=15,
    )


SAMPLE_TEXT = "商法讲义\n第一章 归责原则\n过错责任是侵权责任的一般归责原则。"


# ==============================================================
# classify_material 测试
# ==============================================================
def test_classify_success(temp_db) -> None:
    """正常识别：写入 detected_* 字段，状态变 suggested。"""
    mid = _make_material()

    fake = FakeLLM({
        "course_name": "商法",
        "course_confidence": 0.9,
        "knowledge_points": [
            {"name": "归责原则", "confidence": 0.95},
            {"name": "过错推定", "confidence": 0.88},
        ],
        "reasoning": "文件名含商法。",
    })

    result = material_classifier.classify_material(
        material_id=mid,
        sample_text=SAMPLE_TEXT,
        doc_title="商法讲义",
        llm=fake,
    )

    assert result["success"] is True
    assert result["course_name"] == "商法"
    assert result["course_confidence"] == 0.9
    assert len(result["knowledge_points"]) == 2
    assert fake.calls == 1

    # 检查数据库
    material = material_store.get_by_id(mid)
    assert material["detection_status"] == material_store.STATUS_SUGGESTED
    assert material["detected_course_name"] == "商法"
    assert len(material["detected_knowledge_points"]) == 2
    # 关键：识别阶段不该写 course_id
    assert material["course_id"] is None


def test_classify_empty_course_name(temp_db) -> None:
    """LLM 说看不出课程名：这是合法结果，应该正常处理。"""
    mid = _make_material()

    fake = FakeLLM({
        "course_name": "",
        "course_confidence": 0.0,
        "knowledge_points": [],
        "reasoning": "样本太短，无法判断。",
    })

    result = material_classifier.classify_material(
        material_id=mid,
        sample_text="简短文本",
        llm=fake,
    )

    # success=True 但课程名为空——这是合法的"识别完成，但没结果"
    assert result["success"] is True
    assert result["course_name"] == ""


def test_classify_material_not_found(temp_db) -> None:
    """资料 id 不存在：返回失败，不抛异常。"""
    fake = FakeLLM({"course_name": "x"})
    result = material_classifier.classify_material(
        material_id=999999,
        sample_text="内容",
        llm=fake,
    )
    assert result["success"] is False
    assert "不存在" in result["error"]
    # 没调用 LLM
    assert fake.calls == 0


def test_classify_empty_sample_text(temp_db) -> None:
    """样本为空：直接失败，不调 LLM。"""
    mid = _make_material()
    fake = FakeLLM({"course_name": "x"})

    result = material_classifier.classify_material(
        material_id=mid,
        sample_text="   ",
        llm=fake,
    )

    assert result["success"] is False
    assert "样本" in result["error"]
    assert fake.calls == 0


def test_classify_llm_failure(temp_db) -> None:
    """LLM 调用失败：返回 success=False，不抛异常。"""
    mid = _make_material()
    fake = FakeLLM({}, raise_error=True)

    result = material_classifier.classify_material(
        material_id=mid,
        sample_text=SAMPLE_TEXT,
        llm=fake,
    )

    assert result["success"] is False
    assert "调用失败" in result["error"] or "模拟" in result["error"]


def test_classify_malformed_response(temp_db) -> None:
    """LLM 返回格式不对：容错处理，不崩。

    返回一个 course_confidence 是字符串、knowledge_points 混入非法项的 JSON。
    """
    mid = _make_material()

    fake = FakeLLM({
        "course_name": "商法",
        "course_confidence": "not-a-number",   # 应该是数字
        "knowledge_points": [
            {"name": "归责原则", "confidence": 0.9},
            "这不是字典",                       # 非法项
            {"name": "", "confidence": 0.5},   # 空名
            {"confidence": 0.8},                # 缺 name
        ],
        "reasoning": None,
    })

    result = material_classifier.classify_material(
        material_id=mid,
        sample_text=SAMPLE_TEXT,
        llm=fake,
    )

    # 不该崩，能成功
    assert result["success"] is True
    # 置信度转成 0（因为 "not-a-number" 转不了）
    assert result["course_confidence"] == 0.0
    # 只保留合法的那一个知识点
    assert len(result["knowledge_points"]) == 1
    assert result["knowledge_points"][0]["name"] == "归责原则"


def test_classify_confidence_clamped(temp_db) -> None:
    """置信度超出范围：截到 0~1。"""
    mid = _make_material()
    fake = FakeLLM({
        "course_name": "商法",
        "course_confidence": 2.5,   # 超出
        "knowledge_points": [],
        "reasoning": "",
    })

    result = material_classifier.classify_material(mid, SAMPLE_TEXT, llm=fake)
    assert result["course_confidence"] == 1.0


# ==============================================================
# apply_suggestion 测试
# ==============================================================
def test_apply_suggestion_creates_course(temp_db) -> None:
    """应用建议时课程不存在：应该自动建。"""
    mid = _make_material()
    fake = FakeLLM({
        "course_name": "新课程_测试",
        "course_confidence": 0.9,
        "knowledge_points": [
            {"name": "知识点A", "confidence": 0.9},
            {"name": "知识点B", "confidence": 0.9},
        ],
        "reasoning": "",
    })

    material_classifier.classify_material(mid, SAMPLE_TEXT, llm=fake)
    result = material_classifier.apply_suggestion(mid, confirmed_by="test")

    assert result["success"] is True
    assert result["created_course"] is True
    assert result["course_id"] is not None

    # 课程真的建了
    c = course.get_by_name("新课程_测试")
    assert c is not None
    assert c["id"] == result["course_id"]

    # 知识点建了
    kps = knowledge_point.list_by_course(result["course_id"], use_cache=False)
    assert len(kps) == 2

    # 资料关联了
    material = material_store.get_by_id(mid)
    assert material["course_id"] == result["course_id"]
    assert material["detection_status"] == material_store.STATUS_CONFIRMED


def test_apply_suggestion_reuses_existing_course(temp_db) -> None:
    """应用建议时课程已存在：复用，不重复建。"""
    # 先建一个课程
    existing_id = course.create(name="已存在的课程_测试")

    mid = _make_material(source_file="测试_资料2.pdf")
    fake = FakeLLM({
        "course_name": "已存在的课程_测试",
        "course_confidence": 0.9,
        "knowledge_points": [],
        "reasoning": "",
    })

    material_classifier.classify_material(mid, SAMPLE_TEXT, llm=fake)
    result = material_classifier.apply_suggestion(mid, confirmed_by="test")

    assert result["success"] is True
    assert result["created_course"] is False   # 没新建
    assert result["course_id"] == existing_id  # 用的是已存在的


def test_apply_suggestion_no_course_name(temp_db) -> None:
    """资料没有被识别出课程名：应用建议应失败。"""
    mid = _make_material()
    fake = FakeLLM({
        "course_name": "",
        "course_confidence": 0.0,
        "knowledge_points": [],
        "reasoning": "",
    })

    material_classifier.classify_material(mid, SAMPLE_TEXT, llm=fake)
    result = material_classifier.apply_suggestion(mid)

    assert result["success"] is False
    assert "没有" in result["error"] or "识别" in result["error"]


def test_apply_suggestion_no_auto_create(temp_db) -> None:
    """禁止自动建课程时，课程不存在就失败。"""
    mid = _make_material()
    fake = FakeLLM({
        "course_name": "不会自动建的课程",
        "course_confidence": 0.9,
        "knowledge_points": [],
        "reasoning": "",
    })

    material_classifier.classify_material(mid, SAMPLE_TEXT, llm=fake)
    result = material_classifier.apply_suggestion(mid, create_missing_course=False)

    assert result["success"] is False
    assert "不存在" in result["error"]