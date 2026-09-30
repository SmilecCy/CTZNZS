# -*- coding: utf-8 -*-
"""临时脚本：查看预热任务状态与失败原因。

【注意】
    预热功能已在数据库迁移 018 中移除（warmup_jobs / warmup_items 表已删除）。
    题库生成逻辑已迁移到 parse_tasks 模块。
    本脚本保留作为历史参考，仅打印状态说明。
"""

from __future__ import annotations


def main() -> None:
    print("=" * 70)
    print("预热任务诊断")
    print("=" * 70)
    print()
    print("  预热功能已在数据库迁移 018 中移除。")
    print("  预热任务表（warmup_jobs / warmup_items）已删除。")
    print("  题库生成逻辑已迁移到 parse_tasks 模块。")
    print("  如需查看当前题库生成任务，请使用 _check_status.py。")
    print()


if __name__ == "__main__":
    main()