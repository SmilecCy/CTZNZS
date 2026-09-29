# -*- coding: utf-8 -*-
"""FastAPI 应用入口。

【启动方式】

    python scripts/run_api.py
    或
    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

【访问】

    API 服务：http://localhost:8000
    接口文档：http://localhost:8000/docs    （Swagger UI）
    健康检查：http://localhost:8000/health
"""

from __future__ import annotations

import os

# PaddlePaddle 3.x 的 PIR 格式与 OneDNN 推理引擎不兼容
# 在导入任何 paddle 相关模块之前禁用 PIR，回退到旧版执行路径
os.environ["FLAGS_enable_pir_api"] = "0"
# 同时禁用 OneDNN 默认启用（PaddleX 专用标志），避免 PIR→OneDNN 转换失败
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"

import sys
from pathlib import Path

# 把项目根目录加入 sys.path，让 uvicorn 能 import app
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 加载 .env（必须在 import app 模块之前）
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from api.routers import admin, auth, user  # noqa: E402
from app.database import connection as db_mysql, redis as db_redis  # noqa: E402


# ==============================================================
# 应用实例
# ==============================================================
app = FastAPI(
    title="思政+法学 双课程 AI 辅助学习系统",
    description="题库优先、LLM 兜底、来源可追溯",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ==============================================================
# 启动与关闭事件
# ==============================================================
# 【为什么需要】
#   parse_worker 用的线程池是进程级的。
#   启动时要清理上次崩溃留下的僵尸任务；
#   退出时要优雅关闭线程池，避免任务被硬杀。
@app.on_event("startup")
async def on_startup() -> None:
    """应用启动时的初始化。"""
    from app.database import parse_tasks as parse_task

    # 清理僵尸任务
    # 【为什么】
    #   服务重启后，之前在 running 的任务实际已经死了
    #   （后台线程随进程一起消失），但数据库里还是 running。
    #   不清理的话，用户会一直看到"解析中"永远转圈。
    try:
        count = parse_task.cleanup_zombie_tasks()
        if count > 0:
            print(f"[启动] 清理了 {count} 个中断的解析任务")
    except Exception as exc:
        print(f"[启动] 清理僵尸任务失败：{exc}")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """应用退出时的清理。"""
    from app.pipeline import parse_worker

    # 关闭线程池
    # wait=False：立即返回（开发时按 Ctrl+C 更快）
    try:
        parse_worker.shutdown(wait=False)
    except Exception as exc:
        print(f"[关闭] 关闭线程池失败：{exc}")


# ==============================================================
# CORS（跨域）
# ==============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================
# 注册路由
# ==============================================================
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(user.router, prefix="/api/user", tags=["用户"])
app.include_router(admin.router, prefix="/api/admin", tags=["后台"])


# ==============================================================
# 统一异常处理
# ==============================================================
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底异常处理。"""
    import traceback
    traceback.print_exc()

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务器内部错误",
                "detail": str(exc) if app.debug else None,
            }
        },
    )


# ==============================================================
# 健康检查
# ==============================================================
@app.get("/health", tags=["系统"])
async def health_check() -> dict:
    """健康检查。"""
    mysql_status = db_mysql.health_check()
    redis_status = db_redis.health_check()

    return {
        "status": "ok" if (mysql_status["ok"] and redis_status["ok"]) else "degraded",
        "mysql": mysql_status,
        "redis": redis_status,
    }


@app.get("/", tags=["系统"])
async def root() -> dict:
    """根路径。"""
    return {
        "name": "思政+法学 双课程 AI 辅助学习系统",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)