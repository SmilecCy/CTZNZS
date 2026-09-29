# -*- coding: utf-8 -*-
"""资料合并的单元测试。

【测试目标】

    1. 把多份资料合并到同一课程 → 都关联上
    2. 资料的知识点被合并到课程（自动去重）
    3. 目标课程不存在 → 返回失败
    4. 资料已经在该课程下 → 跳过（不报错，但记在 failed 里）
    5. 按建议自动分组：相同建议名归一组，不同的分开
    6. 部分失败不影响其他（单份失败不连坐整批）
"""

from __future__ import annotations

import json

import pytest

from app.database import (
    course,
    knowledge_point,
    material_classifier,
    material_merge,
    material_store,
)
from app.ai.llm_client import LLMResponse, LLMUsage


class FakeLLM:
    """假 LLM，返回预设 JSON。"""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.model = "fake"

    def chat_json(self, messages, temperature=None):
        response = LLMResponse(
            content=json.dumps(self.payload, ensure_ascii=False),
            usage=LLMUsage(model=self.model, prompt_tokens=10, completion_tokens=5),
        )
        return self.payload, response


def _make_material(file_name: str) -> int:
    """建一份测试资料。"""
    return material_store.create(source_file=file_name, kind="pdf")


def _classify(mid: int, course_name: str, kp_names: list[str]) -> None:
    """用假 LLM 识别一份资料。"""
    fake = FakeLLM({
        "course_name": course_name,
        "course_confidence": 0.9,
        "knowledge_points": [
            {"name": name, "confidence": 0.9} for name in kp_names
        ],
        "reasoning": "",
    })
    material_classifier.classify_material(mid, "测试文本", llm=fake)


# ==============================================================
# merge_materials_to_course 测试
# ==============================================================
def test_merge_two_materials(temp_db) -> None:
    """两份资料归到同一门课。"""
    mid_a = _make_material("测试_合并_资料1.pdf")
    mid_b = _make_material("测试_合并_资料2.pdf")

    _classify(mid_a, "合并目标课", ["知识点1"])
    _classify(mid_b, "合并目标课", ["知识点2"])

    target_id = course.create(name="合并目标课")

    result = material_merge.merge_materials_to_course(
        material_ids=[mid_a, mid_b],
        target_course_id=target_id,
        confirmed_by="test",
    )

    assert result["success"] is True
    assert result["merged_count"] == 2

    # 两份资料都关联了
    for mid in [mid_a, mid_b]:
        material = material_store.get_by_id(mid)
        assert material["course_id"] == target_id

    # 知识点被合并到课程
    kps = knowledge_point.list_by_course(target_id, use_cache=False)
    kp_names = {k["name"] for k in kps}
    assert "知识点1" in kp_names
    assert "知识点2" in kp_names


def test_merge_target_course_not_found(temp_db) -> None:
    """目标课程不存在：失败，但不抛异常。"""
    mid = _make_material("测试_合并_资料3.pdf")

    result = material_merge.merge_materials_to_course(
        material_ids=[mid],
        target_course_id=999999,
    )

    assert result["success"] is False
    assert len(result["failed"]) == 1
    assert "不存在" in result["failed"][0]["error"]


def test_merge_material_already_in_course(temp_db) -> None:
    """资料已经在目标课程下：跳过，记在 failed 里。"""
    target_id = course.create(name="已有课程_测试")
    mid = _make_material("测试_合并_资料4.pdf")

    # 直接把资料关联到课程（不用分类流程）
    material_store.confirm_classification(mid, target_id)

    result = material_merge.merge_materials_to_course(
        material_ids=[mid],
        target_course_id=target_id,
    )

    # 没有成功合并（因为已经在了）
    assert result["merged_count"] == 0
    assert len(result["failed"]) == 1
    assert "已经" in result["failed"][0]["error"]


def test_merge_partial_failure(temp_db) -> None:
    """一份成功一份失败：成功的要成功，失败的记下来。"""
    mid_a = _make_material("测试_合并_资料5.pdf")
    target_id = course.create(name="部分失败测试")

    _classify(mid_a, "部分失败测试", ["知识点X"])

    # 第二份资料不存在
    result = material_merge.merge_materials_to_course(
        material_ids=[mid_a, 999999],
        target_course_id=target_id,
    )

    assert result["merged_count"] == 1
    assert len(result["failed"]) == 1
    assert result["failed"][0]["material_id"] == 999999


def test_merge_without_knowledge_points(temp_db) -> None:
    """不合知识点时，只关联资料不建知识点。"""
    mid = _make_material("测试_合并_资料6.pdf")
    target_id = course.create(name="不建知识点的课")
    _classify(mid, "不建知识点的课", ["不该出现的知识点"])

    result = material_merge.merge_materials_to_course(
        material_ids=[mid],
        target_course_id=target_id,
        create_missing_knowledge_points=False,
    )

    assert result["merged_count"] == 1
    # 知识点没建
    kps = knowledge_point.list_by_course(target_id, use_cache=False)
    assert len(kps) == 0


# ==============================================================
# merge_by_suggested_course 测试
# ==============================================================
def test_auto_group_two_groups(temp_db) -> None:
    """按建议课程名分两组。"""
    mid_a = _make_material("测试_自动_商法1.pdf")
    mid_b = _make_material("测试_自动_商法2.pdf")
    mid_c = _make_material("测试_自动_民法1.pdf")

    _classify(mid_a, "自动分组_商法", ["知识点A"])
    _classify(mid_b, "自动分组_商法", ["知识点B"])
    _classify(mid_c, "自动分组_民法", ["知识点C"])

    result = material_merge.merge_by_suggested_course(
        material_ids=[mid_a, mid_b, mid_c],
        confirmed_by="test",
    )

    assert result["success"] is True
    assert len(result["groups"]) == 2
    assert "自动分组_商法" in result["groups"]
    assert "自动分组_民法" in result["groups"]

    # 商法组有 2 份
    assert len(result["groups"]["自动分组_商法"]["material_ids"]) == 2
    # 民法组有 1 份
    assert len(result["groups"]["自动分组_民法"]["material_ids"]) == 1


def test_auto_group_creates_courses(temp_db) -> None:
    """自动分组时，课程不存在应该建。"""
    mid = _make_material("测试_自动_新建课.pdf")
    _classify(mid, "自动新建_测试课", ["知识点X"])

    result = material_merge.merge_by_suggested_course([mid])

    assert result["groups"]["自动新建_测试课"]["created"] is True


def test_auto_group_reuses_courses(temp_db) -> None:
    """自动分组时，课程已存在应该复用。"""
    existing_id = course.create(name="自动复用_测试课")

    mid = _make_material("测试_自动_复用课.pdf")
    _classify(mid, "自动复用_测试课", [])

    result = material_merge.merge_by_suggested_course([mid])

    assert result["groups"]["自动复用_测试课"]["created"] is False
    assert result["groups"]["自动复用_测试课"]["course_id"] == existing_id


def test_auto_group_skips_unclassified(temp_db) -> None:
    """没有识别出课程名的资料：记在 errors 里，不参与分组。"""
    mid = _make_material("测试_自动_未识别.pdf")
    # 不给它分类

    result = material_merge.merge_by_suggested_course([mid])

    assert len(result["errors"]) == 1
    assert result["errors"][0]["material_id"] == mid


def test_auto_group_empty_input(temp_db) -> None:
    """空输入：返回空结果，不报错。"""
    result = material_merge.merge_by_suggested_course([])
    assert result["success"] is True
    assert result["groups"] == {}
    assert result["errors"] == []