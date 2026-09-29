# -*- coding: utf-8 -*-
"""M0 编排层：把"解析 → 切分 → 索引"串成一次可观察的入库流程。

【这个模块做什么】

    输入：一份文件（PDF / DOCX / 图片 / TXT）
    输出：IngestResult（含 chunk 列表、页数、警告、ParseResult 引用）

    流程（三步）：
      1. 解析（doc_parser）：把文件转成按页组织的文本
      2. 切分（chunker）：把文本切成带元数据的 chunk
      3. 索引（indexer）：把 chunk 向量化后写入 FAISS

【为什么不在这里登记数据库 / 生成 Markdown】

    本模块保持纯粹——只做"文件 → 向量"的转换，
    数据库操作和 Markdown 生成交给调用方（parse_worker）。
    这样：
      · pipeline 不依赖任何数据库
      · 单元测试不需要连数据库就能跑
      · 调用方可以根据结果做更多事（写任务进度、记录日志、生成 MD 等）

【调用方用法】

    from app.pipeline import orchestrator as pipeline

    result = pipeline.ingest_document(path, course="tort")

    # 调用方在外部处理：
    #   - 登记 materials 表
    #   - 教材：调用 save_to_markdown(result.parsed, course_id=..., material_id=...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.pipeline import indexer
from app.pipeline.chunker import Chunk, chunk_pages
from app.pipeline.doc_parser import ParseResult, parse_document

# 进度回调签名：(阶段名, 当前值, 总值)
ProgressCb = Callable[[str, int, int], None]


# ==============================================================
# 结果结构
# ==============================================================
@dataclass
class IngestResult:
    """一次资料入库的完整结果。"""

    source_file: str          # 原始文件名
    course: str               # 课程 key（过渡期用，将来改为 course_id）
    kind: str                 # 文件类型（pdf / docx / image / text）
    page_count: int           # 页数
    chunk_count: int          # 切分出的 chunk 数
    ocr_used: bool            # 是否走了 OCR 通道
    warnings: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    parsed: ParseResult | None = field(default=None)  # v2.2: 供调用方生成 Markdown

    @property
    def ok(self) -> bool:
        """是否成功产出了至少一个 chunk。"""
        return self.chunk_count > 0


# ==============================================================
# 主函数
# ==============================================================
def ingest_document(
    path: str | Path,
    course: str,
    progress: ProgressCb | None = None,
) -> IngestResult:
    """把一份资料完整地纳入 M0 索引。

    Args:
        path: 资料路径。
        course: 课程 key。
        progress: 可选进度回调，用于前端进度条。
            回调签名：``progress(stage: str, current: int, total: int)``。

    Returns:
        IngestResult。

    Raises:
        FileNotFoundError: 文件不存在。
        UnsupportedFormatError: 无法识别的格式。
        OcrUnavailableError: 需要 OCR 但未安装 PaddleOCR。
    """

    def _tick(stage: str, cur: int, total: int) -> None:
        """安全地调用进度回调。"""
        if progress is not None:
            progress(stage, cur, total)

    # ---------- 第 1 步：解析 ----------
    _tick("解析", 0, 1)
    parsed: ParseResult = parse_document(path)
    _tick("解析", 1, 1)

    # 从这里开始累积警告。
    # 解析阶段的警告先收进来，后面索引与清理阶段的警告再往后追加。
    warnings: list[str] = list(parsed.warnings)

    # ---------- 第 2 步：切分 ----------
    _tick("切分", 0, 1)
    chunks = chunk_pages(parsed.pages, source_file=parsed.source_file, course=course)
    _tick("切分", 1, 1)

    if not chunks:
        # 空文件或全是空白页：如实返回空结果，不报错
        return IngestResult(
            source_file=parsed.source_file,
            course=course,
            kind=parsed.kind.value,
            page_count=len(parsed.pages),
            chunk_count=0,
            ocr_used=any(p.ocr_used for p in parsed.pages),
            warnings=[*warnings, "未切分出任何有效文本，已跳过索引"],
        )

    # ---------- 第 3 步：向量化 + 索引 ----------
    # 【为什么要分批】
    #   向量化耗时最长（大文件可能几十秒），分批上报进度让界面不假死。
    #   每批 32 个 chunk 是经验值——批次太小进度回调太频繁，
    #   太大则进度更新不够细。
    #
    # 【为什么先写后清】
    #   新数据先落进去（upsert），清理只是收尾。
    #   顺序反过来（先清后写）会有个问题：删完之后任何一步失败，
    #   这份资料在库里就彻底消失了，只能整个重来。
    #   而 upsert 本来就按 id 覆盖，所以"先写"是安全且完整的。
    batch_size = 32
    total = len(chunks)
    for start in range(0, total, batch_size):
        batch = chunks[start:start + batch_size]
        indexer.index_chunks(batch, course=course)
        _tick("索引", min(start + batch_size, total), total)

    # ---------- 第 4 步：清理旧分段（可选，失败不影响结果）----------
    # 【为什么这是可选步骤】
    #   清理的作用只有一件事：删掉这次不再有的旧分段。
    #   比如同一份资料重新解析后，内容变短了，之前切出的第 8 段
    #   现在不再存在，要删掉。但这是"收尾"，不是"必须成功"。
    #
    # 【为什么失败不报错】
    #   新数据已经写进去了，是可用的。
    #   清理失败只影响"会不会留下一点旧残留"，不影响新数据的正确性。
    try:
        stale = indexer.prune_source(
            parsed.source_file,
            keep_ids={chunk.id for chunk in chunks},
        )
        if stale:
            warnings.append(f"清理了 {stale} 个旧版本的残留分段")
    except Exception as exc:  # noqa: BLE001 - 收尾动作，失败不影响可用性
        warnings.append(f"旧分段清理失败（不影响本次解析结果）：{exc}")

    # ---------- 完成 ----------
    ocr_used = any(p.ocr_used for p in parsed.pages)

    return IngestResult(
        source_file=parsed.source_file,
        course=course,
        kind=parsed.kind.value,
        page_count=len(parsed.pages),
        chunk_count=len(chunks),
        ocr_used=ocr_used,
        warnings=warnings,
        chunks=chunks,
        parsed=parsed,
    )