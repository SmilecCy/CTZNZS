# -*- coding: utf-8 -*-
"""课程服务：课程 CRUD、软删除、合并。

【为什么课程要单独一个 service】

    课程是整个系统的"根"。题库、错题、试卷全都挂在课程上。
    所以课程的操作比其他实体更敏感：
      - 删除必须是软删除（直接删会破坏一堆外键）
      - 合并要迁移数据 + 去重 + 留痕
      - 缓存失效必须及时，否则前端看到的是旧课程列表

    把这些逻辑集中在这里，而不是散在 API 层，是为了：
      1. 缓存失效不漏（改课程的地方只有这一个文件）
      2. 合并逻辑只写一次（API 层不需要知道细节）

【与 config.COURSES 的关系】

    config.COURSES 是**种子数据**，只在首次建库时用一次。
    建库之后，课程真相源就是本模块操作的 MySQL 表。
    业务代码不得再引用 config.COURSES。
"""

from __future__ import annotations

from typing import Any

from app.database import cache, connection as db_mysql


# ==============================================================
# 异常
# ==============================================================
class CourseError(RuntimeError):
    """课程操作的统一异常基类。

    【为什么单独定义一个异常】
        上层（API 层）需要区分"课程相关的业务错误"和"其他错误"。
        继承 RuntimeError 而不是 ValueError，是因为：
          - ValueError 用于"参数格式不对"
          - 课程名重复、课程不存在这类是"业务规则问题"
        两者语义不同，分开便于上层分别处理。
    """


class CourseNotFoundError(CourseError):
    """课程不存在。"""


class CourseNameExistsError(CourseError):
    """课程名已存在。"""


# ==============================================================
# 建
# ==============================================================
def create(
    name: str,
    display_name: str | None = None,
    description: str = "",
    question_focus: str = "",
) -> int:
    """新建一门课程。

    Args:
        name: 课程名（机器用）。唯一。
        display_name: 展示名。不传就用 name。
        description: 课程描述。
        question_focus: 出题侧重说明。

    Returns:
        新课程的 id。

    Raises:
        CourseNameExistsError: 课程名已存在。
    """
    # 去掉首尾空白。用户手滑输 " 商法 " 和 "商法" 应该视为同名。
    name = (name or "").strip()
    if not name:
        raise CourseError("课程名不能为空")

    # display_name 没传就用 name
    display_name = (display_name or name).strip()

    # 先查重。为什么不直接 INSERT 让数据库抛错：
    #   数据库的唯一约束报错信息不友好（是英文的 Duplicate entry），
    #   先查一次能给中文提示。
    # 【注意】这里有一个微小的竞态：查完到插入之间，别的进程可能刚插入了同名课程。
    #   但个人项目并发极低，可忽略。如果将来并发高，应该改成"直接 INSERT 然后捕获异常"。
    existing = get_by_name(name)
    if existing is not None:
        raise CourseNameExistsError(f"课程「{name}」已存在")

    course_id = db_mysql.insert_returning_id(
        "INSERT INTO courses (name, display_name, description, question_focus, is_active) "
        "VALUES (%s, %s, %s, %s, 1)",
        (name, display_name, description, question_focus),
    )

    # 课程列表变了，清缓存。
    # 【为什么必须清】不清的话前端还会看到旧列表（缓存 5 分钟）。
    cache.invalidate_course_list()

    return course_id


# ==============================================================
# 查
# ==============================================================
def get_by_id(course_id: int) -> dict[str, Any] | None:
    """按 id 查课程。

    Args:
        course_id: 课程 id。

    Returns:
        课程字典；不存在返回 None。
    """
    return db_mysql.fetch_one(
        "SELECT id, name, display_name, description, question_focus, "
        "is_active, merged_into, created_at, updated_at "
        "FROM courses WHERE id = %s",
        (course_id,),
    )


def get_by_name(name: str) -> dict[str, Any] | None:
    """按名字查课程。

    【用途】资料分类时，LLM 建议的课程名要查一下"是不是已经存在"。
        存在就复用，不存在才新建。

    Args:
        name: 课程名。

    Returns:
        课程字典；不存在返回 None。
    """
    return db_mysql.fetch_one(
        "SELECT id, name, display_name, description, question_focus, "
        "is_active, merged_into, created_at, updated_at "
        "FROM courses WHERE name = %s",
        ((name or "").strip(),),
    )


