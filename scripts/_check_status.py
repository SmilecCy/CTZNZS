# -*- coding: utf-8 -*-
"""临时诊断脚本：看课程、知识点、资料、题库、LLM、预热任务。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from app.database import (
    course,
    knowledge_point,
    llm_client,
    material_store,
    question_bank_mysql,
    warmup_mysql,
)


def main() -> None:
    print("=" * 60)
    print("系统状态诊断")
    print("=" * 60)

    # LLM
    print()
    print("【LLM】")
    client = llm_client.LLMClient()
    print(f"  已配置: {client.is_configured()}")
    print(f"  模型:   {client.model}")

    # 课程 + 知识点
    print()
    print("【课程与知识点】")
    courses = course.list_all()
    print(f"  课程数: {len(courses)}")
    for c in courses:
        kps = knowledge_point.list_by_course(c["id"])
        print(f"    [{c['id']}] {c['name']}: {len(kps)} 个知识点")
        for kp in kps[:10]:
            print(f"        - {kp['name']}")
        if len(kps) > 10:
            print(f"        ... 还有 {len(kps) - 10} 个")

    # 资料
    print()
    print("【资料】")
    materials = material_store.list_all(limit=20)
    print(f"  资料数: {len(materials)}")
    for m in materials:
        print(f"    id={m['id']} {m['source_file']}")
        print(f"        状态={m['detection_status']} course_id={m.get('course_id')}")
        print(f"        块数={m.get('chunk_count')}")

    # 题库
    print()
    print("【题库】")
    for c in courses:
        n = question_bank_mysql.count_questions(c["id"])
        print(f"    {c['name']}: {n} 道题")

    # 预热任务
    print()
    print("【预热任务】")
    for c in courses:
        jobs = warmup_mysql.list_jobs(c["id"], limit=5)
        if jobs:
            print(f"    {c['name']}:")
            for j in jobs:
                print(f"      id={j['id']} status={j['status']} planned={j['planned']}")
        else:
            print(f"    {c['name']}: 无")

    print()


if __name__ == "__main__":
    main()