# -*- coding: utf-8 -*-
"""M0-v0.1 资料解析层：格式识别 → 文本抽取 → 清洗。

本模块只负责"把任意格式的原始资料变成干净的、按页组织的文本"，
不做切分、不做向量化——那两件事分别属于 chunker / indexer。

依赖采用**惰性导入**：只有真正处理到某类文件时才导入对应库，
因此即使环境里没装 PaddleOCR，纯文本与文本型 PDF 仍可正常工作。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------


class DocumentKind(str, Enum):
    """资料的真实类型（由扩展名 + 内容嗅探共同判定）。"""

    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    IMAGE = "image"
    TEXT = "text"
    UNKNOWN = "unknown"


@dataclass
class ExtractedPage:
    """一页（或一个逻辑段）抽出的文本。

    Attributes:
        page: 页码，从 1 开始；对不分页的格式统一记为 1。
        text: 原始抽取文本（尚未清洗）。
        ocr_used: 该页是否走了 OCR 通道。
    """

    page: int
    text: str
    ocr_used: bool = False


@dataclass
class ParseResult:
    """一次完整解析的结果。"""

    source_file: str
    kind: DocumentKind
    pages: list[ExtractedPage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """所有页按顺序拼接（清洗后）。"""
        return "\n\n".join(p.text for p in self.pages if p.text.strip())


# ---------------------------------------------------------------
# 异常
# ---------------------------------------------------------------
class UnsupportedFormatError(ValueError):
    """遇到不支持的扩展名时抛出。"""


class OcrUnavailableError(RuntimeError):
    """需要 OCR 但环境未安装 PaddleOCR 时抛出。"""


# ---------------------------------------------------------------
# 一、格式识别
# ---------------------------------------------------------------
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
_TEXT_EXTS = {".txt", ".md"}
_DOCX_EXTS = {".docx"}

# PDF 若平均每页可抽出字符数低于此值，判定为扫描件
_SCANNED_PDF_CHARS_PER_PAGE = 20


def sniff_kind(path: str | Path) -> DocumentKind:
    """判定文件的真实类型。

    先看扩展名，再做轻量内容嗅探（magic number），两者冲突时以内容为准。

    Args:
        path: 文件路径。

    Returns:
        DocumentKind 枚举值。
    """
    p = Path(path)
    ext = p.suffix.lower()

    if ext == ".pdf":
        return DocumentKind.PDF
    if ext == ".doc":
        return DocumentKind.DOC
    if ext in _DOCX_EXTS:
        return DocumentKind.DOCX
    if ext in _IMAGE_EXTS:
        return DocumentKind.IMAGE
    if ext in _TEXT_EXTS:
        return DocumentKind.TEXT

    # 扩展名不认识时嗅探文件头
    head = p.read_bytes()[:8]
    if head.startswith(b"%PDF"):
        return DocumentKind.PDF
    if head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8\xff"):
        return DocumentKind.IMAGE
    if head.startswith(b"PK\x03\x04"):
        return DocumentKind.DOCX  # docx 本质是 zip
    if head[:4] == b"\xd0\xcf\x11\xe0":
        return DocumentKind.DOC  # OLE2 容器（.doc / .xls / .ppt 共用）

    return DocumentKind.UNKNOWN


# ---------------------------------------------------------------
# 二、文本清洗
# ---------------------------------------------------------------
_RE_MULTI_BLANK = re.compile(r"\n{3,}")
_RE_TRAIL_SPACE = re.compile(r"[ \t　]+$", re.MULTILINE)
_RE_LEAD_SPACE = re.compile(r"^[ \t　]+", re.MULTILINE)
# 中文断行：上一行以中文/逗号结尾且下一行以中文开头 → 合并（中间无标点说明是被硬折行）
_RE_CN_HYPHEN_BREAK = re.compile(r"([一-鿿，、；：])\n(?=[一-鿿])")
# 英文断字：word-\nword → wordword
_RE_EN_HYPHEN_BREAK = re.compile(r"([A-Za-z])-\n([a-z])")


def clean_text(raw: str) -> str:
    """对单页原始文本做清洗。

    规则：合并被硬折行拆断的中文句子、修复英文断字、
    去行首行尾空白、压缩连续空行。保留原意，不改写用词。

    Args:
        raw: 原始文本。

    Returns:
        清洗后的文本。
    """
    if not raw:
        return ""

    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ").replace("", "")   # 不换行空格 / BOM
    text = _RE_EN_HYPHEN_BREAK.sub(r"\1\2", text)
    text = _RE_CN_HYPHEN_BREAK.sub(r"\1", text)
    text = _RE_TRAIL_SPACE.sub("", text)
    text = _RE_LEAD_SPACE.sub("", text)
    text = _RE_MULTI_BLANK.sub("\n\n", text)
    return text.strip()


def strip_repeated_headers_footers(pages: list[ExtractedPage],
                                   min_ratio: float = 0.5) -> list[ExtractedPage]:
    """去掉跨页重复的页眉页脚。

    做法：统计每行在多少页出现过；出现比例 >= ``min_ratio`` 且长度 < 30
    的行视为页眉/页脚样板文字，从所有页中删除。

    Args:
        pages: 已抽取的页列表。
        min_ratio: 判定为"样板行"的出现比例阈值。

    Returns:
        处理后的页列表（原地修改 text，返回同一列表引用）。
    """
    if len(pages) < 3:
        return pages  # 页数太少，统计不可靠

    counter: dict[str, int] = {}
    for page in pages:
        for line in {ln.strip() for ln in page.text.split("\n") if ln.strip()}:
            counter[line] = counter.get(line, 0) + 1

    threshold = max(2, int(len(pages) * min_ratio))
    boilerplate = {ln for ln, n in counter.items() if n >= threshold and len(ln) < 30}
    if not boilerplate:
        return pages

    for page in pages:
        kept = [ln for ln in page.text.split("\n") if ln.strip() not in boilerplate]
        page.text = clean_text("\n".join(kept))
    return pages


# ---------------------------------------------------------------
# 三、各格式抽取器
# ---------------------------------------------------------------
def _extract_pdf(path: Path) -> tuple[list[ExtractedPage], list[str]]:
    """抽取 PDF。文本型走 PyMuPDF，扫描型自动转 OCR。"""
    import fitz  # PyMuPDF

    warnings: list[str] = []
    pages: list[ExtractedPage] = []

    with fitz.open(path) as doc:
        for idx, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            pages.append(ExtractedPage(page=idx, text=clean_text(text)))

    total_chars = sum(len(p.text) for p in pages)
    avg = total_chars / max(len(pages), 1)

    if pages and avg < _SCANNED_PDF_CHARS_PER_PAGE:
        warnings.append(f"检测到扫描型 PDF（平均 {avg:.1f} 字/页），已切换 OCR 通道")
        pages = _extract_pdf_via_ocr(path)

    return pages, warnings


def _extract_pdf_via_ocr(path: Path) -> list[ExtractedPage]:
    """把 PDF 每页栅格化后逐页 OCR。"""
    import fitz

    ocr = _get_ocr()
    results: list[ExtractedPage] = []
    with fitz.open(path) as doc:
        for idx, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            results.append(
                ExtractedPage(page=idx, text=clean_text(_ocr_png_bytes(ocr, img_bytes)),
                              ocr_used=True)
            )
    return results


def _extract_docx(path: Path) -> tuple[list[ExtractedPage], list[str]]:
    """抽取 DOCX：按文档顺序保留段落与表格内容。"""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(path))
    lines: list[str] = []

    # body 内按真实顺序遍历，保证表格不会跑到正文末尾
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            text = Paragraph(child, doc).text.strip()
            if text:
                lines.append(text)
        elif child.tag.endswith("}tbl"):
            lines.append(_table_to_markdown(Table(child, doc)))

    return [ExtractedPage(page=1, text=clean_text("\n".join(lines)))], []


def _extract_doc(path: Path) -> tuple[list[ExtractedPage], list[str]]:
    """抽取 .doc（OLE2 二进制格式）：读取原始字节并提取可读文本。

    .doc 是 Microsoft Word 97-2003 的私有二进制格式（OLE2 Compound Document），
    没有简单的标准库可以解析。这里采用启发式方法：
    逐偏移尝试 UTF-16LE → GBK 解码，选择 CJK 字符占比最高的片段作为结果。
    """
    warnings: list[str] = []
    data = path.read_bytes()
    size = len(data)

    if size < 1024:
        raise UnsupportedFormatError("文件过小，不是有效的 .doc 文件")

    candidates: list[tuple[int, str]] = []  # (cjk_count, text)

    search_chunk = min(size, 200000)
    step = 1024

    for offset in range(0, search_chunk, step):
        # 1) UTF-16LE 解码
        chunk = data[offset:size]
        try:
            text = chunk.decode("utf-16-le", errors="replace")
            cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
            if cjk > 20:
                cleaned = "".join(
                    c for c in text
                    if c == "\n" or c == "\r" or c == "\t" or ("\u0020" <= c <= "\uffff")
                )
                if cleaned.strip():
                    candidates.append((cjk, cleaned))
                    break  # UTF-16LE 命中即选最优
        except Exception:
            pass

        # 2) GBK 解码
        try:
            text = chunk.decode("gbk", errors="replace")
            cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
            if cjk > 20:
                cleaned = "".join(
                    c for c in text
                    if c == "\n" or c == "\r" or c == "\t" or ("\u0020" <= c <= "\uffff")
                )
                if cleaned.strip():
                    candidates.append((cjk, cleaned))
        except Exception:
            pass

    if not candidates:
        raise UnsupportedFormatError(
            "无法从 .doc 文件中提取 Unicode 文本。"
            "请尝试用 Word/WPS 将该文件另存为 .docx 格式后重新上传。"
        )

    best = max(candidates, key=lambda x: x[0])
    if len(best[1]) < 50:
        warnings.append("提取到的文本极少（可能为空白文档或非文本型 .doc）")

    return [ExtractedPage(page=1, text=clean_text(best[1]))], warnings


def _table_to_markdown(table: object) -> str:
    """把 python-docx 表格转成 Markdown 表格文本，避免表格内容丢失。"""
    rows: list[list[str]] = []
    for row in table.rows:  # type: ignore[attr-defined]
        cells = [c.text.strip().replace("\n", " ") for c in row.cells]
        rows.append(cells)
    if not rows:
        return ""
    header, *body = rows
    sep = ["---"] * len(header)
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join(sep) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(out)


def _extract_image(path: Path) -> tuple[list[ExtractedPage], list[str]]:
    """抽取图片：直接 OCR。"""
    ocr = _get_ocr()
    text = _ocr_png_bytes(ocr, path.read_bytes())
    return [ExtractedPage(page=1, text=clean_text(text), ocr_used=True)], []


def _extract_text(path: Path) -> tuple[list[ExtractedPage], list[str]]:
    """抽取纯文本：自动尝试 UTF-8 / GBK。"""
    for enc in ("utf-8", "gbk", "utf-16"):
        try:
            raw = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raw = path.read_text(encoding="utf-8", errors="ignore")

    # 按空行分段当作"页"的近似，便于后续按页追溯
    pages = [
        ExtractedPage(page=i, text=clean_text(block))
        for i, block in enumerate(re.split(r"\n\s*\n", raw), start=1)
        if block.strip()
    ]
    return pages or [ExtractedPage(page=1, text=clean_text(raw))], []


# ---------------------------------------------------------------
# 四、OCR（惰性单例）
# ---------------------------------------------------------------
_OCR_INSTANCE: object | None = None


def _build_ocr(factory: Callable[..., object]) -> object:
    """按构造函数的**实际签名**组装参数，兼容 PaddleOCR 2.x / 3.x。

    PaddleOCR 3.x 改过构造参数，硬编码任何一版的写法在另一版上都会直接报错：

        show_log         —— 3.x 删除（传了就是 "Unknown argument: show_log"）
        use_angle_cls    —— 3.x 改名为 use_textline_orientation

    所以这里先问一句"你到底接受哪些参数"，再按它的回答裁剪。
    拿不到签名时只传 ``lang``——这个参数两版都有，最保守也最安全。

    Args:
        factory: PaddleOCR 类（作为参数传入，方便测试时替换成假的）。

    Returns:
        构造好的 OCR 实例。
    """
    import inspect

    try:
        accepted = set(inspect.signature(factory.__init__).parameters)
    except (TypeError, ValueError):  # 拿不到签名（如 C 扩展），走最保守的路
        accepted = set()

    kwargs: dict = {"lang": "ch"}

    # 方向分类器换过名字，哪个在就用哪个
    for name in ("use_textline_orientation", "use_angle_cls"):
        if name in accepted:
            kwargs[name] = True
            break

    # show_log 只有旧版有；新版传了会直接抛 Unknown argument
    if "show_log" in accepted:
        kwargs["show_log"] = False

    return factory(**kwargs)


def _get_ocr() -> object:
    """获取（并缓存）PaddleOCR 实例。未安装时抛出可读错误。"""
    global _OCR_INSTANCE
    if _OCR_INSTANCE is not None:
        return _OCR_INSTANCE

    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:  # pragma: no cover - 取决于运行环境
        raise OcrUnavailableError(
            "需要 OCR 能力但未安装 PaddleOCR。请执行：\n"
            "    pip install paddleocr paddlepaddle"
        ) from exc

    try:
        _OCR_INSTANCE = _build_ocr(PaddleOCR)
    except Exception as exc:  # noqa: BLE001 - 要给用户可读的提示而不是原始堆栈
        raise OcrUnavailableError(
            f"PaddleOCR 初始化失败：{type(exc).__name__}: {exc}\n\n"
            "本模块已按构造函数的签名自动裁剪参数；如果仍报参数错误，"
            "说明这个版本的 API 又变了。请把下面的版本信息反馈给我：\n"
            "    python -c \"import paddleocr; print(paddleocr.__version__)\""
        ) from exc

    return _OCR_INSTANCE


def _extract_ocr_lines(result: object) -> list[str]:
    """从 PaddleOCR 的返回里取出文字行，兼容 2.x 与 3.x 两种结构。

    两版的返回长得完全不一样：:

        2.x:  [[ [box, (text, score)], ... ]]     嵌套列表
        3.x:  [ {"rec_texts": [...], ...} ]       字典

    与其猜用户装的是哪一版，不如把两种情况都处理掉——
    多写十行，换掉一整类"换个版本就崩"的问题。
    """
    lines: list[str] = []

    for block in result or []:
        # 3.x：字典，文字在 rec_texts 里
        if isinstance(block, dict):
            texts = block.get("rec_texts") or block.get("texts") or []
            lines.extend(str(t) for t in texts)
            continue

        # 2.x：列表，每一项是 [box, (text, score)]
        for item in block or []:
            try:
                lines.append(str(item[1][0]))
            except (IndexError, TypeError, KeyError):
                continue

    return [line for line in lines if line.strip()]


def _ocr_png_bytes(ocr: object, data: bytes) -> str:
    """对 PNG 字节流做 OCR，返回按行拼接的文本。"""
    import io

    import numpy as np
    from PIL import Image

    image = np.array(Image.open(io.BytesIO(data)).convert("RGB"))

    # 不传 cls 之类的额外参数：3.x 已经没有 cls，传了同样会报 Unknown argument。
    # 方向分类是在构造时开启的，调用时不需要再指定。
    result = ocr.ocr(image)  # type: ignore[attr-defined]
    return "\n".join(_extract_ocr_lines(result))


# ---------------------------------------------------------------
# 五、统一入口
# ---------------------------------------------------------------
_EXTRACTORS: dict[DocumentKind, Callable[[Path], tuple[list[ExtractedPage], list[str]]]] = {
    DocumentKind.PDF: _extract_pdf,
    DocumentKind.DOCX: _extract_docx,
    DocumentKind.DOC: _extract_doc,
    DocumentKind.IMAGE: _extract_image,
    DocumentKind.TEXT: _extract_text,
}


def parse_document(path: str | Path) -> ParseResult:
    """解析单个资料文件，返回结构化结果。

    Args:
        path: 资料文件路径。

    Returns:
        ParseResult，含按页组织的清洗后文本。

    Raises:
        FileNotFoundError: 文件不存在。
        UnsupportedFormatError: 无法识别的格式。
        OcrUnavailableError: 需要 OCR 但未安装 PaddleOCR。
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"资料文件不存在：{p}")

    kind = sniff_kind(p)
    if kind is DocumentKind.UNKNOWN:
        raise UnsupportedFormatError(
            f"不支持的文件格式：{p.name}（支持 pdf / docx / doc / jpg / png / txt / md）"
        )

    pages, warnings = _EXTRACTORS[kind](p)
    pages = strip_repeated_headers_footers(pages)

    empty_pages = sum(1 for pg in pages if not pg.text.strip())
    if empty_pages and empty_pages == len(pages):
        warnings.append("所有页均无有效文本，请确认文件是否为空或损坏")

    return ParseResult(source_file=p.name, kind=kind, pages=pages, warnings=warnings)