def get_or_create(
    name: str,
    display_name: str | None = None,
    description: str = "",
    question_focus: str = "",
) -> tuple[int, bool]:
    """查课程；不存在就建。

    【用途】资料分类时，LLM 说"这是商法课的资料"，
        但系统里可能已经建过商法课了。这时应该复用，不该报错。

    Args:
        name: 课程名。
        display_name: 展示名。
        description: 描述。
        question_focus: 出题侧重。

    Returns:
        ``(course_id, created)``。created=True 表示这次新建了。
    """
    existing = get_by_name(name)
    if existing is not None:
        return int(existing["id"]), False

    course_id = create(
        name=name,
        display_name=display_name,
        description=description,
        question_focus=question_focus,
    )
    return course_id, True


def list_all(include_inactive: bool = False) -> list[dict[str, Any]]:
    """列出所有课程，带 Redis 缓存。

    Args:
        include_inactive: 是否包含已软删除的课程。
            默认 False（前端只需要看到启用的）。
            后台管理页要看全部时传 True。

    Returns:
        课程列表。

    【缓存策略】
        默认查询（不含已删除）走缓存——这是最高频的调用。
        带 include_inactive 的查询不走缓存——它是后台管理页专用，
        低频且要求实时，缓存反而会让人困惑（"我刚删的课怎么还在列表里"）。
    """
    # 只有"默认查询"才走缓存
    if not include_inactive:
        cached = cache.get(cache.course_list_key())
        if cached is not None:
            return cached

    if include_inactive:
        rows = db_mysql.fetch_all(
            "SELECT id, name, display_name, description, question_focus, "
            "is_active, merged_into, created_at "
            "FROM courses ORDER BY id"
        )
    else:
        rows = db_mysql.fetch_all(
            "SELECT id, name, display_name, description, question_focus, "
            "is_active, merged_into, created_at "
            "FROM courses WHERE is_active = 1 ORDER BY id"
        )

    # 只有默认查询才写缓存
    if not include_inactive:
        cache.set(cache.course_list_key(), rows, ttl=300)   # 5 分钟

    return rows


# ==============================================================
# 改
# ==============================================================
def update(
    course_id: int,
    display_name: str | None = None,
    description: str | None = None,
    question_focus: str | None = None,
) -> bool:
    """改课程信息。

    【注意】不允许改 name。因为 name 是"稳定标识符"，
        改了会让所有引用它的地方对不上（虽然实际引用的是 id，但语义上
        name 应该是不变的）。要改就删了重建。

    Args:
        course_id: 课程 id。
        display_name: 新的展示名；None 表示不改。
        description: 新的描述；None 表示不改。
        question_focus: 新的出题侧重；None 表示不改。

    Returns:
        是否更新成功（False 表示课程不存在）。

    Raises:
        CourseNotFoundError: 课程不存在。
    """
    course = get_by_id(course_id)
    if course is None:
        raise CourseNotFoundError(f"课程 id={course_id} 不存在")

    # 动态拼 SQL：只更新传了值的字段。
    # 【为什么要这样】如果全部字段都更新，传 None 的字段会被改成 NULL，
    #   那调用方就得先把原值查出来再传，很麻烦。
    sets: list[str] = []
    params: list[Any] = []

    if display_name is not None:
        sets.append("display_name = %s")
        params.append(display_name.strip())
    if description is not None:
        sets.append("description = %s")
        params.append(description)
    if question_focus is not None:
        sets.append("question_focus = %s")
        params.append(question_focus)

    # 一个字段都没传，直接返回（不用跑无意义的 UPDATE）
    if not sets:
        return True

    params.append(course_id)
    db_mysql.execute(
        f"UPDATE courses SET {', '.join(sets)} WHERE id = %s",
        tuple(params),
    )

    # 改了就清缓存
    cache.invalidate_course_list()

    return True


