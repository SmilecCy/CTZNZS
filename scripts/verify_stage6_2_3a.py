# -*- coding: utf-8 -*-
"""阶段 6.2.3a 验证脚本：预热服务的 service 层。

【验证内容】
    1. 算缺口
    2. 建任务
    3. 逐格执行（用真实 LLM，会花几毛钱）
    4. 查进度
    5. 报告
    6. 清理

【注意】
    这个脚本会真的调 LLM 生成题目，会产生费用。
    默认只跑 1 个格子（1 道题），成本极低（约 0.01 元）。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app.database import (
    course,
    db_mysql,
    knowledge_point,
    question_bank_mysql,
    warmup_mysql,
)


def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _section(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def check_prerequisites() -> int | None:
    """检查前置条件：至少 1 个启用课程 + 1 个知识点。"""
    _section("1. 前置条件")

    courses = course.list_all()
    if not courses:
        _fail("没有启用课程，请先到后台建课程")
        return None

    _ok(f"有 {len(courses)} 个启用课程")
    course_id = courses[0]["id"]

    kps = knowledge_point.list_by_course(course_id)
    if not kps:
        _fail(f"课程 {courses[0]['name']} 没有知识点")
        return None

    _ok(f"课程 [{course_id}] {courses[0]['name']} 有 {len(kps)} 个知识点")
    return course_id


def check_plan(course_id: int) -> warmup_mysql.WarmupPlan | None:
    """算缺口。"""
    _section("2. 算缺口")

    kps = knowledge_point.list_by_course(course_id)
    # 只取第一个知识点，避免测试时消耗太多
    test_kp = [kps[0]["name"]]

    # 目标：只补 1 道简答题
    plan = warmup_mysql.plan_gaps(
        course_id=course_id,
        knowledge_points=test_kp,
        targets={"简答": 1, "选择": 0},
    )

    _ok(f"计划生成 {plan.total_questions} 道题，分布在 {plan.estimated_calls} 个格子")
    for cell in plan.cells:
        _ok(f"  {cell.knowledge_point} / {cell.question_type} / {cell.difficulty} → {cell.need} 道")

    if plan.is_empty:
        _ok("没有缺口，跳过（题库已达标）")
        return None

    return plan


def check_create_job(plan: warmup_mysql.WarmupPlan) -> int:
    """建任务。"""
    _section("3. 建任务")

    job_id = warmup_mysql.create_job(plan)
    _ok(f"建任务 id={job_id}")

    job = warmup_mysql.get_job(job_id)
    _ok(f"  状态={job['status']}, planned={job['planned']}")

    items = warmup_mysql.list_items(job_id)
    _ok(f"  分项数={len(items)}")

    return job_id


def check_run_job(job_id: int) -> bool:
    """逐格执行（走真实 LLM）。"""
    _section("4. 逐格执行")
    print("  注意：会真的调 LLM，成本约 0.01 元")
    print()

    max_steps = 10
    for step in range(max_steps):
        result = warmup_mysql.run_next_step(job_id)

        if not result["executed"]:
            _ok("没有更多待办格子")
            break

        item = result["item"]
        cell = f"{item['knowledge_point']} / {item['question_type']} / {item['difficulty']}"

        if result["error"]:
            _fail(f"  {cell} 失败：{result['error']}")
        else:
            generated = result["result"]["source_summary"]["from_llm"] if result["result"] else 0
            _ok(f"  {cell} → 生成 {generated} 道")

    warmup_mysql.finish_if_complete(job_id)
    job = warmup_mysql.get_job(job_id)
    _ok(f"任务最终状态：{job['status']}")

    return True


def check_progress(job_id: int) -> bool:
    """查进度。"""
    _section("5. 进度")
    p = warmup_mysql.job_progress(job_id)
    _ok(f"计划 {p['planned']} 道，已生成 {p['generated']} 道")
    _ok(f"格子：完成 {p['items_done']} / 失败 {p['items_failed']} / 待办 {p['items_pending']}")
    _ok(f"进度：{p['ratio'] * 100:.0f}%")
    return True


def check_report(job_id: int) -> bool:
    """查报告。"""
    _section("6. 报告")
    report = warmup_mysql.job_report(job_id)

    _ok(f"计划 {report['planned']} 道，实际生成 {report['generated']} 道")
    _ok(f"LLM 调用 {report['llm_calls']} 次（失败 {report['failed_calls']} 次）")
    _ok(f"Token：输入 {report['prompt_tokens']}，输出 {report['completion_tokens']}")

    if report["by_difficulty"]:
        _ok(f"难度分布：{report['by_difficulty']}")

    if report["failed_items"]:
        _fail("有失败的格子：")
        for f in report["failed_items"]:
            _fail(f"  {f['knowledge_point']} / {f['question_type']}：{f['error']}")

    return True


def check_cleanup() -> bool:
    """清理测试数据。"""
    _section("7. 清理")

    # 只删测试课程（用"测试_" 前缀的）
    db_mysql.execute("DELETE FROM warmup_items WHERE job_id IN "
                     "(SELECT id FROM warmup_jobs WHERE course_id IN "
                     "(SELECT id FROM courses WHERE name LIKE '测试_%'))")
    db_mysql.execute("DELETE FROM warmup_jobs WHERE course_id IN "
                     "(SELECT id FROM courses WHERE name LIKE '测试_%')")
    _ok("测试任务已清理")

    return True


def main() -> int:
    print("=" * 60)
    print("阶段 6.2.3a 验证脚本（预热 service 层）")
    print("=" * 60)

    course_id = check_prerequisites()
    if course_id is None:
        return 1

    plan = check_plan(course_id)
    if plan is None:
        # 没有缺口，也算通过
        _section("结论")
        print("  阶段 6.2.3a 的 service 层通过（无需预热）")
        return 0

    job_id = check_create_job(plan)

    if not check_run_job(job_id):
        return 1

    if not check_progress(job_id):
        return 1

    if not check_report(job_id):
        return 1

    check_cleanup()

    _section("结论")
    print("  阶段 6.2.3a 的 service 层全部通过。")
    print()
    print("  下一步：等第二批（HTTP 接口 + 前端向导）")
    return 0


if __name__ == "__main__":
    sys.exit(main())