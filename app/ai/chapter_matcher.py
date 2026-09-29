# -*- coding: utf-8 -*-
"""章节匹配器：将用户输入的自由文本匹配到数据库中的章节。

【用途】
    学生在练习页输入"第一章 商法概述"这类自然语言，
    系统需要把它匹配到数据库中的准确章节记录。

【匹配策略】
    1. 精确匹配：输入完全等于某个章节名
    2. 包含匹配：章节名包含输入（或反过来）
    3. LLM 匹配：模糊时调 LLM 判断（可选）

【为什么需要这个模块】
    用户输入是自由的，不可能要求他们记住精确的章节名。
    需要一个"模糊→精确"的桥梁。
"""

from __future__ import annotations

from typing import Any

from app.database.chapters import list_chapters, get_chapter_by_id


def match_chapter(
    user_input: str,
    course_id: int,
) -> dict[str, Any] | None:
    """将用户输入匹配到章节。

    Args:
        user_input: 用户输入的自然语言（如"第一章 商法概述"）。
        course_id: 课程 id。

    Returns:
        匹配到的章节 dict，如果匹配不到返回 None。
    """
    chapters = list_chapters(course_id)
    if not chapters:
        return None

    user_input = user_input.strip()
    if not user_input:
        return None

    user_lower = user_input.lower()

    # 策略1：精确匹配（忽略大小写）
    for ch in chapters:
        if ch["name"].strip().lower() == user_lower:
            return ch

    # 策略2：包含匹配（章节名包含用户输入，或用户输入包含章节名）
    for ch in chapters:
        ch_name = ch["name"].strip().lower()
        if ch_name in user_lower or user_lower in ch_name:
            return ch

    # 策略3：关键词匹配（去掉"第X章""第X节"等前缀后比对）
    import re
    cleaned_input = re.sub(
        r'^第[一二三四五六七八九十\d]+[章节]', '', user_input
    ).strip()
    for ch in chapters:
        ch_name = ch["name"].strip().lower()
        if cleaned_input.lower() in ch_name or ch_name in cleaned_input.lower():
            return ch

    return None


def generate_reply(
    user_input: str,
    chapter: dict[str, Any],
    llm_client: Any,
) -> str:
    """生成友好的章节确认回复。

    Args:
        user_input: 用户原始输入。
        chapter: 匹配到的章节 dict。
        llm_client: LLM 客户端。

    Returns:
        友好的回复文本。
    """
    from app.prompts.loader import load_rendered

    prompt = load_rendered("m3_all_chapter_reply_v0.1",
        user_input=user_input,
        chapter_name=chapter.get("name", ""),
        chapter_summary=chapter.get("summary") or "暂无摘要",
    )

    response = llm_client.chat([
        {"role": "system", "content": "你是一位友善的学习助手。"},
        {"role": "user", "content": prompt},
    ])

    return response.content


def log_chapter_request(
    user_id: int,
    course_id: int,
    chapter_id: int | None,
    input_text: str,
    matched_name: str | None,
    reply_text: str,
    llm_model: str = "",
    llm_tokens: int = 0,
) -> bool:
    """记录章节匹配请求到日志表。

    Args:
        user_id: 用户 id。
        course_id: 课程 id。
        chapter_id: 匹配到的章节 id，None 表示未匹配。
        input_text: 用户输入的文本。
        matched_name: 匹配到的章节名。
        reply_text: LLM 生成的回复文本。
        llm_model: 使用的模型名。
        llm_tokens: 消耗 token 数。

    Returns:
        是否成功。
    """
    from app.database import connection as db_mysql

    db_mysql.execute(
        "INSERT INTO chapter_request_log "
        "(user_id, course_id, chapter_id, input_text, matched_name, "
        "reply_text, llm_model, llm_tokens) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (user_id, course_id, chapter_id, input_text, matched_name,
         reply_text, llm_model, llm_tokens),
    )
    return True