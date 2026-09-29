# -*- coding: utf-8 -*-
"""解析任务服务：parse_tasks 表的 CRUD。

【这个模块做什么】

    1. 建任务
    2. 更新任务状态、进度
    3. 查任务（单个、列表）
    4. 清理僵尸任务（服务重启后 running 状态的任务）

【为什么要单独一个模块】

    任务状态的流转（pending → running → done/failed）只在这里发生。
    集中管理避免"某个调用方忘了写 finished_at"之类的问题。
"""

from __future__ import annotations

import json
from typing import Any

from app.database import connection as db_mysql


# ==============================================================
# 状态常量
# ==============================================================
STATUS_PENDING = "pending"    # 刚创建，未开始
STATUS_RUNNING = "running"    # 正在跑
STATUS_DONE = "done"          # 成功
STATUS_FAILED = "failed"      # 失败


# ==============================================================
# 建
# ==============================================================
def create_task(
    source_file: str,
    file_path: str,
    course_key: str | None = None,
    upload_type: str = "supplement",
) -> int:
    """建一个解析任务。

    Args:
        source_file: 文件名（含扩展名）。
        file_path: 服务器上的完整路径。
        course_key: 课程 key（可选）。
        upload_type: 上传类型（textbook / supplement）。

    Returns:
        新任务 id。
    """
    return db_mysql.insert_returning_id(
        "INSERT INTO parse_tasks (source_file, file_path, course_key, upload_type, status) "
        "VALUES (%s, %s, %s, %s, %s)",
        (source_file, file_path, course_key, upload_type, STATUS_PENDING),
    )


# ==============================================================
# 查
# ==============================================================
def get_task(task_id: int) -> dict[str, Any] | None:
    """按 id 查任务。"""
    row = db_mysql.fetch_one(
        "SELECT * FROM parse_tasks WHERE id = %s",
        (task_id,),
    )
    return _decorate(row) if row else None


def list_tasks(
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """列出任务。

    Args:
        status: 筛选状态；None 表示全部。
        limit: 最多返回条数。

    Returns:
        任务列表（最新的排前面）。
    """
    sql = "SELECT * FROM parse_tasks WHERE 1=1"
    params: list[Any] = []

    if status:
        sql += " AND status = %s"
        params.append(status)

    sql += " ORDER BY id DESC LIMIT %s"
    params.append(int(limit))

    rows = db_mysql.fetch_all(sql, tuple(params))
    return [_decorate(r) for r in rows]


def find_by_file(source_file: str) -> dict[str, Any] | None:
    """按文件名查最近一次任务（用于"这份资料是不是已经处理过了"）。"""
    row = db_mysql.fetch_one(
        "SELECT * FROM parse_tasks WHERE source_file = %s ORDER BY id DESC LIMIT 1",
        (source_file,),
    )
    return _decorate(row) if row else None


# ==============================================================
# 更新
# ==============================================================
def mark_running(task_id: int) -> None:
    """标记任务开始执行。"""
    db_mysql.execute(
        "UPDATE parse_tasks SET status = %s, started_at = CURRENT_TIMESTAMP, "
        "progress = 0 WHERE id = %s",
        (STATUS_RUNNING, task_id),
    )


def update_progress(
    task_id: int,
    progress: int,
    stage: str = "",
) -> None:
    """更新进度。

    Args:
        task_id: 任务 id。
        progress: 0~100。
        stage: 阶段名（解析 / 切分 / 索引）。
    """
    progress = max(0, min(100, int(progress)))
    db_mysql.execute(
        "UPDATE parse_tasks SET progress = %s, stage = %s WHERE id = %s",
        (progress, stage or None, task_id),
    )


def mark_done(
    task_id: int,
    page_count: int,
    chunk_count: int,
    ocr_used: bool,
    warnings: list[str] | None = None,
) -> None:
    """标记任务成功完成。"""
    warnings_json = json.dumps(warnings or [], ensure_ascii=False)

    db_mysql.execute(
        "UPDATE parse_tasks SET "
        "status = %s, progress = 100, page_count = %s, chunk_count = %s, "
        "ocr_used = %s, warnings = %s, finished_at = CURRENT_TIMESTAMP "
        "WHERE id = %s",
        (STATUS_DONE, page_count, chunk_count, int(ocr_used), warnings_json, task_id),
    )


def mark_failed(task_id: int, error: str) -> None:
    """标记任务失败。"""
    db_mysql.execute(
        "UPDATE parse_tasks SET "
        "status = %s, error = %s, finished_at = CURRENT_TIMESTAMP "
        "WHERE id = %s",
        (STATUS_FAILED, error[:1000], task_id),
    )


# ==============================================================
# 清理
# ==============================================================
def cleanup_zombie_tasks() -> int:
    """把僵死的 running 任务标记为 failed。

    【什么时候需要】
        服务重启后，之前在 running 的任务实际已经死了
        （后台线程随进程一起消失），但数据库里还是 running。
        如果不清理，用户会一直看到"解析中"永远转圈。

    【什么时候调用】
        应用启动时（api/main.py 的 lifespan 事件里）。

    Returns:
        清理掉的任务数。
    """
    affected = db_mysql.execute(
        "UPDATE parse_tasks SET "
        "status = %s, error = '服务重启导致任务中断，请重新上传或重试' "
        "WHERE status = %s",
        (STATUS_FAILED, STATUS_RUNNING),
    )
    return affected


# ==============================================================
# 内部工具
# ==============================================================
def _decorate(row: dict[str, Any]) -> dict[str, Any]:
    """整理数据库行，解析 JSON 字段。"""
    row = dict(row)

    # 解析 warnings JSON
    raw = row.get("warnings")
    if raw:
        try:
            parsed = json.loads(raw)
            row["warnings"] = parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            row["warnings"] = []
    else:
        row["warnings"] = []

    return row