# -*- coding: utf-8 -*-
"""启动 FastAPI 服务。

用法::

    python scripts/run_api.py

【为什么单独一个脚本，而不是直接 uvicorn 命令】

    uvicorn api.main:app --reload 这条命令有两个问题：
      1. 需要在项目根目录跑（因为 api.main 是相对路径导入）
      2. --reload 会在当前目录生成 __pycache__

    这个脚本把路径、参数都固定好，你只需要 python scripts/run_api.py。

【热重载是什么】

    改代码后不用手动重启服务，uvicorn 会自动重新加载。
    开发期很方便，生产环境要关掉。

    实现方式：uvicorn 起两个进程，主进程监视文件变化，
    发现变化就重启工作进程。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 加载 .env（必须在 import api.main 之前）
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import uvicorn  # noqa: E402


def main() -> int:
    """启动服务。"""
    print("=" * 60)
    print("FastAPI 服务")
    print("=" * 60)
    print("地址：http://localhost:8000")
    print("文档：http://localhost:8000/docs")
    print("健康：http://localhost:8000/health")
    print("=" * 60)
    print()
    print("按 Ctrl+C 停止服务。")
    print()

    uvicorn.run(
        "api.main:app",        # 应用位置
        host="0.0.0.0",        # 0.0.0.0 表示监听所有网卡
        port=8000,             # 端口
        reload=True,           # 热重载（开发用）
        reload_dirs=[str(ROOT / "api"), str(ROOT / "app")],   # 监视哪些目录
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())