# -*- coding: utf-8 -*-
"""阶段一验证脚本：把数据层与课程/知识点服务跑一遍。

用法（在项目根目录执行）::

    python scripts/verify_stage1.py

【这个脚本做什么】

    它真的会操作数据库，不是"读一遍代码看看"：
      1. 检查 MySQL / Redis 连通
      2. 建一个测试课程
      3. 给课程加几个知识点（逐个建 + 批量建）
      4. 从缓存读课程列表
      5. 改课程信息
      6. 建第二个课程，合并到第一个
      7. 软删除课程、恢复课程
      8. 清理测试数据

    最后打印"全部通过"或指出哪一步失败。

【为什么需要这个脚本，而不是只用单元测试】

    单元测试里用假数据库（mock），跑通不代表真实 MySQL 能跑通。
    这个脚本用真实的 MySQL + Redis，把所有服务层接口跑一遍，
    是阶段一的"端到端验收"。

【为什么脚本末尾要清理测试数据】

    测试会往数据库里插入"测试课程_xxx"之类的记录。
    如果不清理，反复跑就会积累一堆垃圾数据，
    下次看课程列表会看到一堆"测试课程"。

    所以用 try/finally 保证无论成功失败都清理。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 把项目根目录加入 sys.path，这样才能 import app.*
# 为什么需要这行：脚本在 scripts/ 目录下，直接运行的话
# Python 只会把 scripts/ 加入 sys.path，找不到 app 包。
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 在 import 任何 app 模块之前加载 .env
# 因为 app.config 在导入时就会读环境变量，晚了就读不到。
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app.database import (  # noqa: E402
    cache,
    connection as db_mysql,
    courses as course,
    knowledge_points as knowledge_point,
    redis as db_redis,
)


# ==============================================================
# 测试用常量
# ==============================================================
# 用特殊前缀，避免和真实课程冲突。
# 清理时也按这个前缀删，不会误删真实数据。
TEST_PREFIX = "测试课程_验证用_"

# 测试用的知识点名
TEST_KNOWLEDGE_POINTS = ["测试知识点_A", "测试知识点_B", "测试知识点_C"]


# ==============================================================
# 辅助函数
# ==============================================================
def _ok(msg: str) -> None:
    """打印成功信息（绿色对勾）。"""
    print(f"  [OK]   {msg}")


def _fail(msg: str) -> None:
    """打印失败信息（红色叉）。"""
    print(f"  [FAIL] {msg}")


def _section(title: str) -> None:
    """打印分节标题。"""
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def _cleanup() -> None:
    """清理所有测试数据。

    【为什么按前缀删而不是按 id 删】
        如果测试中途崩了，我们可能拿不到已创建课程的 id。
        按前缀删更稳——不管创建了多少个测试课程，都能一次清掉。

    【删除顺序】
        必须先删知识点，再删课程。
        因为知识点有 course_id 外键（ON DELETE CASCADE），
        但实际上删课程会自动级联删知识点，所以理论上删课程就够。
        显式删知识点是为了"课程被软删除但还在"的情况（软删除不触发级联）。
    """
    try:
        with db_mysql.connection() as conn:
            with conn.cursor() as cur:
                # 查所有测试课程 id
                cur.execute(
                    "SELECT id FROM courses WHERE name LIKE %s",
                    (f"{TEST_PREFIX}%",),
                )
                ids = [row["id"] for row in cur.fetchall()]

                if not ids:
                    return

                # 构造 IN 的占位符：如果是 3 个 id，生成 "%s, %s, %s"
                placeholders = ", ".join(["%s"] * len(ids))

                # 删知识点
                cur.execute(
                    f"DELETE FROM knowledge_points WHERE course_id IN ({placeholders})",
                    ids,
                )

                # 删课程
                cur.execute(
                    f"DELETE FROM courses WHERE id IN ({placeholders})",
                    ids,
                )

        # 清缓存（测试课程可能在缓存里）
        cache.invalidate_course_list()
    except Exception as exc:  # noqa: BLE001 - 清理失败不该让整个脚本崩
        print(f"  [警告] 清理测试数据时出错（可忽略）：{exc}")


# ==============================================================
# 各项检查
# ==============================================================
def check_connections() -> bool:
    """检查 MySQL 与 Redis 是否连通。"""
    _section("1. 数据库连通性检查")

    mysql = db_mysql.health_check()
    if mysql["ok"]:
        _ok(f"MySQL 连通（版本 {mysql['version']}）")
    else:
        _fail(f"MySQL 连不上：{mysql['error']}")
        print()
        print("  排查建议：")
        print("    1. 确认容器在跑：docker compose ps")
        print("    2. 确认 .env 里 MYSQL_PORT 和 docker-compose.yml 的端口映射一致")
        return False

    redis = db_redis.health_check()
    if redis["ok"]:
        _ok(f"Redis 连通（版本 {redis['version']}）")
    else:
        _fail(f"Redis 连不上：{redis['error']}")
        print()
        print("  排查建议：")
        print("    1. 确认容器在跑：docker compose ps")
        print("    2. 确认 .env 里 REDIS_PORT 和 docker-compose.yml 的端口映射一致")
        return False

    return True


def check_course_create() -> int | None:
    """建一个测试课程，返回它的 id。"""
    _section("2. 建课程")

    test_name = f"{TEST_PREFIX}商法"
    try:
        course_id = course.create(
            name=test_name,
            display_name="测试商法",
            description="这是验证脚本创建的测试课程",
            question_focus="构成要件辨析",
        )
        _ok(f"建课程成功：id={course_id}, name={test_name}")
        return course_id
    except Exception as exc:  # noqa: BLE001
        _fail(f"建课程失败：{type(exc).__name__}: {exc}")
        return None


def check_course_duplicate() -> bool:
    """验证"同名课程不能重复建"。"""
    test_name = f"{TEST_PREFIX}商法"
    try:
        course.create(name=test_name)
        _fail("同名课程居然能重复建，唯一约束没生效")
        return False
    except course.CourseNameExistsError:
        _ok("同名课程被正确拒绝（CourseNameExistsError）")
        return True
    except Exception as exc:  # noqa: BLE001
        _fail(f"预期抛 CourseNameExistsError，实际抛了 {type(exc).__name__}: {exc}")
        return False


def check_knowledge_points(course_id: int) -> list[int] | None:
    """建知识点：逐个建 + 批量建。"""
    _section("3. 建知识点")

    try:
        # 逐个建
        kp_a = knowledge_point.create(course_id, TEST_KNOWLEDGE_POINTS[0])
        _ok(f"逐个建知识点成功：id={kp_a}, name={TEST_KNOWLEDGE_POINTS[0]}")

        # 批量建（包含一个已存在的，验证"已存在就复用"）
        ids = knowledge_point.bulk_create(
            course_id,
            [TEST_KNOWLEDGE_POINTS[0], TEST_KNOWLEDGE_POINTS[1], TEST_KNOWLEDGE_POINTS[2]],
        )
        _ok(f"批量建知识点成功：{len(ids)} 个 id={ids}")

        # 验证：第一个应该是复用的（id 和 kp_a 相同）
        if ids[0] != kp_a:
            _fail(f"批量建时已存在的知识点没有被复用：期望 {kp_a}，实际 {ids[0]}")
            return None
        _ok("批量建时已存在的知识点被正确复用")

        # 查该课程的知识点列表
        kps = knowledge_point.list_by_course(course_id)
        if len(kps) != 3:
            _fail(f"知识点数量不对：期望 3，实际 {len(kps)}")
            return None
        _ok(f"列出知识点成功：{len(kps)} 个")

        return ids

    except Exception as exc:  # noqa: BLE001
        _fail(f"建知识点失败：{type(exc).__name__}: {exc}")
        return None


def check_course_list_cache(course_id: int) -> bool:
    """验证课程列表缓存生效。"""
    _section("4. 课程列表缓存")

    try:
        # 第一次查询（走数据库）
        list1 = course.list_all()
        _ok(f"第一次查课程列表：{len(list1)} 门课")

        # 检查缓存里有没有
        cached = cache.get(cache.course_list_key())
        if cached is None:
            _fail("第一次查询后缓存里没有数据")
            return False
        _ok("第一次查询后数据已写入缓存")

        # 第二次查询（走缓存）
        list2 = course.list_all()
        if len(list2) != len(list1):
            _fail("第二次查询结果和第一次不一致")
            return False
        _ok("第二次查询走缓存，结果一致")

        return True

    except Exception as exc:  # noqa: BLE001
        _fail(f"缓存测试失败：{type(exc).__name__}: {exc}")
        return False


def check_course_update(course_id: int) -> bool:
    """验证改课程信息，且缓存被清。"""
    _section("5. 改课程")

    try:
        course.update(course_id, display_name="改过的展示名", description="改过的描述")
        _ok("改课程成功")

        # 重新查，验证改了
        updated = course.get_by_id(course_id)
        if updated["display_name"] != "改过的展示名":
            _fail(f"改课程没生效：display_name={updated['display_name']}")
            return False
        _ok("改课程已生效")

        # 验证缓存被清了（再查一次应该从数据库读，能看到新值）
        list_after = course.list_all()
        target = next((c for c in list_after if c["id"] == course_id), None)
        if target is None or target["display_name"] != "改过的展示名":
            _fail("改课程后列表缓存没更新")
            return False
        _ok("改课程后缓存已刷新")

        return True

    except Exception as exc:  # noqa: BLE001
        _fail(f"改课程失败：{type(exc).__name__}: {exc}")
        return False


def check_course_merge(course_id: int) -> bool:
    """验证课程合并。"""
    _section("6. 课程合并")

    try:
        # 建第二个课程
        second_id = course.create(
            name=f"{TEST_PREFIX}商法基础",
            display_name="测试商法基础",
        )
        _ok(f"建第二个课程：id={second_id}")

        # 给第二个课程也加知识点（其中 A 和第一个课程重名，应该被合并去重）
        knowledge_point.bulk_create(
            second_id,
            [TEST_KNOWLEDGE_POINTS[0], "测试知识点_D"],
        )
        _ok("给第二个课程加了 2 个知识点（其中 A 与第一个课程重名）")

        # 合并第二个到第一个
        report = course.merge(second_id, course_id, merged_by="verify_script")

        # 验证报告
        if report["merged_knowledge_points"] != 1:
            _fail(f"合并去重的知识点数不对：期望 1，实际 {report['merged_knowledge_points']}")
            return False
        _ok("合并去重了 1 个重名知识点")

        if report["moved_knowledge_points"] != 1:
            _fail(f"迁移的知识点数不对：期望 1，实际 {report['moved_knowledge_points']}")
            return False
        _ok("迁移了 1 个不重名的知识点")

        # 验证第二个课程被标记为已合并
        second = course.get_by_id(second_id)
        if second["merged_into"] != course_id:
            _fail(f"第二个课程没被正确标记：merged_into={second['merged_into']}")
            return False
        _ok("第二个课程被正确标记为已合并")

        if second["is_active"] != 0:
            _fail("第二个课程没被停用")
            return False
        _ok("第二个课程已被停用")

        # 清理第二个课程（它是测试数据，硬删除）
        # 用 SQL 直接删，因为 course 服务没有硬删除接口
        db_mysql.execute("DELETE FROM knowledge_points WHERE course_id = %s", (second_id,))
        db_mysql.execute("DELETE FROM course_merge_log WHERE from_course_id = %s", (second_id,))
        db_mysql.execute("DELETE FROM courses WHERE id = %s", (second_id,))
        _ok("清理了第二个课程")

        return True

    except Exception as exc:  # noqa: BLE001
        _fail(f"课程合并失败：{type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return False


def check_course_soft_delete(course_id: int) -> bool:
    """验证软删除和恢复。"""
    _section("7. 软删除与恢复")

    try:
        # 软删除
        course.soft_delete(course_id)
        _ok("软删除成功")

        # 默认列表里不该有它
        active_list = course.list_all()
        if any(c["id"] == course_id for c in active_list):
            _fail("软删除后课程还在启用列表里")
            return False
        _ok("软删除后课程不在启用列表里")

        # 但能查到（含已删除）
        all_list = course.list_all(include_inactive=True)
        target = next((c for c in all_list if c["id"] == course_id), None)
        if target is None:
            _fail("含已删除的列表里也找不到该课程")
            return False
        if target["is_active"] != 0:
            _fail(f"is_active 应为 0，实际 {target['is_active']}")
            return False
        _ok("含已删除的列表里能找到它，is_active=0")

        # 恢复
        course.restore(course_id)
        _ok("恢复成功")

        active_list = course.list_all()
        if not any(c["id"] == course_id for c in active_list):
            _fail("恢复后课程没回到启用列表")
            return False
        _ok("恢复后课程回到启用列表")

        return True

    except Exception as exc:  # noqa: BLE001
        _fail(f"软删除测试失败：{type(exc).__name__}: {exc}")
        return False


# ==============================================================
# 主流程
# ==============================================================
def main() -> int:
    """入口：按顺序跑所有检查。

    Returns:
        0 表示全部通过，1 表示有失败。
    """
    print("=" * 60)
    print("阶段一验证脚本")
    print("=" * 60)

    # 先清理一遍（避免上次跑崩了残留的测试数据）
    _cleanup()

    # ---------- 1. 连通性 ----------
    if not check_connections():
        return 1

    # ---------- 2. 建课程 ----------
    course_id = check_course_create()
    if course_id is None:
        _cleanup()
        return 1

    try:
        # ---------- 3. 同名拒绝 ----------
        _section("3. 同名课程去重")
        if not check_course_duplicate():
            return 1

        # ---------- 4. 建知识点 ----------
        kp_ids = check_knowledge_points(course_id)
        if kp_ids is None:
            return 1

        # ---------- 5. 缓存 ----------
        if not check_course_list_cache(course_id):
            return 1

        # ---------- 6. 改课程 ----------
        if not check_course_update(course_id):
            return 1

        # ---------- 7. 合并 ----------
        if not check_course_merge(course_id):
            return 1

        # ---------- 8. 软删除 ----------
        if not check_course_soft_delete(course_id):
            return 1

    finally:
        # 不管前面成功还是失败，都清理测试数据
        _section("清理测试数据")
        _cleanup()
        _ok("清理完成")

    # ---------- 全部通过 ----------
    _section("结论")
    print("  阶段一全部通过。")
    print()
    print("  下一步：进入阶段二（资料分类与合并）。")
    return 0
# ===== 临时诊断：看 .env 读取情况 =====
import os as _os
print("=" * 60)
print("诊断信息")
print("=" * 60)
print("当前工作目录:", _os.getcwd())
print("脚本所在目录:", Path(__file__).resolve().parent)
print("ROOT:", ROOT)
print(".env 路径:", ROOT / ".env")
print(".env 存在:", (ROOT / ".env").is_file())
print("MYSQL_HOST =", _os.getenv("MYSQL_HOST"))
print("MYSQL_PORT =", _os.getenv("MYSQL_PORT"))
print("MYSQL_USER =", _os.getenv("MYSQL_USER"))
print("MYSQL_PASSWORD 长度 =", len(_os.getenv("MYSQL_PASSWORD") or ""))
print("MYSQL_DATABASE =", _os.getenv("MYSQL_DATABASE"))
print("=" * 60)

if __name__ == "__main__":
    sys.exit(main())