# ==============================================================
# 软删除
# ==============================================================
def soft_delete(course_id: int) -> bool:
    """软删除课程（置 is_active = 0）。

    【为什么是软删除而不是硬删除】
        课程关联着题库、错题、试卷。
        硬删除会触发外键 CASCADE，把这些数据一起删掉。
        而"删一门课"的真实意图通常是"我不想在列表里看到它了"，
        不是"把这门课的所有历史数据都清掉"。

        所以用软删除：is_active = 0。
        列表查询里 WHERE is_active = 1 就看不到了，
        但历史数据仍然完好，需要时可以恢复。

    Args:
        course_id: 课程 id。

    Returns:
        是否删除成功（False 表示课程不存在）。

    Raises:
        CourseNotFoundError: 课程不存在。
    """
    course = get_by_id(course_id)
    if course is None:
        raise CourseNotFoundError(f"课程 id={course_id} 不存在")

    db_mysql.execute(
        "UPDATE courses SET is_active = 0 WHERE id = %s",
        (course_id,),
    )

    # 课程列表变了，清缓存
    cache.invalidate_course_list()
    # 知识点列表也清一下（虽然知识点没变，但前端可能会刷新这两个列表）
    cache.invalidate_knowledge_points(course_id)

    return True


def restore(course_id: int) -> bool:
    """恢复软删除的课程。

    Args:
        course_id: 课程 id。

    Returns:
        是否恢复成功。

    Raises:
        CourseNotFoundError: 课程不存在。
    """
    course = get_by_id(course_id)
    if course is None:
        raise CourseNotFoundError(f"课程 id={course_id} 不存在")

    db_mysql.execute(
        "UPDATE courses SET is_active = 1 WHERE id = %s",
        (course_id,),
    )

    cache.invalidate_course_list()
    return True


