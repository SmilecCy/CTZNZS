# -*- coding: utf-8 -*-
"""章节抽取器：从教材文本中抽取章节结构。

【用途】
    M0 解析完成后，教材的全文文本被抽出来了。
    这个模块用 LLM 从中识别章节标题和层级关系，
    生成章节树（章 → 节 → 小节 + 摘要）。

【调用时机】
    管理员在后台点"抽取章节"按钮时触发。
    只对教材（upload_type='textbook'）执行。
"""

from __future__ import annotations

import json
from typing import Any

from app.ai import llm_client as llm_client_module
from app.database.chapters import bulk_create_chapters, delete_all_chapters
from app.ai.llm_client import LLMClient


def extract_chapters_from_textbook(
    content: str,
    course_id: int,
    llm: LLMClient,
) -> list[dict[str, Any]]:
    """从教材全文抽章节。

    Args:
        content: 教材的全文文本。
        course_id: 目标课程 id。
        llm: LLM 客户端。

    Returns:
        章节树列表，每项 {"title": str, "summary": str, "children": [...]}。

    Raises:
        RuntimeError: LLM 返回无法解析。
    """
    del course_id  # 保留参数用于将来扩展

    # 限制输入长度
    max_chars = 30000
    if len(content) > max_chars:
        content = content[:max_chars]

    from app.prompts.loader import load_rendered

    prompt = load_rendered("m0_all_extract_chapters_v0.1", content=content[:30000])

    response = llm.chat([
        {"role": "system", "content": "你是一个教材章节抽取器。只返回 JSON。"},
        {"role": "user", "content": prompt},
    ])

    try:
        chapters = json.loads(response.content)
    except json.JSONDecodeError:
        chapters = llm_client_module.extract_json(response.content)

    # LLM 可能返回 {"chapters": [...]} 而非纯数组，自动解包
    if isinstance(chapters, dict):
        for key in ("chapters", "sections", "data", "result", "items"):
            if isinstance(chapters.get(key), list):
                chapters = chapters[key]
                break
        else:
            # 取第一个值是数组的键
            for val in chapters.values():
                if isinstance(val, list):
                    chapters = val
                    break

    if not isinstance(chapters, list):
        raise RuntimeError(f"LLM 返回的不是数组: {type(chapters).__name__}")

    return chapters


def save_chapters_to_db(
    course_id: int,
    chapters: list[dict[str, Any]],
) -> int:
    """将抽取的章节保存到数据库。

    先清空该课程现有章节，再批量写入。

    Args:
        course_id: 课程 id。
        chapters: 章节树列表。

    Returns:
        创建的章节总数。
    """
    # 清空现有章节
    delete_all_chapters(course_id)

    # 批量建
    ids = bulk_create_chapters(course_id, chapters)
    return len(ids)