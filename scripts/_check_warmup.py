# -*- coding: utf-8 -*-
"""临时脚本：查看预热任务状态与失败原因。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# from app.database import courses as course  # warmup_mysql 已移除


def main() -> None:
    print("=" * 70)
    print("预热任务诊断")
    print("=" * 70)

    courses = course.list_all()
    print(f"\n共 {len(courses)} 个课程\n")

    for c in courses:
        jobs = warmup_mysql.list_jobs(c["id"], limit=10)
        print(f"【课程 {c['id']}】{c['name']}：{len(jobs)} 个任务")
        print("-" * 70)

        for j in jobs:
            print(f"\n  任务 id={j['id']}")
            print(f"    status   = {j['status']}")
            print(f"    planned  = {j['planned']}")
            print(f"    created  = {j['created_at']}")
            print(f"    finished = {j.get('finished_at')}")

            items = warmup_mysql.list_items(j["id"])
            total_done = sum(int(i["done"] or 0) for i in items)
            print(f"    分项数   = {len(items)}")
            print(f"    已生成   = {total_done}")
            print()

            for i in items:
                print(f"      [分项 id={i['id']}]")
                print(f"        知识点   = '{i['knowledge_point']}'")
                print(f"        题型     = {i['question_type']}")
                print(f"        难度     = {i['difficulty']}")
                print(f"        need     = {i['need']}")
                print(f"        done     = {i['done']}")
                print(f"        status   = {i['status']}")

                err = i.get("error")
                if err:
                    print(f"        ❌ ERROR = {err}")

                print()

        print("=" * 70)


if __name__ == "__main__":
    main()