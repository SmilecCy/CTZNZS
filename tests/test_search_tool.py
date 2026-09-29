# -*- coding: utf-8 -*-
"""搜索工具的单元测试。

【测试目标】

    1. 未配置 API Key 时返回空列表，不抛异常
    2. 空查询词返回空列表
    3. 每次调用都写审计日志（成功与失败都写）
    4. 博查返回解析正确（模拟各种响应结构）
    5. build_query 拼的查询词符合预期

【测试策略】

    用 monkeypatch 替换 httpx.Client，模拟博查 API 的响应。
    绝不真的发 HTTP 请求。
"""

from __future__ import annotations

import pytest

from app.ai import search_tool


# ==============================================================
# 假 httpx 客户端
# ==============================================================
class FakeResponse:
    """假 HTTP 响应。"""

    def __init__(self, json_data: dict, status_code: int = 200) -> None:
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class FakeHttpxClient:
    """假 httpx.Client，上下文管理器协议 + post 方法。

    【为什么实现 __enter__/__exit__】
        search_tool 用的是 with httpx.Client(...) as client: 这种写法，
        假类必须支持上下文管理器协议。
    """

    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers=None, json=None):
        return self.response


def _patch_httpx(monkeypatch, response_data: dict, status_code: int = 200) -> None:
    """把 httpx.Client 替换成假客户端。"""
    def _fake_client(*args, **kwargs):
        return FakeHttpxClient(FakeResponse(response_data, status_code))

    monkeypatch.setattr("app.ai.search_tool.httpx.Client", _fake_client)


def _patch_api_key(monkeypatch, key: str = "fake-key") -> None:
    """把 BOCHA_API_KEY 替换成测试值。"""
    monkeypatch.setattr("app.ai.search_tool.BOCHA_API_KEY", key)


# ==============================================================
# 未配置 Key
# ==============================================================
def test_search_returns_empty_when_not_configured(temp_db, monkeypatch) -> None:
    """未配置 Key：返回空列表，不抛异常。"""
    monkeypatch.setattr("app.ai.search_tool.BOCHA_API_KEY", "")

    results = search_tool.search("测试查询")
    assert results == []


def test_search_logs_when_not_configured(temp_db, monkeypatch) -> None:
    """未配置 Key：仍然写审计日志（失败记录）。"""
    monkeypatch.setattr("app.ai.search_tool.BOCHA_API_KEY", "")

    search_tool.search("测试", purpose="test_purpose")

    from app.database import connection as db_mysql
    row = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n FROM search_call_log WHERE purpose = %s",
        ("test_purpose",),
    )
    assert row["n"] >= 1


# ==============================================================
# 空查询
# ==============================================================
def test_search_returns_empty_on_blank_query(temp_db, monkeypatch) -> None:
    """空查询词：返回空列表。"""
    _patch_api_key(monkeypatch)
    assert search_tool.search("") == []
    assert search_tool.search("   ") == []


# ==============================================================
# 正常搜索
# ==============================================================
def test_search_parses_results(temp_db, monkeypatch) -> None:
    """正常返回：正确解析结果。"""
    _patch_api_key(monkeypatch)
    _patch_httpx(monkeypatch, {
        "code": 200,
        "data": {
            "webPages": {
                "value": [
                    {"name": "结果1", "url": "https://a.com", "summary": "摘要1"},
                    {"name": "结果2", "url": "https://b.com", "snippet": "摘要2"},
                ]
            }
        }
    })

    results = search_tool.search("测试")
    assert len(results) == 2
    assert results[0]["title"] == "结果1"
    assert results[0]["url"] == "https://a.com"
    assert results[0]["snippet"] == "摘要1"
    assert results[1]["title"] == "结果2"
    assert results[1]["snippet"] == "摘要2"   # snippet 兜底字段


def test_search_logs_success(temp_db, monkeypatch) -> None:
    """成功调用写审计日志。"""
    _patch_api_key(monkeypatch)
    _patch_httpx(monkeypatch, {
        "data": {"webPages": {"value": [{"name": "x", "summary": "y"}]}}
    })

    search_tool.search("测试", purpose="success_test")

    from app.database import connection as db_mysql
    row = db_mysql.fetch_one(
        "SELECT success, result_count FROM search_call_log WHERE purpose = %s",
        ("success_test",),
    )
    assert row["success"] == 1
    assert row["result_count"] == 1


# ==============================================================
# 异常响应
# ==============================================================
def test_search_handles_http_error(temp_db, monkeypatch) -> None:
    """HTTP 错误：返回空列表，记失败日志。"""
    _patch_api_key(monkeypatch)
    _patch_httpx(monkeypatch, {}, status_code=500)

    results = search_tool.search("测试", purpose="error_test")
    assert results == []

    from app.database import connection as db_mysql
    row = db_mysql.fetch_one(
        "SELECT success FROM search_call_log WHERE purpose = %s",
        ("error_test",),
    )
    assert row["success"] == 0


def test_search_handles_malformed_response(temp_db, monkeypatch) -> None:
    """响应结构不对：返回空列表，不抛异常。"""
    _patch_api_key(monkeypatch)
    _patch_httpx(monkeypatch, {"unexpected": "structure"})

    results = search_tool.search("测试")
    assert results == []


def test_search_handles_empty_results(temp_db, monkeypatch) -> None:
    """返回空结果列表。"""
    _patch_api_key(monkeypatch)
    _patch_httpx(monkeypatch, {"data": {"webPages": {"value": []}}})

    results = search_tool.search("测试")
    assert results == []


def test_search_skips_invalid_items(temp_db, monkeypatch) -> None:
    """结果里混入非法项：跳过它，处理合法的。"""
    _patch_api_key(monkeypatch)
    _patch_httpx(monkeypatch, {
        "data": {
            "webPages": {
                "value": [
                    "这不是字典",
                    None,
                    {"name": "有效结果", "summary": "摘要"},
                    {"name": "", "summary": ""},   # 全空，跳过
                ]
            }
        }
    })

    results = search_tool.search("测试")
    # 只有第 3 项是有效的
    assert len(results) == 1
    assert results[0]["title"] == "有效结果"


# ==============================================================
# build_query
# ==============================================================
def test_build_query_short_answer() -> None:
    """简答题的查询词。"""
    q = search_tool.build_query("商法", "归责原则", "简答")
    assert "商法" in q
    assert "归责原则" in q
    assert "简答题" in q


def test_build_query_choice() -> None:
    """选择题的查询词。"""
    q = search_tool.build_query("习概", "中国式现代化", "选择")
    assert "选择题" in q


# ==============================================================
# is_configured
# ==============================================================
def test_is_configured_false(monkeypatch) -> None:
    monkeypatch.setattr("app.ai.search_tool.BOCHA_API_KEY", "")
    assert search_tool.is_configured() is False


def test_is_configured_true(monkeypatch) -> None:
    monkeypatch.setattr("app.ai.search_tool.BOCHA_API_KEY", "sk-test")
    assert search_tool.is_configured() is True