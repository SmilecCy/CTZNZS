# -*- coding: utf-8 -*-
"""M0-v0.1 结构化切分：把解析后的文本切成带元数据的 chunk。

切分策略（严格对应总控文档 M0"处理流程"第 4 步）：
    1. 优先按**标题层级**切分（第 X 章 / 一、 / （一） / 1. / Markdown #）;
    2. 同一标题内再按语义段落切分，chunk_size=500 字，overlap=50 字;
    3. 每个 chunk 保留元数据 {source_file, page, section_title, course}。

页码归属靠字符偏移映射：记录每个字符属于原文档第几行、第几页，
切分器给出 chunk 起始偏移后即可反查页码，因此"章节跨页"也不会串页。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from app.config import CHINESE_SEPARATORS, CHUNK_OVERLAP, CHUNK_SIZE
from app.pipeline.doc_parser import ExtractedPage

# ---------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------


@dataclass
class Chunk:
    """一个可检索、可追溯的最小知识单元。"""

    id: str
    text: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转成总控文档约定的输出结构（不含 embedding，向量化在 indexer 完成）。"""
        return {"id": self.id, "text": self.text, "metadata": self.metadata}


# ---------------------------------------------------------------
# 标题识别
# ---------------------------------------------------------------
_HEADING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^#{1,6}\s+\S"),                                  # Markdown 标题
    re.compile(r"^第[一二三四五六七八九十百零\d]+[章节讲篇部分]"),  # 第一章 / 第3节
    re.compile(r"^[一二三四五六七八九十]+、"),                     # 一、
    re.compile(r"^（[一二三四五六七八九十\d]+）"),                  # （一）
    re.compile(r"^\d+(\.\d+)*[、.．]\s*\S"),                       # 1. / 1.2.
]

_HEADING_MAX_LEN = 40  # 超过这个长度基本是正文，不是标题


def looks_like_heading(line: str) -> bool:
    """判断一行是否像标题。"""
    s = line.strip()
    if not s or len(s) > _HEADING_MAX_LEN:
        return False
    # 标题通常不以句号结尾
    if s.endswith("。"):
        return False
    return any(p.match(s) for p in _HEADING_PATTERNS)


# ---------------------------------------------------------------
# 内部：把页文本摊平成 (行, 页) 序列
# ---------------------------------------------------------------
@dataclass
class _Line:
    text: str
    page: int


def _flatten(pages: Iterable[ExtractedPage]) -> list[_Line]:
    """把按页组织的文本摊平成带页码的行序列。"""
    lines: list[_Line] = []
    for page in pages:
        for raw in page.text.split("\n"):
            lines.append(_Line(text=raw, page=page.page))
    return lines


@dataclass
class _Section:
    """一个标题下的完整内容。"""

    title: str
    lines: list[_Line] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(ln.text for ln in self.lines if ln.text.strip())


def _split_into_sections(lines: list[_Line], default_title: str) -> list[_Section]:
    """按标题把行序列切成若干 section。

    标题行自身并入该 section 的正文开头，保证 chunk 里能看到上下文标题。
    """
    sections: list[_Section] = []
    current = _Section(title=default_title)

    for line in lines:
        if looks_like_heading(line.text):
            if current.text.strip():
                sections.append(current)
            current = _Section(title=line.text.strip().lstrip("# ").strip())
            current.lines.append(line)
        else:
            current.lines.append(line)

    if current.text.strip():
        sections.append(current)
    return sections or [_Section(title=default_title, lines=lines)]


# ---------------------------------------------------------------
# 语义切分（LangChain 优先，缺失时退化到内置实现）
# ---------------------------------------------------------------
def _split_text(text: str) -> list[tuple[str, int]]:
    """把一段文本切成 (片段, 起始偏移) 列表。

    优先使用 LangChain 的 RecursiveCharacterTextSplitter；
    若环境未安装，则退化为内置的段落感知切分，行为保持一致。
    """
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:  # pragma: no cover - 取决于运行环境
        return _fallback_split(text)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=CHINESE_SEPARATORS,
        keep_separator=True,
        length_function=len,
        add_start_index=True,   # 关键：让每个 chunk 带 start_index，才能反查页码
    )
    docs = splitter.create_documents([text])
    return [(d.page_content, int(d.metadata.get("start_index", 0))) for d in docs]


def _fallback_split(text: str) -> list[tuple[str, int]]:
    """内置切分实现：按标点边界累积到 chunk_size，并保留 overlap。"""
    if not text:
        return []

    results: list[tuple[str, int]] = []
    start = 0
    n = len(text)

    while start < n:
        end = min(start + CHUNK_SIZE, n)
        if end < n:
            # 从 end 往回找最近的句子边界，避免把句子劈开
            for punct in ("。", "；", "\n", "，"):
                pos = text.rfind(punct, start + CHUNK_SIZE // 2, end)
                if pos != -1:
                    end = pos + 1
                    break
        results.append((text[start:end], start))
        if end >= n:
            break
        start = max(end - CHUNK_OVERLAP, start + 1)

    return results


# ---------------------------------------------------------------
# 偏移 -> 页码
# ---------------------------------------------------------------
def _page_of_offset(lines: list[_Line], offset: int) -> int:
    """把 chunk 在 section 内的字符偏移换算成原文档页码。"""
    cursor = 0
    for line in lines:
        cursor += len(line.text) + 1  # +1 为 join 时的换行符
        if offset < cursor:
            return line.page
    return lines[-1].page if lines else 1


# ---------------------------------------------------------------
# 对外主函数
# ---------------------------------------------------------------
def slugify(name: str) -> str:
    """把文件名压成适合做 id 前缀的短标识。

    公开函数（原来的私有名 ``_slug``）：chunk id 由它生成，
    而"这道题来自哪份资料"要靠比对这段前缀来判断，
    所以外部模块也需要用它，不能藏起来。
    """
    stem = re.sub(r"\.[^.]+$", "", name)
    stem = re.sub(r"[^\w一-鿿]+", "_", stem).strip("_")
    return stem or "doc"


def chunk_pages(
    pages: list[ExtractedPage],
    source_file: str,
    course: str,
    default_section: str = "全文",
) -> list[Chunk]:
    """把解析结果切成带完整元数据的 chunk 列表。

    Args:
        pages: doc_parser 产出的按页文本。
        source_file: 原始文件名，写入元数据用于追溯。
        course: 课程 key（如 "tort" / "xigai"）。
        default_section: 没有标题时使用的章节名。

    Returns:
        Chunk 列表，id 形如 ``商法讲义_0001``，全局唯一。
    """
    lines = _flatten(pages)
    sections = _split_into_sections(lines, default_section)

    prefix = slugify(source_file)
    chunks: list[Chunk] = []
    counter = 0

    for section in sections:
        body = "\n".join(ln.text for ln in section.lines)
        for piece, offset in _split_text(body):
            if not piece.strip():
                continue
            counter += 1
            chunks.append(
                Chunk(
                    id=f"{prefix}_{counter:04d}",
                    text=piece.strip(),
                    metadata={
                        "source_file": source_file,
                        "page": _page_of_offset(section.lines, offset),
                        "section_title": section.title,
                        "course": course,
                    },
                )
            )

    return chunks