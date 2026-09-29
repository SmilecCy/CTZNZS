# -*- coding: utf-8 -*-
"""提示词库加载器。

命名规范：{module}_{course}_{type}_v{version}.txt

例如：m0_all_classify_material_v0.1.txt

本模块负责扫描 prompts 目录、按模块解析元信息，并按名字读取内容。
提示词与代码分离，改提示词不需要动代码。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import PROMPTS_DIR


# ==============================================================
# 命名规范解析
# ==============================================================
# 匹配形如：m0_all_classify_material_v0.1
#   module=m0
#   course=all
#   type=classify_material
#   version=0.1
_NAME_RE = re.compile(
    r"^(?P<module>m[\d.]+)_(?P<course>[a-z]+)_(?P<type>[a-z_]+)_v(?P<version>[\d.]+)$"
)

# 模板占位符：{{名称}}
# 用双花括号是为了和提示词里的 JSON 示例（单花括号）区分
_RE_PLACEHOLDER = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}")


# ==============================================================
# 元信息
# ==============================================================
@dataclass(frozen=True)
class PromptMeta:
    """一个提示词文件的元信息。"""

    name: str       # 不含扩展名的文件名
    module: str     # m0 / m2 / m4 ...
    course: str     # all / tort / xigai
    type: str       # ocr_clean / short_answer ...
    version: str    # 0.1
    path: Path      # 文件路径


# ==============================================================
# 扫描
# ==============================================================
def list_prompts() -> list[PromptMeta]:
    """列出 prompts 目录下所有符合命名规范的提示词。

    【为什么要扫描而不是硬编码】
        新增提示词文件后，不需要改代码。
        扫描目录即可发现。

    Returns:
        PromptMeta 列表，按文件名排序。
        不符合命名规范的文件会被跳过（不报错）。
    """
    items: list[PromptMeta] = []
    for f in sorted(PROMPTS_DIR.glob("*.txt")):
        m = _NAME_RE.match(f.stem)
        if not m:
            continue   # 不符合命名规范的跳过
        items.append(PromptMeta(name=f.stem, path=f, **m.groupdict()))
    return items


# ==============================================================
# 读取
# ==============================================================
@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """按文件名（不含扩展名）读取提示词正文。

    【为什么加 lru_cache】
        同一个提示词在一次进程里会被反复读（每次调用都读文件太浪费）。
        加了缓存后，第一次读文件，之后从内存取。

        提示词文件在开发时可能会改，想让它重新读：
        重启 Python 进程即可（缓存是进程级的）。

    Args:
        name: 如 "m0_all_classify_material_v0.1"。

    Returns:
        提示词文本。

    Raises:
        FileNotFoundError: 提示词不存在。
    """
    path = PROMPTS_DIR / f"{name}.txt"
    # 防御：如果调用方已经带 .txt，去重避免变成 name.txt.txt
    if not path.is_file():
        alt = PROMPTS_DIR / name
        if alt.is_file():
            path = alt
    if not path.is_file():
        raise FileNotFoundError(f"提示词不存在：{name}（查找路径 {path}）")
    return path.read_text(encoding="utf-8")


def prompt_version(name: str) -> str:
    """取提示词版本号。

    【用途】写入题库的 prompt_version 字段，用于后续迭代分析：
        "哪一版提示词生成的题质量差"。

    Args:
        name: 提示词名。

    Returns:
        版本号字符串（如 "0.1"）；解析失败返回 "unknown"。
    """
    m = _NAME_RE.match(name)
    return m.group("version") if m else "unknown"


# ==============================================================
# 渲染
# ==============================================================
def render_template(template: str, **values: str) -> str:
    """把模板中的 {{占位符}} 替换为实际值。

    【为什么不用 str.format】
        提示词里大量出现 JSON 示例（单个花括号），
        format 会把它们当成格式字段而抛 KeyError。

        改用双花括号占位符，与 JSON 天然不冲突，也不需要转义。

    Args:
        template: 模板文本。
        **values: 占位符名 -> 值。

    Returns:
        渲染后的文本。

    Raises:
        KeyError: 模板中存在未提供值的占位符。
            早失败优于把半成品喂给模型。
    """
    # 先检测模板中是否有未提供值的占位符
    before = set(_RE_PLACEHOLDER.findall(template))
    after = set(values.keys())
    missing = before - after
    if missing:
        raise KeyError(f"提示词模板存在未填充的占位符：{sorted(missing)}")

    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))

    return rendered


def load_rendered(name: str, **values: str) -> str:
    """读取提示词并直接渲染。

    是 load_prompt + render_template 的快捷方式。

    Args:
        name: 提示词名。
        **values: 占位符值。

    Returns:
        渲染后的提示词。
    """
    return render_template(load_prompt(name), **values)