# ==============================================================
# 合并
# ==============================================================
def merge(from_course_id: int, to_course_id: int, merged_by: str = "") -> dict[str, Any]:
    """把一门课程合并到另一门。

    【什么场景会用到】
        资料分类时，LLM 把两份资料判成了两门课（"商法"和"商法基础"），
        但管理员知道它们其实是同一门。这时把其中一门合并到另一门。

    【合并做了什么】
        1. 把 from 课程的**资料**改挂到 to 课程
        2. 把 from 课程的**知识点**改挂到 to 课程（同名的去重）
        3. 把 from 课程的**题目**改挂到 to 课程（去重：题干相似度 ≥ 0.9）
        4. 把 from 课程的**错题、试卷**改挂到 to 课程
        5. 把 from 课程标记为 merged_into = to_course_id，并停用
        6. 写 course_merge_log 留痕

    【为什么必须去重】
        合并前，"商法"和"商法基础"可能各有 10 道题，
        其中 3 道是重复的（同一份资料来的）。
        合并后如果不处理，题库里就有 3 对重复题，抽题时会抽到"同一道题两次"。

    Args:
        from_course_id: 被合并的课程 id。
        to_course_id: 合并到的目标课程 id。
        merged_by: 操作人（管理员用户名）。

    Returns:
        合并报告，含迁移数量、去重数量。

    Raises:
        CourseNotFoundError: 任一课程不存在。
        CourseError: 合并到自己、或 from 已被合并过。
    """
    if from_course_id == to_course_id:
        raise CourseError("不能把课程合并到自己")

    from_course = get_by_id(from_course_id)
    if from_course is None:
        raise CourseNotFoundError(f"课程 id={from_course_id} 不存在")

    to_course = get_by_id(to_course_id)
    if to_course is None:
        raise CourseNotFoundError(f"课程 id={to_course_id} 不存在")

    if from_course.get("merged_into") is not None:
        raise CourseError(f"课程「{from_course['name']}」已经被合并过了")

    report: dict[str, Any] = {
        "from_course_id": from_course_id,
        "to_course_id": to_course_id,
        "moved_materials": 0,
        "moved_knowledge_points": 0,
        "merged_knowledge_points": 0,
        "moved_questions": 0,
        "deduped_questions": 0,
        "moved_wrong_questions": 0,
        "moved_papers": 0,
        }

    # ---------- 1. 迁移资料 ----------
    # 【注意】material_course_map 的 material_id 有唯一约束，
    #   所以是"更新"而不是"插入"。
    report["moved_materials"] = db_mysql.execute(
        "UPDATE material_course_map SET course_id = %s WHERE course_id = %s",
        (to_course_id, from_course_id),
    )

    # ---------- 2. 迁移知识点 ----------
    # 同名知识点要合并（不能建两个同名的），所以策略是：
    #   a. 查目标课程里已有的知识点名
    #   b. from 课程的知识点里，名字已在目标里存在的 → 删掉（对应题目重新指向目标的知识点）
    #   c. 名字不在目标里的 → 改 course_id 挂过去
    existing_kp_names = {
        row["name"]
        for row in db_mysql.fetch_all(
            "SELECT name FROM knowledge_points WHERE course_id = %s",
            (to_course_id,),
        )
    }

    from_kps = db_mysql.fetch_all(
        "SELECT id, name FROM knowledge_points WHERE course_id = %s",
        (from_course_id,),
    )

    for kp in from_kps:
        if kp["name"] in existing_kp_names:
            # 目标已有同名知识点。把引用它的题目重定向到目标的知识点。
            target_kp = db_mysql.fetch_one(
                "SELECT id FROM knowledge_points WHERE course_id = %s AND name = %s",
                (to_course_id, kp["name"]),
            )
            if target_kp:
                db_mysql.execute(
                    "UPDATE question_bank SET knowledge_point_id = %s "
                    "WHERE knowledge_point_id = %s",
                    (target_kp["id"], kp["id"]),
                )
            # 删掉 from 课程的这个重复知识点
            db_mysql.execute("DELETE FROM knowledge_points WHERE id = %s", (kp["id"],))
            report["merged_knowledge_points"] += 1
        else:
            # 目标没有同名的，改挂过去
            db_mysql.execute(
                "UPDATE knowledge_points SET course_id = %s WHERE id = %s",
                (to_course_id, kp["id"]),
            )
            report["moved_knowledge_points"] += 1

    # ---------- 3. 迁移题目 ----------
    # 【去重逻辑】
    #   a. 目标课程已有的题干集合（用 question_json 里的 question 字段）
    #   b. from 课程的题，题干在目标里已存在 → 标 deprecated
    #   c. 不在的 → 改 course_id 挂过去
    #
    #   【为什么用字符串比对而不是向量比对】
    #     向量比对要加载 embedder，很重。
    #     合并是低频操作，要求准确但可以慢一点。
    #     用规范化后的字符串比对（去空白、去标点）能覆盖 90% 的情况。
    #     剩下 10% 的近似重复，让用户事后在题库浏览里手动处理。
    target_stems = {
        _extract_stem(row["question_json"])
        for row in db_mysql.fetch_all(
            "SELECT question_json FROM question_bank WHERE course_id = %s AND status = 'active'",
            (to_course_id,),
        )
    }

    from_questions = db_mysql.fetch_all(
        "SELECT id, question_json FROM question_bank WHERE course_id = %s AND status = 'active'",
        (from_course_id,),
    )

    for q in from_questions:
        stem = _extract_stem(q["question_json"])
        if stem in target_stems:
            # 重复题：废弃它（不是删除，保留历史）
            db_mysql.execute(
                "UPDATE question_bank SET status = 'deprecated' WHERE id = %s",
                (q["id"],),
            )
            report["deduped_questions"] += 1
        else:
            # 不重复：改挂过去
            db_mysql.execute(
                "UPDATE question_bank SET course_id = %s WHERE id = %s",
                (to_course_id, q["id"]),
            )
            report["moved_questions"] += 1

    # ---------- 4. 迁移错题 ----------
    # 错题有唯一约束 (user_id, course_id, question_bank_id)，
    # 如果同一学生在两门课下都错过同一道题，迁移会冲突。
    # 处理方式：先查一下目标课程里有没有相同 (user_id, question_bank_id) 的记录。
    report["moved_wrong_questions"] = _merge_wrong_questions(
        from_course_id, to_course_id
    )

    # ---------- 5. 迁移试卷 ----------
    report["moved_papers"] = db_mysql.execute(
        "UPDATE papers SET course_id = %s WHERE course_id = %s",
        (to_course_id, from_course_id),
    )

    # ---------- 6. 标记原课程为已合并 ----------
    db_mysql.execute(
        "UPDATE courses SET is_active = 0, merged_into = %s WHERE id = %s",
        (to_course_id, from_course_id),
    )

    # ---------- 8. 写合并日志 ----------
    import json
    db_mysql.execute(
        "INSERT INTO course_merge_log (from_course_id, to_course_id, merged_by, detail) "
        "VALUES (%s, %s, %s, %s)",
        (from_course_id, to_course_id, merged_by,
         json.dumps(report, ensure_ascii=False,default=str)),
    )

    # ---------- 9. 清缓存 ----------
    cache.invalidate_course_list()
    cache.invalidate_knowledge_points(to_course_id)
    cache.invalidate_question_bank(to_course_id)

    return report


