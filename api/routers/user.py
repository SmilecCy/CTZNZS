# -*- coding: utf-8 -*-
"""用户端路由：出题、作答、判分、错题集、章节匹配、收藏、笔记、统计。

【接口清单】

    GET   /api/user/courses                                课程列表
    GET   /api/user/courses/{course_id}/knowledge-points   知识点列表
    GET   /api/user/courses/{course_id}/chapters           章节树
    POST  /api/user/chapter/match                          章节匹配
    POST  /api/user/questions                              出题（题库优先）
    POST  /api/user/answers                                提交作答（自动判分）
    POST  /api/user/answers/resolve                        按勾选重算分数
    GET   /api/user/wrong-questions                        错题集
    GET   /api/user/wrong-questions/stats                  错题统计
    PATCH /api/user/wrong-questions/{id}                   标记掌握状态
    POST  /api/user/wrong-questions/{id}/review            记录一次复习
    DELETE /api/user/wrong-questions/{id}                  删除错题
    POST  /api/user/favorites/{qid}                        收藏题目
    DELETE /api/user/favorites/{qid}                       取消收藏
    GET   /api/user/favorites                              收藏列表
    POST  /api/user/notes/{qid}                            保存笔记
    GET   /api/user/notes/{qid}                            读取笔记
    GET   /api/user/stats/overview                         学习统计总览
    GET   /api/user/stats/trend                            正确率趋势
    GET   /api/user/stats/knowledge-points                 知识点掌握度

【约束】

    1. **只允许学生身份访问** —— 用 Depends(require_user) 保护
    2. **不涉及任何"建设"类操作** —— 上传、课程管理都不在这里
    3. **所有查询都限定当前用户** —— 学生只能看自己的数据
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status

from api import deps
from api.schemas import (
    AnswerRequest,
    AnswerResponse,
    ChapterMatchRequest,
    ChapterMatchResponse,
    ChapterResponse,
    ChatRequest,
    ChatResponse,
    CourseResponse,
    KnowledgePointResponse,
    MasteryUpdateRequest,
    NoteRequest,
    NoteResponse,
    PointJudgementResponse,
    QuestionRequest,
    QuestionResponse,
    QuotaResponse,
    ResolveRequest,
    ReviewRequest,
    StatsKnowledgePointItem,
    StatsOverviewResponse,
    StatsTrendItem,
    SuccessResponse,
    WrongQuestionResponse,
)
from app.database import answers as answer_mysql, chapters as chapter, courses as course, favorites as favorite, knowledge_points as knowledge_point, notes as note, questions as question_bank_mysql, stats, wrong_book as wrong_book_mysql
from app.ai import chapter_matcher, generator, grader
from app.ai.generator import InsufficientMaterialError
from app.ai.llm_client import LLMClient, LLMError
from app.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_TIMEOUT,
)


# ==============================================================
# 路由器
# ==============================================================
router = APIRouter()


# ==============================================================
# 课程与知识点
# ==============================================================
@router.get(
    "/courses",
    response_model=list[CourseResponse],
    summary="课程列表",
)
async def list_courses(
    current: dict = Depends(deps.require_user),
) -> list[CourseResponse]:
    """列出所有启用的课程。"""
    courses = course.list_all()
    return [
        CourseResponse(
            id=c["id"],
            name=c["name"],
            display_name=c["display_name"],
            description=c.get("description"),
            question_focus=c.get("question_focus"),
        )
        for c in courses
    ]


@router.get(
    "/courses/{course_id}/knowledge-points",
    response_model=list[KnowledgePointResponse],
    summary="知识点列表",
)
async def list_knowledge_points(
    course_id: int,
    current: dict = Depends(deps.require_user),
) -> list[KnowledgePointResponse]:
    """列出某课程的知识点。"""
    c = course.get_by_id(course_id)
    if c is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "COURSE_NOT_FOUND", "message": f"课程 id={course_id} 不存在"},
        )

    kps = knowledge_point.list_by_course(course_id)
    return [
        KnowledgePointResponse(
            id=kp["id"],
            course_id=kp["course_id"],
            name=kp["name"],
            description=kp.get("description"),
            sort_order=kp.get("sort_order", 0),
        )
        for kp in kps
    ]


@router.get(
    "/courses/{course_id}/chapters",
    response_model=list[ChapterResponse],
    summary="章节树",
)
async def list_chapters(
    course_id: int,
    current: dict = Depends(deps.require_user),
) -> list[ChapterResponse]:
    """获取课程的章节树（含子章节）。"""
    c = course.get_by_id(course_id)
    if c is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "COURSE_NOT_FOUND", "message": f"课程 id={course_id} 不存在"},
        )

    tree = chapter.get_chapter_tree(course_id)
    return [
        ChapterResponse(
            id=ch["id"],
            course_id=ch["course_id"],
            parent_id=ch.get("parent_id"),
            name=ch["name"],
            summary=ch.get("summary"),
            sort_order=ch.get("sort_order", 0),
            children=_to_chapter_tree(ch.get("children", [])),
        )
        for ch in tree
    ]


@router.post(
    "/chapter/match",
    response_model=ChapterMatchResponse,
    summary="章节匹配",
)
async def match_chapter(
    payload: ChapterMatchRequest,
    current: dict = Depends(deps.require_user),
) -> ChapterMatchResponse:
    """学生输入章节标题，系统匹配并返回友好回复。"""
    matched = chapter_matcher.match_chapter(payload.input_text, payload.course_id)

    if matched is None:
        return ChapterMatchResponse(
            chapter_id=None,
            chapter_name=None,
            chapter_summary=None,
            reply_text="抱歉，没有找到匹配的章节。请试试输入更准确的章节标题。",
        )

    llm = LLMClient(
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY,
        model=LLM_MODEL,
        timeout=LLM_TIMEOUT,
        temperature=LLM_TEMPERATURE,
    )

    reply = ""
    try:
        reply = chapter_matcher.generate_reply(payload.input_text, matched, llm)
    except LLMError:
        reply = f"好的，「{matched['name']}」。{matched.get('summary', '')}你想做选择题还是简答题？"

    chapter_matcher.log_chapter_request(
        user_id=current["id"],
        course_id=payload.course_id,
        chapter_id=matched["id"],
        input_text=payload.input_text,
        matched_name=matched["name"],
        reply_text=reply,
    )

    return ChapterMatchResponse(
        chapter_id=matched["id"],
        chapter_name=matched["name"],
        chapter_summary=matched.get("summary"),
        reply_text=reply,
    )


# ==============================================================
# 对话式出题（一键匹配 + 出题）
# ==============================================================
def _parse_message(message: str) -> tuple[str, str, int, int]:
    """从用户消息中解析：章节名、题型模式、选择题数、简答题数。

    默认每次出题 10道选择 + 1道简答。学生可选全选择/全简答。

    支持格式：
        "第一章 商法概述"                      → ("第一章 商法概述", "混合", 10, 1)
        "公司法"                               → ("公司法", "混合", 10, 1)
        "第一章 商法概述 选择题"                → ("第一章 商法概述", "全选择", 10, 0)
        "商法概述，简答题"                      → ("商法概述", "全简答", 0, 10)
        "公司法 5道选择题 3道简答题"            → ("公司法", "混合", 5, 3)

    返回 (chapter_text, type_mode, choice_count, short_answer_count)。
    type_mode: "混合" | "全选择" | "全简答"
    """
    # 默认：10道选择 + 1道简答
    choice_count = 10
    short_answer_count = 1
    type_mode = "混合"

    # 检测是否明确只选了某一种题型
    has_choice = "选择" in message
    has_short = "简答" in message

    if has_choice and not has_short:
        type_mode = "全选择"
        choice_count = 10
        short_answer_count = 0
    elif has_short and not has_choice:
        type_mode = "全简答"
        choice_count = 0
        short_answer_count = 10

    # 匹配题数：N道选择题 / N道简答题
    m_choice = re.search(r"(\d+)\s*道\s*选择", message)
    if m_choice:
        choice_count = max(1, min(50, int(m_choice.group(1))))
    m_short = re.search(r"(\d+)\s*道\s*简答", message)
    if m_short:
        short_answer_count = max(1, min(10, int(m_short.group(1))))

    # 如果没有具体题型数，但有通用 "N道/N题"
    if type_mode == "混合":
        m = re.search(r"(\d+)\s*[道题个]", message)
        if m and not m_choice and not m_short:
            n = max(1, min(50, int(m.group(1))))
            choice_count = n
    elif not m_choice and not m_short:
        m = re.search(r"(\d+)\s*[道题个]", message)
        if m:
            n = max(1, min(50, int(m.group(1))))
            if type_mode == "全选择":
                choice_count = n
            else:
                short_answer_count = min(10, n)

    # 提取章节名（去掉题型和题数部分）
    chapter_text = message
    chapter_text = re.sub(r"\d+\s*道\s*(选择|简答)", "", chapter_text)
    chapter_text = re.sub(r"\d+\s*[道题个]", "", chapter_text)
    chapter_text = re.sub(r"[,，]\s*(选择|简答)", r"\1", chapter_text)
    chapter_text = re.sub(r"[(（].*?[)）]", "", chapter_text)
    chapter_text = re.sub(r"[,，]\s*$", "", chapter_text)
    chapter_text = chapter_text.strip()

    # 从章节名中去掉纯粹的"选择题""简答题"后缀
    chapter_text = re.sub(r"\s*(选择题|简答题)\s*$", "", chapter_text)
    chapter_text = chapter_text.strip()

    return chapter_text, type_mode, choice_count, short_answer_count


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="对话式出题",
)
async def chat(
    payload: ChatRequest,
    current: dict = Depends(deps.require_user),
) -> ChatResponse:
    """学生输入章节名称，系统匹配章节并出题，一次返回所有结果。

    默认出题 10道选择 + 1道简答，题库:LLM = 7:3 随机混合。
    流程：解析消息 → 匹配章节 → 查配额 → 出题 → 返回
    """
    chapter_text, type_mode, choice_count, short_answer_count = _parse_message(payload.message)

    if not chapter_text:
        return ChatResponse(
            reply="请告诉我你想练习哪个章节，例如\"第一章 商法概述\"",
            quota=_get_quota(0, 0),
        )

    # 1. 匹配章节
    matched = chapter_matcher.match_chapter(chapter_text, payload.course_id)
    if matched is None:
        return ChatResponse(
            reply="没找到对应章节，请换个说法试试。例如\"商法概述\"、\"第一章 公司法\"",
            quota=_get_quota(0, 0),
        )

    chapter_id = int(matched["id"])
    chapter_name = str(matched["name"])
    chapter_summary = matched.get("summary")

    # 2. 查配额
    choice_used = question_bank_mysql.count_questions(
        payload.course_id, chapter_name, "选择"
    )
    short_answer_used = question_bank_mysql.count_questions(
        payload.course_id, chapter_name, "简答"
    )

    # 配额检查
    if choice_count > 0 and choice_used >= 50:
        return ChatResponse(
            reply=f"本章选择题已达上限50道，请先删除部分题目。当前 {choice_used}/50",
            chapter_id=chapter_id,
            chapter_name=chapter_name,
            chapter_summary=chapter_summary,
            quota=_get_quota(choice_used, short_answer_used),
        )
    if short_answer_count > 0 and short_answer_used >= 10:
        return ChatResponse(
            reply=f"本章简答题已达上限10道，请先删除部分题目。当前 {short_answer_used}/10",
            chapter_id=chapter_id,
            chapter_name=chapter_name,
            chapter_summary=chapter_summary,
            quota=_get_quota(choice_used, short_answer_used),
        )

    # 3. 出题：分别生成选择题和简答题，题库:LLM = 7:3
    all_questions: list[dict[str, Any]] = []
    total_from_bank = 0
    total_from_llm = 0
    errors: list[str] = []

    def _gen_one_type(qtype: str, q_count: int):
        nonlocal total_from_bank, total_from_llm
        if q_count <= 0:
            return
        try:
            r = generator.get_questions(
                course_id=payload.course_id,
                knowledge_point=chapter_name,
                question_type=qtype,
                difficulty="中",
                count=q_count,
            )
            all_questions.extend(r["questions"])
            total_from_bank += r["source_summary"]["from_bank"]
            total_from_llm += r["source_summary"]["from_llm"]
        except InsufficientMaterialError as exc:
            errors.append(str(exc))
        except ValueError as exc:
            errors.append(str(exc))

    _gen_one_type("选择", choice_count)
    _gen_one_type("简答", short_answer_count)

    if errors and not all_questions:
        return ChatResponse(
            reply=f"出题失败：{'；'.join(errors)}",
            chapter_id=chapter_id,
            chapter_name=chapter_name,
            chapter_summary=chapter_summary,
            quota=_get_quota(choice_used, short_answer_used),
        )

    # 4. 重新计算配额（含刚刚出的题）
    choice_used = question_bank_mysql.count_questions(
        payload.course_id, chapter_name, "选择"
    )
    short_answer_used = question_bank_mysql.count_questions(
        payload.course_id, chapter_name, "简答"
    )

    # 5. 组装回复
    parts: list[str] = []
    if choice_count > 0 and short_answer_count > 0:
        parts.append(
            f"好的，已从{chapter_name}为你准备了"
            f"{choice_count}道选择题 + {short_answer_count}道简答题"
        )
    elif choice_count > 0:
        parts.append(
            f"好的，已从{chapter_name}为你准备了{choice_count}道选择题"
        )
    else:
        parts.append(
            f"好的，已从{chapter_name}为你准备了{short_answer_count}道简答题"
        )

    # 展示来源
    if total_from_bank > 0 and total_from_llm > 0:
        parts.append(f"（题库{total_from_bank}道 + AI生成{total_from_llm}道）")
    elif total_from_bank > 0:
        parts.append("（全部来自题库）")
    elif total_from_llm > 0:
        parts.append("（全部由AI生成）")

    if errors:
        parts.append(f"\n⚠ 部分题目生成失败：{'；'.join(errors)}")

    reply = "".join(parts)

    return ChatResponse(
        reply=reply,
        chapter_id=chapter_id,
        chapter_name=chapter_name,
        chapter_summary=chapter_summary,
        questions=all_questions,
        source_stats={
            "from_bank": total_from_bank,
            "from_llm": total_from_llm,
        },
        quota=_get_quota(choice_used, short_answer_used),
    )


def _get_quota(choice_used: int, short_answer_used: int) -> dict[str, int]:
    return {
        "choice_used": choice_used,
        "choice_limit": 50,
        "short_answer_used": short_answer_used,
        "short_answer_limit": 10,
    }


@router.get(
    "/questions/quota",
    response_model=QuotaResponse,
    summary="出题配额",
)
async def get_quota(
    course_id: int,
    chapter_id: int,
    current: dict = Depends(deps.require_user),
) -> QuotaResponse:
    """查询某章节的出题配额使用情况。"""
    chapter_info = chapter.get_chapter_by_id(chapter_id)
    chapter_name = chapter_info["name"] if chapter_info else ""

    choice_used = question_bank_mysql.count_questions(
        course_id, chapter_name, "选择"
    )
    short_answer_used = question_bank_mysql.count_questions(
        course_id, chapter_name, "简答"
    )

    return QuotaResponse(
        choice_used=choice_used,
        choice_limit=50,
        short_answer_used=short_answer_used,
        short_answer_limit=10,
    )


# ==============================================================
# 出题
# ==============================================================
@router.post(
    "/questions",
    response_model=QuestionResponse,
    summary="出题",
)
async def request_questions(
    payload: QuestionRequest,
    current: dict = Depends(deps.require_user),
) -> QuestionResponse:
    """出题。题库优先，未命中时调用 LLM 生成。"""
    try:
        result = generator.get_questions(
            course_id=payload.course_id,
            knowledge_point=payload.knowledge_point,
            question_type=payload.question_type,
            difficulty=payload.difficulty,
            count=payload.count,
            knowledge_point_id=payload.knowledge_point_id,
        )
    except InsufficientMaterialError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INSUFFICIENT_MATERIAL", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_INPUT", "message": str(exc)},
        ) from exc

    return QuestionResponse(
        questions=result["questions"],
        source_summary=result["source_summary"],
        warnings=result["warnings"],
    )


@router.delete(
    "/questions/{question_id}",
    response_model=SuccessResponse,
    summary="删除题目",
)
async def delete_question(
    question_id: int,
    current: dict = Depends(deps.require_user),
) -> SuccessResponse:
    """删除题目，同时级联删除作答历史、错题记录、收藏、笔记。"""
    from app.database import connection as db_mysql

    question = question_bank_mysql.get_question(question_id)
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "QUESTION_NOT_FOUND", "message": f"题目 id={question_id} 不存在"},
        )

    # 级联删除：作答历史、错题记录、收藏、笔记
    db_mysql.execute("DELETE FROM answer_records WHERE question_id = %s", (question_id,))
    db_mysql.execute("DELETE FROM wrong_questions WHERE question_bank_id = %s", (question_id,))
    db_mysql.execute("DELETE FROM favorites WHERE question_id = %s", (question_id,))
    db_mysql.execute("DELETE FROM notes WHERE question_id = %s", (question_id,))

    ok = question_bank_mysql.deprecate_question(question_id, "user_deleted")
    return SuccessResponse(
        success=ok,
        message="删除成功" if ok else "删除失败",
        data={"question_id": question_id, "knowledge_point": question.get("knowledge_point", "")},
    )


# ==============================================================
# 作答与判分
# ==============================================================
@router.post(
    "/answers",
    response_model=AnswerResponse,
    summary="提交作答",
    description="选择题直接比对；简答题用 LLM 逐要点判分。",
)
async def submit_answer(
    payload: AnswerRequest,
    current: dict = Depends(deps.require_user),
) -> AnswerResponse:
    """提交作答并判分。

    【完整流程】
        1. 查题目
        2. 判分（选择 / 简答）
        3. 写作答流水（answer_records）
        4. 答错时自动收录错题（wrong_questions）
    """
    question = question_bank_mysql.get_question(payload.question_id)
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "QUESTION_NOT_FOUND", "message": f"题目 id={payload.question_id} 不存在"},
        )

    qtype = question.get("question_type")
    qpayload = dict(question.get("payload") or {})
    # 把 course_id 塞进 qpayload 供判分和错题收录用
    qpayload["id"] = question["id"]
    qpayload["course_id"] = question["course_id"]
    qpayload["question_type"] = qtype

    if qtype == "选择":
        return _handle_choice(
            user_id=current["id"],
            course_id=payload.course_id,
            knowledge_point=payload.knowledge_point,
            question=qpayload,
            user_answer=payload.user_answer,
        )

    return _handle_short_answer(
        user_id=current["id"],
        course_id=payload.course_id,
        knowledge_point=payload.knowledge_point,
        question=qpayload,
        user_answer=payload.user_answer,
    )


@router.post(
    "/answers/resolve",
    response_model=AnswerResponse,
    summary="按勾选重算分数",
    description="用户在界面上推翻了 AI 判定后，用这个接口重算最终分数。",
)
async def resolve_answer(
    payload: ResolveRequest,
    current: dict = Depends(deps.require_user),
) -> AnswerResponse:
    """按用户最终勾选的状态重算分数。

    【为什么需要这个接口】
        AI 判分可能误判，用户可以在界面上勾掉/勾上某个要点。
        勾完后需要重新算分——但这个"重算"不必再调 AI，
        只要拿新的 hits 数组按比例算就行。
    """
    question = question_bank_mysql.get_question(payload.question_id)
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "QUESTION_NOT_FOUND", "message": f"题目 id={payload.question_id} 不存在"},
        )

    qpayload = question.get("payload") or {}
    points = [str(p).strip() for p in (qpayload.get("scoring_points") or []) if str(p).strip()]

    if len(payload.hits) != len(points):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "HITS_LENGTH_MISMATCH",
                "message": f"hits 长度 {len(payload.hits)} 与评分要点数 {len(points)} 不一致",
            },
        )

    hit_count, score = grader.resolve_result(payload.hits, points)

    # 按新的分数决定是否算答对
    is_correct = score >= 0.6

    return AnswerResponse(
        is_correct=is_correct,
        score=score,
        reference_answer=str(qpayload.get("reference_answer") or ""),
        comment=f"命中 {hit_count}/{len(points)} 个要点",
        point_results=[
            PointJudgementResponse(point=p, hit=h, reason="")
            for p, h in zip(points, payload.hits)
        ],
        wrong_recorded=False,   # 重算不改错题状态
    )


# ==============================================================
# 错题集
# ==============================================================
@router.get(
    "/wrong-questions",
    response_model=list[WrongQuestionResponse],
    summary="错题集列表",
)
async def list_wrong_questions(
    course_id: int,
    knowledge_point: str | None = None,
    question_type: str | None = None,
    mastery_status: str | None = None,
    order_by: str = "最近答错",
    limit: int = 100,
    current: dict = Depends(deps.require_user),
) -> list[WrongQuestionResponse]:
    """列出当前学生的错题集。"""
    rows = wrong_book_mysql.list_wrong(
        user_id=current["id"],
        course_id=course_id,
        knowledge_point=knowledge_point,
        question_type=question_type,
        mastery_status=mastery_status,
        order_by=order_by,
        limit=limit,
    )
    return [_to_wrong_response(r) for r in rows]


@router.get(
    "/wrong-questions/stats",
    summary="错题统计",
)
async def wrong_question_stats(
    course_id: int,
    current: dict = Depends(deps.require_user),
) -> dict:
    """错题集统计。"""
    return wrong_book_mysql.wrong_stats(current["id"], course_id)


@router.patch(
    "/wrong-questions/{entry_id}",
    response_model=SuccessResponse,
    summary="标记掌握状态",
)
async def update_mastery(
    entry_id: int,
    payload: MasteryUpdateRequest,
    current: dict = Depends(deps.require_user),
) -> SuccessResponse:
    """标记错题的掌握状态。"""
    ok = wrong_book_mysql.set_mastery(entry_id, current["id"], payload.mastered)

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": f"错题 id={entry_id} 不存在或不属于你"},
        )

    label = "已掌握" if payload.mastered else "待复习"
    return SuccessResponse(message=f"已标记为「{label}」")


@router.post(
    "/wrong-questions/{entry_id}/review",
    response_model=SuccessResponse,
    summary="记录一次复习",
)
async def review_wrong_question(
    entry_id: int,
    payload: ReviewRequest,
    current: dict = Depends(deps.require_user),
) -> SuccessResponse:
    """记录一次复习（只记事实，不改掌握状态）。"""
    result = wrong_book_mysql.record_review(entry_id, current["id"], correct=payload.correct)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": f"错题 id={entry_id} 不存在或不属于你"},
        )

    return SuccessResponse(
        message="已记录",
        data={
            "review_count": result.get("review_count"),
            "correct_count": result.get("correct_count"),
            "last_result": result.get("last_result"),
        },
    )


@router.delete(
    "/wrong-questions/{entry_id}",
    response_model=SuccessResponse,
    summary="删除错题",
)
async def delete_wrong_question(
    entry_id: int,
    current: dict = Depends(deps.require_user),
) -> SuccessResponse:
    """删除一条错题。"""
    ok = wrong_book_mysql.remove_wrong(entry_id, current["id"])

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": f"错题 id={entry_id} 不存在或不属于你"},
        )

    return SuccessResponse(message="已删除")


# ==============================================================
# 内部：判分与收录
# ==============================================================
def _handle_choice(
    user_id: int,
    course_id: int,
    knowledge_point: str,
    question: dict,
    user_answer: str,
) -> AnswerResponse:
    """选择题判分。"""
    options = question.get("options") or []
    correct_index = question.get("correct_index")
    reference_answer = question.get("reference_answer") or ""

    # 解析用户作答
    try:
        user_index = int(user_answer)
    except (ValueError, TypeError):
        # 也接受"A"、"B"这种字母
        ua = str(user_answer).strip().upper()
        if len(ua) == 1 and "A" <= ua <= "Z":
            user_index = ord(ua) - ord("A")
        else:
            return AnswerResponse(
                is_correct=False,
                score=0.0,
                reference_answer=reference_answer,
                comment="作答格式不对，应该是选项编号（0 开始）或字母（A/B/C/D）",
            )

    is_correct = user_index == correct_index
    score = 1.0 if is_correct else 0.0

    # 写作答流水
    answer_mysql.record_answer(
        user_id=user_id,
        course_id=course_id,
        question=question,
        user_answer=user_answer,
        is_correct=is_correct,
        score=score,
        graded_by="auto",
    )

    # 答错：自动收录错题
    wrong_recorded = False
    if not is_correct:
        wrong_book_mysql.record_wrong(
            user_id=user_id,
            course_id=course_id,
            question=question,
            user_answer=user_answer,
            knowledge_point=knowledge_point or None,
        )
        wrong_recorded = True

    return AnswerResponse(
        is_correct=is_correct,
        score=score,
        reference_answer=reference_answer,
        comment=question.get("explanation", "") if is_correct else "",
        wrong_recorded=wrong_recorded,
    )


def _handle_short_answer(
    user_id: int,
    course_id: int,
    knowledge_point: str,
    question: dict,
    user_answer: str,
) -> AnswerResponse:
    """简答题判分。"""
    reference_answer = str(question.get("reference_answer") or "")

    # 空白作答：直接判 0，不调 LLM
    if not user_answer.strip():
        answer_mysql.record_answer(
            user_id=user_id,
            course_id=course_id,
            question=question,
            user_answer="",
            is_correct=False,
            score=0.0,
            graded_by="auto",
        )
        wrong_book_mysql.record_wrong(
            user_id=user_id,
            course_id=course_id,
            question=question,
            user_answer="",
            knowledge_point=knowledge_point or None,
        )
        return AnswerResponse(
            is_correct=False,
            score=0.0,
            reference_answer=reference_answer,
            comment="未作答。",
            wrong_recorded=True,
        )

    # 调 LLM 判分
    try:
        result = grader.grade_short_answer(question, user_answer)
    except (LLMError, ValueError) as exc:
        # 判分失败不阻断作答：写流水，不收录错题
        answer_mysql.record_answer(
            user_id=user_id,
            course_id=course_id,
            question=question,
            user_answer=user_answer,
            is_correct=None,
            score=None,
            graded_by="manual",
        )
        return AnswerResponse(
            is_correct=None,
            score=None,
            reference_answer=reference_answer,
            comment="自动判分不可用，请你自行对照参考答案。",
            error=str(exc),
        )

    is_correct = result.score >= 0.6

    # 写作答流水
    answer_mysql.record_answer(
        user_id=user_id,
        course_id=course_id,
        question=question,
        user_answer=user_answer,
        is_correct=is_correct,
        score=result.score,
        graded_by="llm",
    )

    # 答错：收录错题
    wrong_recorded = False
    if not is_correct:
        wrong_book_mysql.record_wrong(
            user_id=user_id,
            course_id=course_id,
            question=question,
            user_answer=user_answer,
            knowledge_point=knowledge_point or None,
        )
        wrong_recorded = True

    return AnswerResponse(
        is_correct=is_correct,
        score=result.score,
        reference_answer=reference_answer,
        comment=result.comment,
        point_results=[
            PointJudgementResponse(point=p.point, hit=p.hit, reason=p.reason)
            for p in result.point_results
        ],
        wrong_recorded=wrong_recorded,
    )


def _to_wrong_response(row: dict) -> WrongQuestionResponse:
    """把数据库行转成响应模型。"""
    return WrongQuestionResponse(
        id=row["id"],
        question_bank_id=row.get("question_bank_id"),
        knowledge_point=row.get("knowledge_point"),
        question_type=row.get("question_type"),
        mastery_status=row.get("mastery_status") or "unmastered",
        mastery_label=row.get("mastery_label") or "待复习",
        wrong_count=row.get("wrong_count", 1),
        review_count=row.get("review_count", 0),
        correct_count=row.get("correct_count", 0),
        last_result=row.get("last_result"),
        error_tags=row.get("error_tags") or [],
        payload=row.get("payload") or {},
    )


def _to_chapter_tree(children: list[dict]) -> list[ChapterResponse]:
    """递归转换章节子节点。"""
    return [
        ChapterResponse(
            id=ch["id"],
            course_id=ch["course_id"],
            parent_id=ch.get("parent_id"),
            name=ch["name"],
            summary=ch.get("summary"),
            sort_order=ch.get("sort_order", 0),
            children=_to_chapter_tree(ch.get("children", [])),
        )
        for ch in children
    ]


# ==============================================================
# 收藏
# ==============================================================
@router.post(
    "/favorites/{qid}",
    response_model=SuccessResponse,
    summary="收藏题目",
)
async def add_favorite(
    qid: int,
    current: dict = Depends(deps.require_user),
) -> SuccessResponse:
    """收藏一道题目。"""
    favorite.add_favorite(current["id"], qid)
    return SuccessResponse(message="已收藏")


@router.delete(
    "/favorites/{qid}",
    response_model=SuccessResponse,
    summary="取消收藏",
)
async def remove_favorite(
    qid: int,
    current: dict = Depends(deps.require_user),
) -> SuccessResponse:
    """取消收藏。"""
    favorite.remove_favorite(current["id"], qid)
    return SuccessResponse(message="已取消收藏")


@router.get(
    "/favorites",
    summary="收藏列表",
)
async def list_favorites(
    course_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    current: dict = Depends(deps.require_user),
) -> dict:
    """列出当前用户的收藏题目。"""
    items = favorite.list_favorites(current["id"], course_id, limit, offset)
    total = favorite.count_favorites(current["id"], course_id)
    return {"items": items, "total": total}


# ==============================================================
# 笔记
# ==============================================================
@router.post(
    "/notes/{qid}",
    response_model=SuccessResponse,
    summary="保存笔记",
)
async def save_note(
    qid: int,
    payload: NoteRequest,
    current: dict = Depends(deps.require_user),
) -> SuccessResponse:
    """保存或更新题目笔记。"""
    note.save_note(current["id"], qid, payload.content)
    return SuccessResponse(message="笔记已保存")


@router.get(
    "/notes/{qid}",
    response_model=NoteResponse,
    summary="读取笔记",
)
async def get_note(
    qid: int,
    current: dict = Depends(deps.require_user),
) -> NoteResponse:
    """读取某题的笔记。"""
    content = note.get_note(current["id"], qid)
    return NoteResponse(question_id=qid, content=content or "")


# ==============================================================
# 学习统计
# ==============================================================
@router.get(
    "/stats/overview",
    response_model=StatsOverviewResponse,
    summary="学习统计总览",
)
async def get_stats_overview(
    course_id: int,
    current: dict = Depends(deps.require_user),
) -> StatsOverviewResponse:
    """获取学习统计总览数据。"""
    data = stats.get_overview(current["id"], course_id)
    return StatsOverviewResponse(**data)


@router.get(
    "/stats/trend",
    response_model=list[StatsTrendItem],
    summary="正确率趋势",
)
async def get_stats_trend(
    course_id: int,
    days: int = 30,
    current: dict = Depends(deps.require_user),
) -> list[StatsTrendItem]:
    """获取最近 N 天的正确率趋势。"""
    rows = stats.get_trend(current["id"], course_id, days)
    return [
        StatsTrendItem(date=str(r["date"]), count=r["count"], accuracy=r["accuracy"])
        for r in rows
    ]


@router.get(
    "/stats/knowledge-points",
    response_model=list[StatsKnowledgePointItem],
    summary="知识点掌握度",
)
async def get_stats_knowledge_points(
    course_id: int,
    current: dict = Depends(deps.require_user),
) -> list[StatsKnowledgePointItem]:
    """获取各知识点的掌握度。"""
    rows = stats.get_knowledge_point_mastery(current["id"], course_id)
    return [
        StatsKnowledgePointItem(
            knowledge_point=r["knowledge_point"],
            total=r["total"],
            correct=r["correct"],
            accuracy=r["accuracy"],
        )
        for r in rows
    ]