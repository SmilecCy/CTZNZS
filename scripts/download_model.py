# -*- coding: utf-8 -*-
"""把中文向量模型下载到本地 ``models/`` 目录。

**为什么需要这个脚本**：模型默认从 HuggingFace 下载，而国内网络基本连不上——
表现为上传资料时卡住、或者抛一长串 ``WinError 10060``。把它下到本地之后，
应用会**自动优先使用本地那一份**（见 ``app/config.py`` 的
``has_local_model``），从此完全离线运行，再也不碰网络。

用法::

    python scripts/download_model.py

脚本会依次尝试几个来源，哪个通了就用哪个，最后校验文件是否真的下全了。

**如果所有来源都不通**，还有一条最可靠的路：用浏览器打开镜像站
``https://hf-mirror.com/BAAI/bge-small-zh-v1.5/tree/main``，
把里面所有文件下载到 ``models/bge-small-zh-v1.5/`` 目录下。
浏览器能打开的话，这条路一定通——它不依赖 Python 的网络配置。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import (  # noqa: E402
    EMBEDDING_MODEL_ID,
    LOCAL_MODEL_DIR,
    has_local_model,
)

# 依次尝试的来源。镜像放前面——国内它通常能通，而官方源基本不通。
_SOURCES: tuple[tuple[str, str], ...] = (
    ("https://hf-mirror.com", "国内镜像 hf-mirror.com"),
    ("https://huggingface.co", "官方源 huggingface.co"),
)


def _attempt(endpoint: str, label: str) -> bool:
    """在独立子进程里尝试从某个来源下载。

    **为什么用子进程**：``huggingface_hub`` 在**导入时**就把 ``HF_ENDPOINT``
    读进常量了。同一个进程里想换来源，改环境变量已经来不及。
    每个来源开一个新进程，才能保证它读到的是我们要的那个地址。
    """
    print(f"\n  → 尝试 {label}")
    print(f"     {endpoint}")

    code = (
        "from huggingface_hub import snapshot_download\n"
        f"snapshot_download(repo_id={EMBEDDING_MODEL_ID!r}, "
        f"local_dir={str(LOCAL_MODEL_DIR)!r})\n"
    )
    env = {**os.environ, "HF_ENDPOINT": endpoint}

    try:
        result = subprocess.run([sys.executable, "-c", code], env=env, cwd=str(ROOT))
    except OSError as exc:
        print(f"     启动失败：{exc}")
        return False

    if result.returncode == 0:
        print("     ✓ 下载完成")
        return True

    print("     ✗ 这个来源没通")
    return False


def _report_missing() -> list[str]:
    """列出本地目录里缺了哪些关键文件。"""
    required = ("config.json",)
    weights = ("model.safetensors", "pytorch_model.bin")

    missing = [name for name in required if not (LOCAL_MODEL_DIR / name).is_file()]
    if not any((LOCAL_MODEL_DIR / name).is_file() for name in weights):
        missing.append("权重文件（model.safetensors 或 pytorch_model.bin）")
    return missing


def main() -> int:
    print("=" * 62)
    print("下载中文向量模型到本地")
    print("=" * 62)
    print(f"  模型  : {EMBEDDING_MODEL_ID}")
    print(f"  目标  : {LOCAL_MODEL_DIR}")

    if has_local_model():
        print("\n  本地已经有完整的模型了，不需要重新下载。")
        print("  应用会自动优先使用它，不会再联网。")
        return 0

    if LOCAL_MODEL_DIR.exists() and any(LOCAL_MODEL_DIR.iterdir()):
        print("\n  注意：目标目录里已有内容，但看起来不完整——")
        print("        可能是上次下载中断留下的。本次会继续补齐。")

    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        print("\n  [缺失] 需要 huggingface_hub 才能下载。请先安装：")
        print("         pip install huggingface_hub")
        return 1

    for endpoint, label in _SOURCES:
        if _attempt(endpoint, label):
            break
    else:
        print("\n" + "=" * 62)
        print("所有来源都没通")
        print("=" * 62)
        print("\n  改用浏览器手动下载（这条路最可靠）：")
        print(f"    1. 打开  https://hf-mirror.com/{EMBEDDING_MODEL_ID}/tree/main")
        print(f"    2. 把页面里所有文件下载到：")
        print(f"         {LOCAL_MODEL_DIR}")
        print("    3. 保持目录结构（如果有子文件夹，也要一起下）")
        print("    4. 下完重跑本脚本，它会校验是否齐全")
        return 1

    if has_local_model():
        print("\n" + "=" * 62)
        print("完成")
        print("=" * 62)
        print(f"  模型已就位：{LOCAL_MODEL_DIR}")
        print("\n  现在可以启动应用了，它会自动用本地这一份：")
        print("      python app.py dev")
        print("\n  注意：应用启动时才读取模型位置，所以要**重启应用**才会生效。")
        return 0

    missing = _report_missing()
    print("\n  [失败] 下载结束了，但文件不完整，缺少：")
    for item in missing:
        print(f"         - {item}")
    print("\n  请重跑本脚本补齐，或改用浏览器手动下载。")
    return 1


if __name__ == "__main__":
    sys.exit(main())