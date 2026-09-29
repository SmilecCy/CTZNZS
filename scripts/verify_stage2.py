# -*- coding: utf-8 -*-
"""阶段二验证脚本：资料分类与合并。

用法（在项目根目录）::

    python scripts/verify_stage2.py

【这个脚本做什么】

    它真的会操作数据库，但**用假 LLM**（不真的调 API），所以：
      - 不需要 LLM 密钥也能跑
      - 不产生任何费用
      - 速度快

    验证内容：
      1. MySQL / Redis 连通
      2. 建测试资料记录（material_store.create）
      3. 用假 LLM 识别资料 → 检查写入了 detected_* 字段
      4. 应用识别建议 → 自动建课程、建知识点、关联资料
      5. 手动合并多份资料到同一门课
      6. 按建议课程名自动分组
      7. 清理测试数据

【为什么用假 LLM 而不是真调】

    真调 LLM 的问题：
      - 每次跑都要花钱（虽然很少）
      - 网络不通就跑不了
      - 模型输出不稳定，测试会时通时不通

    假 LLM 返回固定的 JSON，测试结果 100% 可复现。

    真调 LLM 的验证单独做一个可选步骤（需要密钥），见脚本末尾注释。

【假 LLM 长什么样】

    实现一个类，有 chat_json() 方法，返回预设的 JSON。
    我们的 material_classifier 只调 client.chat_json()，
    所以只要这个假类的 chat_json 签名对得上，就能用。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 把项目根目录加入 sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app.database import (  # noqa: E402
    course,
    db_mysql,
    db_redis,
    knowledge_point,
    material_classifier,
    material_merge,
    material_store,
)
from app.ai.llm_client import LLMResponse, LLMUsage  # noqa: E402


# ==============================================================
# 测试用常量
# ==============================================================
TEST_COURSE_PREFIX = "测试阶段二_"
TEST_MATERIAL_PREFIX = "测试资料_"


# ==============================================================
# 假 LLM
# ==============================================================
class FakeLLM:
    """假 LLM 客户端：返回预设的 JSON，不真的调 API。

    【为什么要自己实现一个假类】
        material_classifier 只依赖 llm.chat_json() 这个接口，
        不依赖 LLMClient 的其他实现细节。
        所以只要这个假类有 chat_json() 方法，就能替换真客户端。

    【为什么返回固定值】
        测试要可复现。如果每次跑都调真模型，结果会变，
        测试就变成"有时通过有时失败"，没意义。

    Args:
        payload: 要返回的 JSON 对象。
    """

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.model = "fake-llm"
        self.calls = 0

    def chat_json(self, messages, temperature=None):
        """模拟 chat_json 的调用。

        返回 (JSON 对象, LLMResponse) 两元组，与真客户端一致。
        """
        self.calls += 1
        content = json.dumps(self.payload, ensure_ascii=False)
        response = LLMResponse(
            content=content,
            usage=LLMUsage(
                model=self.model,
                prompt_tokens=500,
                completion_tokens=100,
                latency_ms=10,
            ),
        )
        return self.payload, response


# ==============================================================
# 辅助函数
# ==============================================================
def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _section(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def _cleanup() -> None:
    """清理测试数据。

    【删除顺序】
        先删资料（因为资料引用课程），再删课程。
        或者直接删课程（外键 ON DELETE SET NULL 会把资料的 course_id 置 NULL）。
        但资料本身还在，所以要单独删。
    """
    try:
        with db_mysql.connection() as conn:
            with conn.cursor() as cur:
                # 删测试资料
                cur.execute(
                    "DELETE FROM materials WHERE source_file LIKE %s",
                    (f"{TEST_MATERIAL_PREFIX}%",),
                )

                # 查测试课程
                cur.execute(
                    "SELECT id FROM courses WHERE name LIKE %s",
                    (f"{TEST_COURSE_PREFIX}%",),
                )
                ids = [row["id"] for row in cur.fetchall()]
                if ids:
                    placeholders = ", ".join(["%s"] * len(ids))
                    # 先删知识点
                    cur.execute(
                        f"DELETE FROM knowledge_points WHERE course_id IN ({placeholders})",
                        ids,
                    )
                    # 再删课程
                    cur.execute(
                        f"DELETE FROM courses WHERE id IN ({placeholders})",
                        ids,
                    )

        # 清缓存
        from app.database import cache
        cache.invalidate_course_list()
    except Exception as exc:  # noqa: BLE001 - 清理失败可忽略
        print(f"  [警告] 清理时出错（可忽略）：{exc}")


# ==============================================================
# 各项检查
# ==============================================================
def check_connections() -> bool:
    """检查 MySQL / Redis 连通。"""
    _section("1. 数据库连通性")

    mysql = db_mysql.health_check()
    if mysql["ok"]:
        _ok(f"MySQL 连通（{mysql['version']}）")
    else:
        _fail(f"MySQL 连不上：{mysql['error']}")
        return False

    redis = db_redis.health_check()
    if redis["ok"]:
        _ok(f"Redis 连通（{redis['version']}）")
    else:
        _fail(f"Redis 连不上：{redis['error']}")
        return False

    return True


def check_create_material() -> int | None:
    """建一份测试资料。"""
    _section("2. 建资料记录")

    file_name = f"{TEST_MATERIAL_PREFIX}商法讲义.pdf"
    try:
        mid = material_store.create(
            source_file=file_name,
            kind="pdf",
            chunk_count=15,
            page_count=20,
            ocr_used=False,
        )
        _ok(f"建资料成功：id={mid}, file={file_name}")

        # 验证初始状态
        material = material_store.get_by_id(mid)
        if material["detection_status"] != material_store.STATUS_PENDING:
            _fail(f"初始状态应为 pending，实际 {material['detection_status']}")
            return None
        _ok("初始状态为 pending")

        return mid
    except Exception as exc:  # noqa: BLE001
        _fail(f"建资料失败：{type(exc).__name__}: {exc}")
        return None


def check_classify(material_id: int) -> bool:
    """用假 LLM 识别资料。"""
    _section("3. LLM 识别资料")

    # 假 LLM 返回的识别结果
    fake_result = {
        "course_name": f"{TEST_COURSE_PREFIX}商法",
        "course_confidence": 0.92,
        "knowledge_points": [
            {"name": "测试知识点_归责原则", "confidence": 0.95},
            {"name": "测试知识点_过错推定", "confidence": 0.88},
            {"name": "测试知识点_构成要件", "confidence": 0.82},
        ],
        "reasoning": "文件名含「商法」，正文围绕归责原则展开。",
    }
    fake_llm = FakeLLM(fake_result)

    # 一段假的样本文本
    sample_text = "商法讲义\n\n第一章 归责原则\n过错责任是侵权责任的一般归责原则..."

    try:
        result = material_classifier.classify_material(
            material_id=material_id,
            sample_text=sample_text,
            doc_title="商法讲义",
            llm=fake_llm,
        )

        if not result["success"]:
            _fail(f"识别失败：{result['error']}")
            return False

        _ok(f"识别成功：课程名「{result['course_name']}」，置信度 {result['course_confidence']}")
        _ok(f"识别出 {len(result['knowledge_points'])} 个知识点")
        _ok(f"假 LLM 被调用 {fake_llm.calls} 次")

        # 验证数据库里的状态变了
        material = material_store.get_by_id(material_id)
        if material["detection_status"] != material_store.STATUS_SUGGESTED:
            _fail(f"识别后状态应为 suggested，实际 {material['detection_status']}")
            return False
        _ok("识别后状态变为 suggested")

        # 验证 detected_* 字段写入了
        if material["detected_course_name"] != f"{TEST_COURSE_PREFIX}商法":
            _fail(f"detected_course_name 不对：{material['detected_course_name']}")
            return False
        _ok("detected_course_name 写入正确")

        if len(material["detected_knowledge_points"]) != 3:
            _fail(f"知识点数量不对：期望 3，实际 {len(material['detected_knowledge_points'])}")
            return False
        _ok("detected_knowledge_points 写入正确")

        # 验证 course_id 还没写（这是"识别只作建议"的体现）
        if material["course_id"] is not None:
            _fail(f"识别阶段不该写 course_id，实际 {material['course_id']}")
            return False
        _ok("course_id 仍为 NULL（识别只作建议）")

        return True

    except Exception as exc:  # noqa: BLE001
        _fail(f"识别异常：{type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return False


def check_apply_suggestion(material_id: int) -> bool:
    """应用识别建议：自动建课程、建知识点、关联资料。"""
    _section("4. 应用识别建议")

    try:
        result = material_classifier.apply_suggestion(
            material_id=material_id,
            confirmed_by="verify_script",
        )

        if not result["success"]:
            _fail(f"应用建议失败：{result['error']}")
            return False

        _ok(f"建课程：id={result['course_id']}，created_course={result['created_course']}")
        _ok(f"建知识点：{result['created_knowledge_points']} 个")

        # 验证资料已关联到课程
        material = material_store.get_by_id(material_id)
        if material["course_id"] != result["course_id"]:
            _fail(f"资料未关联到课程：期望 {result['course_id']}，实际 {material['course_id']}")
            return False
        _ok("资料已关联到课程")

        if material["detection_status"] != material_store.STATUS_CONFIRMED:
            _fail(f"状态应为 confirmed，实际 {material['detection_status']}")
            return False
        _ok("状态变为 confirmed")

        # 验证知识点真的建到课程下了
        kps = knowledge_point.list_by_course(result["course_id"], use_cache=False)
        if len(kps) != 3:
            _fail(f"课程下知识点数不对：期望 3，实际 {len(kps)}")
            return False
        _ok(f"课程下有 {len(kps)} 个知识点")

        return True

    except Exception as exc:  # noqa: BLE001
        _fail(f"应用建议异常：{type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return False


def check_merge_two_materials() -> bool:
    """测试合并：两份资料归到同一门课。"""
    _section("5. 合并两份资料到同一门课")

    try:
        # 建两份资料
        mid_a = material_store.create(
            source_file=f"{TEST_MATERIAL_PREFIX}民法讲义1.pdf",
            kind="pdf",
            chunk_count=10,
        )
        mid_b = material_store.create(
            source_file=f"{TEST_MATERIAL_PREFIX}民法讲义2.pdf",
            kind="pdf",
            chunk_count=8,
        )
        _ok(f"建了两份资料：id={mid_a}, id={mid_b}")

        # 用假 LLM 识别两份资料（都识别成同一门课）
        fake_result = {
            "course_name": f"{TEST_COURSE_PREFIX}民法",
            "course_confidence": 0.9,
            "knowledge_points": [
                {"name": "测试知识点_物权", "confidence": 0.9},
                {"name": "测试知识点_债权", "confidence": 0.85},
            ],
            "reasoning": "资料内容关于民法。",
        }

        for mid in [mid_a, mid_b]:
            material_classifier.classify_material(
                material_id=mid,
                sample_text="民法讲义内容...",
                llm=FakeLLM(fake_result),
            )
        _ok("两份资料都识别完成")

        # 建目标课程
        target_course_id = course.create(
            name=f"{TEST_COURSE_PREFIX}民法目标",
        )
        _ok(f"建目标课程：id={target_course_id}")

        # 合并两份资料到目标课程
        merge_result = material_merge.merge_materials_to_course(
            material_ids=[mid_a, mid_b],
            target_course_id=target_course_id,
            confirmed_by="verify_script",
        )

        if merge_result["merged_count"] != 2:
            _fail(f"合并数量不对：期望 2，实际 {merge_result['merged_count']}")
            return False
        _ok(f"成功合并 {merge_result['merged_count']} 份资料")

        # 验证两份资料都关联到了目标课程
        for mid in [mid_a, mid_b]:
            material = material_store.get_by_id(mid)
            if material["course_id"] != target_course_id:
                _fail(f"资料 {mid} 未关联到目标课程")
                return False
        _ok("两份资料都关联到目标课程")

        # 验证知识点被合并到目标课程
        kps = knowledge_point.list_by_course(target_course_id, use_cache=False)
        if len(kps) < 2:
            _fail(f"目标课程下知识点太少：{len(kps)}")
            return False
        _ok(f"目标课程下有 {len(kps)} 个知识点（合并了资料的知识点）")

        return True

    except Exception as exc:  # noqa: BLE001
        _fail(f"合并异常：{type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return False


def check_auto_group() -> bool:
    """测试：按建议课程名自动分组。"""
    _section("6. 按建议自动分组")

    try:
        # 建三份资料，两份是商法，一份是民法
        mid_a = material_store.create(source_file=f"{TEST_MATERIAL_PREFIX}auto_商法1.pdf", kind="pdf")
        mid_b = material_store.create(source_file=f"{TEST_MATERIAL_PREFIX}auto_商法2.pdf", kind="pdf")
        mid_c = material_store.create(source_file=f"{TEST_MATERIAL_PREFIX}auto_民法1.pdf", kind="pdf")

        # 识别
        material_classifier.classify_material(
            mid_a, "商法内容...",
            llm=FakeLLM({
                "course_name": f"{TEST_COURSE_PREFIX}自动_商法",
                "course_confidence": 0.9,
                "knowledge_points": [{"name": "测试知识点_归责原则", "confidence": 0.9}],
                "reasoning": "",
            }),
        )
        material_classifier.classify_material(
            mid_b, "商法内容...",
            llm=FakeLLM({
                "course_name": f"{TEST_COURSE_PREFIX}自动_商法",
                "course_confidence": 0.9,
                "knowledge_points": [{"name": "测试知识点_过错推定", "confidence": 0.9}],
                "reasoning": "",
            }),
        )
        material_classifier.classify_material(
            mid_c, "民法内容...",
            llm=FakeLLM({
                "course_name": f"{TEST_COURSE_PREFIX}自动_民法",
                "course_confidence": 0.9,
                "knowledge_points": [{"name": "测试知识点_物权", "confidence": 0.9}],
                "reasoning": "",
            }),
        )
        _ok("三份资料识别完成")

        # 自动分组
        group_result = material_merge.merge_by_suggested_course(
            material_ids=[mid_a, mid_b, mid_c],
            confirmed_by="verify_script",
        )

        if len(group_result["groups"]) != 2:
            _fail(f"分组数不对：期望 2，实际 {len(group_result['groups'])}")
            return False
        _ok(f"分成了 {len(group_result['groups'])} 组")

        # 检查每组的资料数
        for course_name, info in group_result["groups"].items():
            expected = 2 if "商法" in course_name else 1
            if len(info["material_ids"]) != expected:
                _fail(f"组「{course_name}」资料数不对：期望 {expected}，实际 {len(info['material_ids'])}")
                return False
        _ok("每组的资料数正确")

        return True

    except Exception as exc:  # noqa: BLE001
        _fail(f"自动分组异常：{type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================
# 主流程
# ==============================================================
def main() -> int:
    """入口。"""
    print("=" * 60)
    print("阶段二验证脚本")
    print("=" * 60)

    # 先清理一遍
    _cleanup()

    # 1. 连通性
    if not check_connections():
        return 1

    # 2. 建资料
    material_id = check_create_material()
    if material_id is None:
        _cleanup()
        return 1

    try:
        # 3. 识别
        if not check_classify(material_id):
            return 1

        # 4. 应用建议
        if not check_apply_suggestion(material_id):
            return 1

        # 5. 合并
        if not check_merge_two_materials():
            return 1

        # 6. 自动分组
        if not check_auto_group():
            return 1

    finally:
        # 清理测试数据
        _section("清理测试数据")
        _cleanup()
        _ok("清理完成")

    # 结论
    _section("结论")
    print("  阶段二全部通过。")
    print()
    print("  说明：以上验证用的是假 LLM，不产生任何 API 费用。")
    print()
    print("  如果想用真实 LLM 试一次识别效果，可以这样：")
    print()
    print("    python -c \"")
    print("    from app.ai import material_classifier")
    print("    from app.database import materials as material_store")
    print("    from app.ai.llm_client import LLMClient")
    print("    # 先建一份资料（假设 id=1）")
    print("    result = material_classifier.classify_material(")
    print("        1, '这里放一段真实的资料文本...', llm=LLMClient())")
    print("    print(result)")
    print("    \"")
    print()
    print("  需要 .env 里配好 LLM_API_KEY。")

    return 0


if __name__ == "__main__":
    sys.exit(main())