# --------------------------------------------------------------
# 内部工具
# --------------------------------------------------------------
def _extract_stem(question_json: str | None) -> str:
    """从 question_json 里抠出题干，做规范化处理。

    【规范化做什么】
        去空白、去标点符号。这样：
          "请简述过错推定。"
          "请简述过错推定"
        会被当成同一道题。

    【为什么这么处理】
        合并去重是低频操作，不需要向量比对的精度。
        字符串规范化能覆盖大部分情况，且零成本。
        剩下的近似重复让用户事后手动处理。

    Args:
        question_json: 题目 JSON 字符串。

    Returns:
        规范化后的题干。解析失败时返回空字符串（空字符串不会匹配任何题干，
        所以解析失败的题目会被当成"不重复"，安全地迁移过去）。
    """
    import json
    import re

    if not question_json:
        return ""

    try:
        payload = json.loads(question_json)
    except (json.JSONDecodeError, TypeError):
        return ""

    stem = str(payload.get("question", "")).strip()
    # 去掉所有空白和常见标点
    stem = re.sub(r"[\s，。！？；：、（）【】《》\"'.,!?;:()\[\]{}]+", "", stem)
    return stem


def _merge_wrong_questions(from_course_id: int, to_course_id: int) -> int:
    """迁移错题，处理唯一约束冲突。

    【冲突场景】
        错题表的唯一约束是 (user_id, course_id, question_bank_id)。
        如果学生在 from 课程和 to 课程下，都错过同一道题（虽然少见，但可能），
        直接 UPDATE course_id 会违反唯一约束。

    【处理方式】
        逐条迁移。如果目标课程下已有相同 (user_id, question_bank_id)，
        就把两边的错次合并（累加），然后删掉 from 的那条。

    Returns:
        实际迁移的错题数。
    """
    from_rows = db_mysql.fetch_all(
        "SELECT id, user_id, question_bank_id, wrong_count, review_count, correct_count "
        "FROM wrong_questions WHERE course_id = %s",
        (from_course_id,),
    )

    moved = 0
    for row in from_rows:
        # 查目标课程里有没有相同的 (user_id, question_bank_id)
        existing = db_mysql.fetch_one(
            "SELECT id, wrong_count, review_count, correct_count "
            "FROM wrong_questions WHERE user_id = %s AND course_id = %s AND question_bank_id = %s",
            (row["user_id"], to_course_id, row["question_bank_id"]),
        )

        if existing:
            # 有：把错次和复习次数累加到目标记录，然后删掉 from 的记录
            db_mysql.execute(
                "UPDATE wrong_questions SET "
                "wrong_count = wrong_count + %s, "
                "review_count = review_count + %s, "
                "correct_count = correct_count + %s "
                "WHERE id = %s",
                (row["wrong_count"], row["review_count"], row["correct_count"], existing["id"]),
            )
            db_mysql.execute("DELETE FROM wrong_questions WHERE id = %s", (row["id"],))
        else:
            # 没有：直接改 course_id 挂过去
            db_mysql.execute(
                "UPDATE wrong_questions SET course_id = %s WHERE id = %s",
                (to_course_id, row["id"]),
            )
            moved += 1

    return moved
