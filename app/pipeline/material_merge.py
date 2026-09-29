# -*- coding: utf-8 -*-
"""资料合并：把多份资料归到同一门课。

【什么场景会用到】

    1. 上传了 5 份资料，LLM 把其中 3 份识别成"商法"，2 份识别成"民法"。
       但管理员知道它们其实是同一门课——需要合并。

    2. 上传了「商法 - 讲义1.pdf」和「商法 - 讲义2.pdf」，
       LLM 识别课程名不同（一个说"商法"，一个说"商法基础"），
       管理员手动指定它们属于同一门课。

    3. 一份资料本来归到 A 课，后来发现归错了，改到 B 课。

【合并做了三件事】

    1. 把资料 A 的 course_id 改成课程 B
    2. 资料 A 识别出的知识点，合并进课程 B 的知识点列表（同名的去重）
    3. 写 material_course_map 更新归属记录

【与 course.merge 的区别】

    course.merge 是"把一整门课合并到另一门"，
    涉及迁移题库、错题、试卷等一堆东西。

    material_merge 是"把几份资料归到同一门课"，
    只动资料归属，不涉及题目（因为资料刚上传，还没出题）。

    所以两者是不同层级的操作，不能混用。
"""

from __future__ import annotations

from typing import Any

from app.database import courses as course, knowledge_points as knowledge_point, materials as material_store


# ==============================================================
# 主函数
# ==============================================================
def merge_materials_to_course(
    material_ids: list[int],
    target_course_id: int,
    confirmed_by: str = "",
    create_missing_knowledge_points: bool = True,
) -> dict[str, Any]:
    """把多份资料归到同一门课。

    Args:
        material_ids: 要合并的资料 id 列表。
        target_course_id: 目标课程 id。
        confirmed_by: 操作人。
        create_missing_knowledge_points: 是否把资料识别出的知识点
            也合并进课程（默认 True）。

    Returns:
        {
          "success": True/False,
          "merged_count": 成功合并几份,
          "failed": [{"material_id": 1, "error": "..."}, ...],
          "created_knowledge_points": 新建了几个知识点,
          "target_course_id": 目标课程 id,
          "target_course_name": 目标课程名,
        }
    """
    # 先确认目标课程存在
    target_course = course.get_by_id(target_course_id)
    if target_course is None:
        return {
            "success": False,
            "merged_count": 0,
            "failed": [{"material_id": mid, "error": f"目标课程 id={target_course_id} 不存在"}
                       for mid in material_ids],
            "created_knowledge_points": 0,
            "target_course_id": target_course_id,
            "target_course_name": "",
        }

    merged_count = 0
    failed: list[dict[str, Any]] = []
    all_kp_names: list[str] = []

    for mid in material_ids:
        material = material_store.get_by_id(mid)
        if material is None:
            failed.append({"material_id": mid, "error": "资料不存在"})
            continue

        # 检查是不是本来就在目标课程下
        if material.get("course_id") == target_course_id:
            failed.append({"material_id": mid, "error": "资料已经在该课程下"})
            continue

        try:
            # 关联资料到目标课程
            material_store.confirm_classification(
                material_id=mid,
                course_id=target_course_id,
                confirmed_by=confirmed_by,
            )
            merged_count += 1

            # 收集这份资料识别出的知识点名（用于后面合并进课程）
            if create_missing_knowledge_points:
                for item in (material.get("detected_knowledge_points") or []):
                    name = item.get("name") if isinstance(item, dict) else None
                    if name:
                        all_kp_names.append(str(name).strip())

        except Exception as exc:  # noqa: BLE001 - 单份失败不该让整批失败
            failed.append({"material_id": mid, "error": str(exc)})

    # 把收集到的知识点批量建到目标课程下。
    # bulk_create 会自动跳过已存在的，所以不用先去重。
    created_kp_count = 0
    if create_missing_knowledge_points and all_kp_names:
        try:
            # 去重（同一份资料里可能有重复的知识点名，多份资料也可能有）
            unique_names = list(dict.fromkeys(all_kp_names))
            knowledge_point.bulk_create(target_course_id, unique_names)
            created_kp_count = len(unique_names)
        except Exception as exc:  # noqa: BLE001 - 建知识点失败不影响资料归属
            failed.append({
                "material_id": -1,
                "error": f"知识点合并失败（资料归属已成功）：{exc}",
            })

    return {
        "success": len(failed) == 0,
        "merged_count": merged_count,
        "failed": failed,
        "created_knowledge_points": created_kp_count,
        "target_course_id": target_course_id,
        "target_course_name": target_course["name"],
    }


# ==============================================================
# 快捷方式
# ==============================================================
def merge_by_suggested_course(
    material_ids: list[int],
    confirmed_by: str = "",
) -> dict[str, Any]:
    """按 LLM 建议的课程名合并资料。

    【用途】管理员的批量操作：选中一批资料，
        按它们各自的"建议课程名"自动归类。
        建议课程名相同的归到一起。

    【与 merge_materials_to_course 的区别】
        上一个函数是"全部归到指定的一门课"。
        本函数是"按建议自动分组，每组归到自己的课"。

    Args:
        material_ids: 资料 id 列表。
        confirmed_by: 操作人。

    Returns:
        {
          "success": True/False,
          "groups": {
            "商法": {"course_id": 1, "material_ids": [1, 2, 3], "created": False},
            "民法": {"course_id": 5, "material_ids": [4, 5], "created": True},
          },
          "errors": [...],
        }
    """
    # 按建议课程名分组
    groups: dict[str, list[int]] = {}
    errors: list[dict[str, Any]] = []

    for mid in material_ids:
        material = material_store.get_by_id(mid)
        if material is None:
            errors.append({"material_id": mid, "error": "资料不存在"})
            continue

        suggested = (material.get("detected_course_name") or "").strip()
        if not suggested:
            errors.append({"material_id": mid, "error": "资料没有被识别出课程名"})
            continue

        groups.setdefault(suggested, []).append(mid)

    # 逐个分组处理
    result_groups: dict[str, dict[str, Any]] = {}
    for course_name, mids in groups.items():
        # 查课程，不存在就建
        existing = course.get_by_name(course_name)
        created = False
        if existing is not None:
            course_id = int(existing["id"])
        else:
            course_id = course.create(name=course_name)
            created = True

        # 把这一组资料归到该课程
        merge_result = merge_materials_to_course(
            material_ids=mids,
            target_course_id=course_id,
            confirmed_by=confirmed_by,
        )

        result_groups[course_name] = {
            "course_id": course_id,
            "material_ids": mids,
            "created": created,
            "merged_count": merge_result["merged_count"],
            "failed": merge_result["failed"],
        }

    return {
        "success": len(errors) == 0,
        "groups": result_groups,
        "errors": errors,
    }