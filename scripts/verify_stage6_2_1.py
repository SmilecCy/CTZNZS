# -*- coding: utf-8 -*-
"""阶段 6.2.1 验证脚本：解析任务的 service 层。

**这个脚本不走 HTTP，直接调 service 层。**

【验证内容】

    1. 建任务
    2. 提交到线程池
    3. 轮询进度
    4. 完成后检查结果
    5. 清理
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app.database import parse_tasks as parse_task; from app.pipeline import parse_worker  # noqa: E402


def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _section(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


# ==============================================================
# 检查
# ==============================================================
def check_cleanup_zombie() -> bool:
    """检查僵尸任务清理。"""
    _section("1. 僵尸任务清理")

    try:
        count = parse_task.cleanup_zombie_tasks()
        _ok(f"清理了 {count} 个僵尸任务")
        return True
    except Exception as exc:
        _fail(f"异常：{type(exc).__name__}: {exc}")
        return False


def check_full_flow() -> bool:
    """跑完整流程：建任务 → 提交 → 轮询 → 检查结果。"""
    _section("2. 完整流程")

    # 造一份测试资料
    tmp = Path(tempfile.gettempdir()) / "test_621.txt"
    tmp.write_text(
        "第一章 归责原则\n\n过错责任是侵权责任的一般归责原则。\n\n"
        "第二章 过错推定\n\n推定行为人有过错，由行为人证明自己没有过错。",
        encoding="utf-8",
    )
    _ok(f"造测试文件：{tmp}")

    # 建任务
    try:
        task_id = parse_task.create_task(
            source_file=tmp.name,
            file_path=str(tmp),
            course_key="tort",
        )
        _ok(f"建任务：id={task_id}")
    except Exception as exc:
        _fail(f"建任务失败：{type(exc).__name__}: {exc}")
        return False

    # 提交到线程池
    try:
        parse_worker.submit_task(task_id)
        _ok("已提交到线程池")
    except Exception as exc:
        _fail(f"提交失败：{type(exc).__name__}: {exc}")
        return False

    # 轮询进度
    print("  等待任务完成（最多 60 秒）...")
    start = time.time()
    last_status = None
    last_progress = -1

    while time.time() - start < 60:
        task = parse_task.get_task(task_id)
        if task is None:
            _fail("任务消失了？")
            return False

        current_status = task["status"]
        current_progress = task["progress"]

        # 状态或进度变化时打印
        if current_status != last_status or current_progress != last_progress:
            stage = task.get("stage") or ""
            print(f"    [{current_progress:3d}%] {current_status} {stage}")
            last_status = current_status
            last_progress = current_progress

        if current_status in (parse_task.STATUS_DONE, parse_task.STATUS_FAILED):
            break

        time.sleep(1)

    # 检查最终状态
    task = parse_task.get_task(task_id)

    if task["status"] == parse_task.STATUS_DONE:
        _ok(f"任务完成：page_count={task['page_count']}, chunk_count={task['chunk_count']}")
        _ok(f"OCR 使用：{task['ocr_used']}")
        _ok(f"警告：{task['warnings']}")
        return True
    elif task["status"] == parse_task.STATUS_FAILED:
        _fail(f"任务失败：{task['error']}")
        return False
    else:
        _fail(f"超时未完成，当前状态：{task['status']}，进度：{task['progress']}%")
        return False


def check_list_tasks() -> bool:
    """检查任务列表。"""
    _section("3. 任务列表")

    try:
        tasks = parse_task.list_tasks(limit=10)
        _ok(f"共 {len(tasks)} 个任务")

        for t in tasks[:3]:
            _ok(f"  id={t['id']} status={t['status']} file={t['source_file']}")

        return True
    except Exception as exc:
        _fail(f"异常：{type(exc).__name__}: {exc}")
        return False


def check_cleanup_test_data() -> bool:
    """清理测试数据。

    【为什么用参数化查询而不是把值拼进 SQL】
        pymysql 用 %s 做参数占位符，SQL 字符串里的裸 % 会被当成
        格式符。之前写 ``LIKE 'test_621%'`` 会报
        "not enough arguments for format string"。

        两个修法：
          A. 把 % 转义为 %% —— 写 ``LIKE 'test_621%%'``
          B. 用参数化 —— 写 ``LIKE %s``，参数传 "test_621%"

        这里用 B：更清晰、更安全（防止 SQL 注入）。
        参数里的 % 不需要转义（它不在 SQL 字符串里）。
    """
    _section("4. 清理测试数据")

    try:
        from app.database import connection as db_mysql; from app.pipeline import indexer

        # 删测试任务
        db_mysql.execute(
            "DELETE FROM parse_tasks WHERE source_file LIKE %s",
            ("test_621%",),
        )
        _ok("已删除测试任务")

        # 清向量库（本次测试写进去的 chunk）
        result = indexer.reset_store()
        _ok(f"向量库重置：{result['removed']} 项删除")

        # 删 materials 里的测试资料
        db_mysql.execute(
            "DELETE FROM materials WHERE source_file LIKE %s",
            ("test_621%",),
        )
        _ok("已删除测试资料记录")

        return True
    except Exception as exc:
        _fail(f"清理失败：{type(exc).__name__}: {exc}")
        return False


# ==============================================================
# 主流程
# ==============================================================
def main() -> int:
    print("=" * 60)
    print("阶段 6.2.1 验证脚本（service 层）")
    print("=" * 60)

    if not check_cleanup_zombie():
        return 1

    if not check_full_flow():
        parse_worker.shutdown(wait=False)
        return 1

    if not check_list_tasks():
        parse_worker.shutdown(wait=False)
        return 1

    if not check_cleanup_test_data():
        parse_worker.shutdown(wait=False)
        return 1

    # 关闭线程池
    parse_worker.shutdown(wait=False)

    _section("结论")
    print("  阶段 6.2.1 的 service 层全部通过。")
    print()
    print("  下一步：等第二批（HTTP 接口 + 前端上传页）")
    return 0


if __name__ == "__main__":
    sys.exit(main())