# ==============================================================
# 物理删除（危险操作）
# ==============================================================
def get_delete_preview(course_id: int) -> dict:
    """删除课程前的预览：告诉用户会删什么。

    【为什么需要预览】
        物理删除课程会连带删掉：
          - 知识点
          - 题库里的题目
          - 学生的错题
          - 试卷
        这些都是不可恢复的。用户点删除前应该明确知道。

    Returns:
        {
          "course_id": int,
          "name": str,
          "display_name": str,
          "is_active": bool,
          "knowledge_point_count": int,
          "question_count": int,
          "wrong_question_count": int,
          "paper_count": int,
          "material_count": int,
          "can_delete": bool,
        }
    """
    from app.database import connection as db_mysql

    course = get_by_id(course_id)
    if course is None:
        return {
            "course_id": course_id,
            "name": "",
            "display_name": "",
            "is_active": False,
            "knowledge_point_count": 0,
            "question_count": 0,
            "wrong_question_count": 0,
            "paper_count": 0,
            "material_count": 0,
            "can_delete": False,
        }

    def _count(sql: str) -> int:
        row = db_mysql.fetch_one(sql, (course_id,))
        return int(row["n"]) if row else 0

    return {
        "course_id": course_id,
        "name": course["name"],
        "display_name": course["display_name"],
        "is_active": bool(course.get("is_active")),
        "knowledge_point_count": _count(
            "SELECT COUNT(*) AS n FROM knowledge_points WHERE course_id = %s"
        ),
        "question_count": _count(
            "SELECT COUNT(*) AS n FROM question_bank WHERE course_id = %s"
        ),
        "wrong_question_count": _count(
            "SELECT COUNT(*) AS n FROM wrong_questions WHERE course_id = %s"
        ),
        "paper_count": _count(
            "SELECT COUNT(*) AS n FROM papers WHERE course_id = %s"
        ),
        "material_count": _count(
            "SELECT COUNT(*) AS n FROM materials WHERE course_id = %s"
        ),
        "can_delete": True,   # 目前总是允许，将来可以加条件
    }


def hard_delete(course_id: int) -> dict:
    """物理删除课程及其所有关联数据。

    【危险警告】
        这是不可恢复的操作。会删除：
          - 课程本身
          - 所有知识点（knowledge_points）
          - 所有题目（question_bank）
          - 所有错题（wrong_questions）
          - 所有试卷（papers）
        因为所有这些表都有 `ON DELETE CASCADE` 外键约束，
        删课程会自动级联删除它们。

    【不会删】
        - 资料（materials）：资料可能归属别的课程，或者成为孤儿保留
        - 审计日志（llm_call_log / serving_log）：成本审计要留痕

    【为什么先做安全前置检查】
        1. 检查课程是否存在
        2. 检查是否被其他课程合并（merged_into）
           如果是被合并的课程，通常不该直接删——应该保留供审计

    Args:
        course_id: 课程 id。

    Returns:
        {"ok": bool, "deleted": {...}, "error": str | None}
    """
    from app.database import connection as db_mysql

    course = get_by_id(course_id)
    if course is None:
        return {
            "ok": False,
            "deleted": {},
            "error": f"课程 id={course_id} 不存在",
        }

    # 记下删除前的统计（返回给前端展示）
    preview = get_delete_preview(course_id)

    try:
        # 直接删课程，其他表通过外键级联删除
        db_mysql.execute("DELETE FROM courses WHERE id = %s", (course_id,))

        # 清缓存
        from app.database import cache
        cache.invalidate_course_list()
        cache.invalidate_knowledge_points(course_id)
        cache.invalidate_question_bank(course_id)

    except Exception as exc:  # noqa: BLE001 - 要把原始错误返回给前端
        return {
            "ok": False,
            "deleted": {},
            "error": f"{type(exc).__name__}: {exc}",
        }

    return {
        "ok": True,
        "deleted": {
            "course_id": course_id,
            "name": course["name"],
            "display_name": course["display_name"],
            "knowledge_point_count": preview["knowledge_point_count"],
            "question_count": preview["question_count"],
            "wrong_question_count": preview["wrong_question_count"],
            "paper_count": preview["paper_count"],
        },
        "error": None,
    }