# -*- coding: utf-8 -*-
"""临时诊断脚本：看课程、知识点、资料、题库、LLM。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from app.database import courses, knowledge_points, materials, questions
from app.ai import llm_client


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
    all_courses = courses.list_all()
    print(f"  课程数: {len(all_courses)}")
    for c in all_courses:
        kps = knowledge_points.list_by_course(c["id"])
        print(f"    [{c['id']}] {c['name']}: {len(kps)} 个知识点")
        for kp in kps[:10]:
            print(f"        - {kp['name']}")
        if len(kps) > 10:
            print(f"        ... 还有 {len(kps) - 10} 个")

    # 资料
    print()
    print("【资料】")
    mats = materials.list_all(limit=20)
    print(f"  资料数: {len(mats)}")
    for m in mats:
        print(f"    id={m['id']} {m['source_file']}")
        print(f"        状态={m['detection_status']} course_id={m.get('course_id')}")
        print(f"        块数={m.get('chunk_count')}")

    # 题库
    print()
    print("【题库】")
    for c in all_courses:
        n = questions.count_questions(c["id"])
        print(f"    {c['name']}: {n} 道题")

    # 预热任务（已移除）
    print()
    print("【预热任务】")
    print("  预热功能已在数据库迁移 018 中移除。")
    print("  预热任务表（warmup_jobs / warmup_items）已删除。")
    print("  题库生成逻辑已迁移到 parse_tasks 模块。")

    print()


if __name__ == "__main__":
    main()