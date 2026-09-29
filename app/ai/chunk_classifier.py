# -*- coding: utf-8 -*-
"""Chunk 章节分类器：将附属资料的 chunk 归类到对应章节。

【用途】
    附属资料（讲义、真题等）解析后切成了 chunk。
    这个模块用 LLM 判断每个 chunk 属于哪个章节，
    结果写入 chunk_chapter_map 表。

【调用时机】
    管理员在后台点"按章节分类"按钮时触发。
    只对附属资料（upload_type='supplement'）执行，
    且要求该课程已有章节（否则无法分类）。
"""

from __future__ import annotations

from typing import Any

from app.database import connection as db_mysql
from app.ai import llm_client as llm_client_module
from app.database.chapters import list_chapters
from app.ai.llm_client import LLMClient


def classify_chunks_to_chapters(
    material_id: int,
    course_id: int,
    chunks: list[dict[str, Any]],
    llm: LLMClient,
) -> list[dict[str, Any]]:
    """将一个资料的所有 chunk 分类到章节。

    Args:
        material_id: 资料 id。
        course_id: 课程 id。
        chunks: chunk 列表，每项 {"chunk_id": str, "text": str}。
        llm: LLM 客户端。

    Returns:
        分类结果列表。
    """
    del material_id  # 保留参数用于将来扩展

    chapters = list_chapters(course_id)
    if not chapters:
        raise RuntimeError("该课程还没有章节，请先上传教材并抽取章节")

    from app.prompts.loader import load_rendered

    # 构建章节列表描述
    chapters_desc = "\n".join(
        f"  [{ch['id']}] {ch['name']}" for ch in chapters
    )

    results: list[dict[str, Any]] = []
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id", "")
        text = chunk.get("text", "")

        if not text.strip():
            results.append({
                "chunk_id": chunk_id,
                "chapter_id": None,
                "confidence": 0.0,
                "reasoning": "空文本",
            })
            continue

        prompt = load_rendered("m0_all_classify_to_chapters_v0.1",
            chapters=chapters_desc,
            chunk_text=text[:4000],
        )

        try:
            response = llm.chat([
                {"role": "system", "content": "你是一个资料章节分类器。只返回 JSON。"},
                {"role": "user", "content": prompt},
            ])
            parsed = llm_client_module.extract_json(response.content)
            results.append({
                "chunk_id": chunk_id,
                "chapter_id": parsed.get("chapter_id") if isinstance(parsed, dict) else None,
                "confidence": parsed.get("confidence", 0.0) if isinstance(parsed, dict) else 0.0,
                "reasoning": parsed.get("reasoning", "") if isinstance(parsed, dict) else "",
            })
        except Exception as e:
            results.append({
                "chunk_id": chunk_id,
                "chapter_id": None,
                "confidence": 0.0,
                "reasoning": f"分类失败: {e}",
            })

    return results


def save_classification_results(
    material_id: int,
    results: list[dict[str, Any]],
) -> int:
    """将分类结果写入 chunk_chapter_map。

    Args:
        material_id: 资料 id。
        results: 分类结果列表。

    Returns:
        写入的记录数。
    """
    # 删除旧结果
    db_mysql.execute(
        "DELETE FROM chunk_chapter_map WHERE material_id = %s",
        (material_id,),
    )

    count = 0
    for r in results:
        chunk_id = r.get("chunk_id")
        if not chunk_id:
            continue

        db_mysql.execute(
            "INSERT INTO chunk_chapter_map "
            "(chunk_id, chapter_id, material_id, confidence, reasoning, is_confirmed) "
            "VALUES (%s, %s, %s, %s, %s, 1)",
            (chunk_id, r.get("chapter_id"), material_id, r.get("confidence", 0.0), r.get("reasoning", "")),
        )
        count += 1

    # 标记资料已分类
    db_mysql.execute(
        "UPDATE materials SET chapter_classified = 1 WHERE id = %s",
        (material_id,),
    )

    return count


def get_classification_by_material(
    material_id: int,
) -> list[dict[str, Any]]:
    """查询某资料的 chunk-章节分类结果。"""
    return db_mysql.fetch_all(
        "SELECT ccm.*, kp.name AS chapter_name "
        "FROM chunk_chapter_map ccm "
        "LEFT JOIN knowledge_points kp ON ccm.chapter_id = kp.id "
        "WHERE ccm.material_id = %s "
        "ORDER BY ccm.id",
        (material_id,),
    )


def update_chunk_chapter(
    chunk_id: str,
    chapter_id: int,
) -> bool:
    """手动修改某个 chunk 的章节归属。"""
    db_mysql.execute(
        "UPDATE chunk_chapter_map SET chapter_id = %s, is_confirmed = 1 "
        "WHERE chunk_id = %s",
        (chapter_id, chunk_id),
    )
    return True


def confirm_chunk(chunk_id: str) -> bool:
    """确认某个 chunk 的分类。"""
    db_mysql.execute(
        "UPDATE chunk_chapter_map SET is_confirmed = 1 WHERE chunk_id = %s",
        (chunk_id,),
    )
    return True