# ---------------------------------------------------------------
# 六、保存为 Markdown
# ---------------------------------------------------------------
def save_to_markdown(result: ParseResult,
                     output_dir: str | Path | None = None,
                     course_id: int | None = None,
                     material_id: int | None = None) -> Path:
    """将解析结果保存为 Markdown 文件。

    两种路径模式：

    - **v2.2 模式**（传入 course_id + material_id）：
      ``data/markdown/{course_id}/{material_id}.md``
      用于生产环境，路径稳定，不随文件名变化。

    - **兼容模式**（不传 course_id/material_id）：
      ``data/markdown/{stem}/{stem}.md``
      用于独立调用或测试场景。

    生成的 Markdown 格式：
        - 顶部为元信息（源文件、类型、页数等）
        - 每页以 ``## 第 N 页`` 为标题
        - OCR 页面会标注 ``*(OCR识别)*``
        - 警告信息附在文末

    Args:
        result: parse_document 返回的解析结果。
        output_dir: 可选，自定义输出根目录。默认使用 ``data/markdown/``。
        course_id: 课程 id（v2.2 路径模式）。
        material_id: 资料 id（v2.2 路径模式）。

    Returns:
        生成的 Markdown 文件路径。

    Raises:
        OSError: 目录创建或文件写入失败。
    """
    if output_dir is None:
        from app.config import MARKDOWN_DIR
        output_dir = Path(MARKDOWN_DIR)
    else:
        output_dir = Path(output_dir)

    if course_id is not None and material_id is not None:
        sub_dir = output_dir / str(course_id)
        sub_dir.mkdir(parents=True, exist_ok=True)
        md_path = sub_dir / f"{material_id}.md"
    else:
        stem = Path(result.source_file).stem
        sub_dir = output_dir / stem
        sub_dir.mkdir(parents=True, exist_ok=True)
        md_path = sub_dir / f"{stem}.md"

    lines: list[str] = []
    lines.append(f"# {result.source_file}")
    lines.append("")
    lines.append(f"- **类型**: {result.kind.value}")
    lines.append(f"- **页数**: {len(result.pages)}")
    if result.warnings:
        lines.append(f"- **警告**: {len(result.warnings)} 条（见文末）")
    lines.append("")
    lines.append("---")
    lines.append("")

    for page in result.pages:
        label = f"第 {page.page} 页"
        if page.ocr_used:
            label += " *(OCR识别)*"
        lines.append(f"## {label}")
        lines.append("")
        lines.append(page.text)
        lines.append("")

    if result.warnings:
        lines.append("---")
        lines.append("")
        lines.append("## 解析警告")
        lines.append("")
        for w in result.warnings:
            lines.append(f"- {w}")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path