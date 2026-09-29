# -*- coding: utf-8 -*-
"""搜索引擎工具：博查（Bocha）API 封装。

【为什么用博查而不是 Google/Bing/Serper】

    1. **国内可直连** —— Google、Bing 都要代理，开发环境很麻烦
    2. **便宜** —— 有免费额度，付费也比 Serper 便宜
    3. **专为中文优化** —— 中文搜索质量好
    4. **API 简单** —— 一次 POST 就返回 JSON

【这个模块做什么】

    输入：一个查询词
    输出：[{"title": ..., "url": ..., "snippet": ...}, ...]

    并把每次调用写入 search_call_log 表（审计）。

【三条硬约束】

    1. **不抛异常** —— 搜索失败时返回空列表 + 记录错误。
       搜索是"增强"，不是"前提"。资料不足时搜索挂了，
       题该生成不出来就生成不出来，但业务不能崩。

    2. **每次调用写审计** —— 搜索也是花钱的（虽然很少），
       成本审计要求记下来。

    3. **超时保护** —— 10 秒。搜索服务偶尔会慢，不能卡住整个出题流程。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import BOCHA_API_KEY, BOCHA_BASE_URL
from app.database import connection as db_mysql


# ==============================================================
# 配置
# ==============================================================
# 单次搜索的超时时间（秒）。
# 为什么是 10：搜索服务通常在 1~3 秒内返回，
# 10 秒是"极端情况"的上限。再长就会严重拖慢出题体验。
SEARCH_TIMEOUT = 10.0

# 默认返回条数。
# 为什么是 5：太多会稀释相关性（后面的结果通常不相关），
# 太少可能漏掉有用信息。
DEFAULT_TOP_K = 5


# ==============================================================
# 数据结构
# ==============================================================
@dataclass
class SearchResult:
    """一条搜索结果。"""

    title: str
    url: str
    snippet: str

    def to_dict(self) -> dict[str, str]:
        """转成字典，方便 JSON 序列化。"""
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


# ==============================================================
# 异常
# ==============================================================
class SearchError(RuntimeError):
    """搜索操作的统一异常基类。

    【注意】本模块的公开函数**不抛这个异常**。
        search() 遇到问题会返回空列表 + 记日志。
        定义这个类是为了将来可能需要区分错误类型时用。
    """


class SearchNotConfiguredError(SearchError):
    """未配置 API Key 时抛出（内部用，不往上抛）。"""


# ==============================================================
# 主函数
# ==============================================================
def search(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    purpose: str = "supplement_material",
    course_id: int | None = None,
    knowledge_point: str | None = None,
) -> list[dict[str, str]]:
    """搜索网络资料。

    Args:
        query: 搜索关键词。
        top_k: 返回条数。
        purpose: 用途标记（写入审计日志）。
            例如 supplement_material（补充资料）、verify_fact（核实事实）。
        course_id: 关联的课程 id（可为空）。
        knowledge_point: 关联的知识点（可为空）。

    Returns:
        搜索结果列表。每项是 {"title": ..., "url": ..., "snippet": ...}。

        **无论成功失败都返回列表**（失败时是空列表）。
        调用方不需要 try/except，只需检查列表是否为空。
    """
    # 检查配置
    if not BOCHA_API_KEY:
        _log_call(
            query=query,
            purpose=purpose,
            course_id=course_id,
            knowledge_point=knowledge_point,
            result_count=0,
            latency_ms=0,
            success=False,
            error="未配置 BOCHA_API_KEY",
        )
        return []

    # 检查查询词
    if not query or not query.strip():
        _log_call(
            query=query,
            purpose=purpose,
            course_id=course_id,
            knowledge_point=knowledge_point,
            result_count=0,
            latency_ms=0,
            success=False,
            error="查询词为空",
        )
        return []

    # 计时
    started = time.monotonic()

    try:
        results = _call_bocha(query.strip(), top_k)
        latency_ms = int((time.monotonic() - started) * 1000)

        _log_call(
            query=query,
            purpose=purpose,
            course_id=course_id,
            knowledge_point=knowledge_point,
            result_count=len(results),
            latency_ms=latency_ms,
            success=True,
            error=None,
        )
        return results

    except Exception as exc:  # noqa: BLE001 - 见模块 docstring：不抛异常
        latency_ms = int((time.monotonic() - started) * 1000)
        _log_call(
            query=query,
            purpose=purpose,
            course_id=course_id,
            knowledge_point=knowledge_point,
            result_count=0,
            latency_ms=latency_ms,
            success=False,
            error=f"{type(exc).__name__}: {exc}"[:500],
        )
        return []


def is_configured() -> bool:
    """是否已配置博查 API Key。

    【用途】界面显示"搜索功能是否可用"、验证脚本决定要不要跑真搜索。
    """
    return bool(BOCHA_API_KEY)


# ==============================================================
# 内部：实际调 API
# ==============================================================
def _call_bocha(query: str, top_k: int) -> list[dict[str, str]]:
    """调博查 API。

    【博查 API 协议】
        POST https://api.bochaai.com/v1/web-search
        Headers:
          Authorization: Bearer {API_KEY}
          Content-Type: application/json
        Body:
          {"query": "关键词", "count": 5, "summary": true}

        返回 JSON：
          {"code": 200, "data": {"webPages": {"value": [{"name": ..., "url": ..., "snippet": ...}]}}}

    【为什么要独立一个函数】
        把"构造请求 + 解析响应"放在一起，
        出问题时日志更清晰（能看到具体是哪一步失败）。
    """
    headers = {
        "Authorization": f"Bearer {BOCHA_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "query": query,
        "count": min(top_k, 10),   # 博查最多返回 10 条
        "summary": True,           # 让博查返回摘要（比纯 snippet 好）
    }

    with httpx.Client(timeout=SEARCH_TIMEOUT) as client:
        response = client.post(BOCHA_BASE_URL, headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()

    return _parse_bocha_response(payload)


def _parse_bocha_response(payload: Any) -> list[dict[str, str]]:
    """解析博查返回的 JSON。

    【为什么要容错】
        博查的返回结构在不同版本有细微差别：
          - 有的版本结果在 data.webPages.value
          - 有的在 data.webPages
          - 有的直接是 data.pages

        与其猜用户装的是哪版，不如都试一遍。

    Args:
        payload: 博查返回的 JSON 对象。

    Returns:
        规范化后的结果列表。
    """
    if not isinstance(payload, dict):
        return []

    # 逐层找结果列表
    data = payload.get("data")
    if not isinstance(data, dict):
        return []

    web_pages = data.get("webPages")
    if not isinstance(web_pages, dict):
        return []

    items = web_pages.get("value") or web_pages.get("items") or []
    if not isinstance(items, list):
        return []

    results: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        title = str(item.get("name") or item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(
            item.get("summary") or item.get("snippet") or item.get("description") or ""
        ).strip()

        # 至少要有一个有用的字段
        if title or snippet:
            results.append({"title": title, "url": url, "snippet": snippet})

    return results


# ==============================================================
# 内部：写审计日志
# ==============================================================
def _log_call(
    query: str,
    purpose: str,
    course_id: int | None,
    knowledge_point: str | None,
    result_count: int,
    latency_ms: int,
    success: bool,
    error: str | None,
) -> None:
    """写一条 search_call_log。

    【为什么记失败也写】
        搜索失败也要能审计（是密钥错了还是网络问题还是查询词有问题）。
        只看成功的记录，排查时缺一半信息。
    """
    try:
        db_mysql.execute(
            "INSERT INTO search_call_log "
            "(purpose, course_id, knowledge_point, query, engine, "
            "result_count, latency_ms, success, error) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                purpose,
                course_id,
                knowledge_point,
                query[:500],   # 截断防止超长
                "bocha",
                result_count,
                latency_ms,
                int(success),
                error,
            ),
        )
    except Exception:  # noqa: BLE001 - 记日志失败不该影响主流程
        pass


# ==============================================================
# 业务便捷函数
# ==============================================================
def build_query(
    course_name: str,
    knowledge_point: str,
    question_type: str,
) -> str:
    """按约定拼搜索关键词。

    【为什么要拼得这么具体】
        泛泛地搜"归责原则"会返回百科、论文、新闻，噪音大。
        加上课程名 + 题型 + "真题"，能搜到更相关的教辅材料。

    Args:
        course_name: 课程名（如"商法"）。
        knowledge_point: 知识点（如"归责原则"）。
        question_type: 题型（"简答" / "选择"）。

    Returns:
        搜索关键词。
    """
    # 题型后缀
    suffix = "简答题" if question_type == "简答" else "选择题"

    return f"{course_name} {knowledge_point} {suffix} 真题"