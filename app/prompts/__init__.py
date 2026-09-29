# -*- coding: utf-8 -*-
"""提示词库包。

【为什么这个文件不能空】
    它需要把 loader 里的公开函数导出。
    这样其他模块可以：
        from app.prompts import load_rendered
    而不需要写：
        from app.prompts.loader import load_rendered

    两种写法都可以，但导出的写法更简洁。

【提示词的命名规范】
    {module}_{course}_{type}_v{version}.txt
    例如：m2_tort_short_answer_v0.1.txt
"""

from app.prompts.loader import (
    PromptMeta,
    list_prompts,
    load_prompt,
    load_rendered,
    prompt_version,
    render_template,
)

__all__ = [
    "PromptMeta",
    "list_prompts",
    "load_prompt",
    "load_rendered",
    "prompt_version",
    "render_template",
]