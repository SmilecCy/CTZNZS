# -*- coding: utf-8 -*-
"""Pydantic 请求/响应模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ==============================================================
# 认证
# ==============================================================
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    display_name: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=200)


class LoginRequest(BaseModel):
    username: str
    password: str
    role: str = "user"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict[str, Any]


class MeResponse(BaseModel):
    id: int
    username: str
    role: str
    display_name: str


# ==============================================================
# 课程与知识点
# ==============================================================
class CourseResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: str | None = None
    question_focus: str | None = None
    is_active: int = 1  # ← 加这一行


class KnowledgePointResponse(BaseModel):
    id: int
    course_id: int
    name: str
    description: str | None = None
    sort_order: int = 0


# ==============================================================
# 出题
# ==============================================================
class QuestionRequest(BaseModel):
    course_id: int
    knowledge_point: str
    question_type: str
    difficulty: str
    count: int = Field(default=1, ge=1, le=10)
    knowledge_point_id: int | None = None


class QuestionResponse(BaseModel):
    questions: list[dict[str, Any]]
    source_summary: dict[str, int]
    warnings: list[str]


# ==============================================================
# 作答与判分
# ==============================================================
class AnswerRequest(BaseModel):
    question_id: int
    user_answer: str
    course_id: int
    knowledge_point: str = ""


class PointJudgementResponse(BaseModel):
    point: str
    hit: bool
    reason: str = ""


class AnswerResponse(BaseModel):
    is_correct: bool | None
    score: float | None
    reference_answer: str = ""
    comment: str = ""
    point_results: list[PointJudgementResponse] = Field(default_factory=list)
    wrong_recorded: bool = False
    error: str | None = None


class ResolveRequest(BaseModel):
    question_id: int
    hits: list[bool]


# ==============================================================
# 错题集
# ==============================================================
class WrongQuestionResponse(BaseModel):
    id: int
    question_bank_id: int | None
    knowledge_point: str | None
    question_type: str | None
    mastery_status: str
    mastery_label: str
    wrong_count: int
    review_count: int
    correct_count: int
    last_result: str | None = None
    error_tags: list[str] = Field(default_factory=list)
    payload: dict[str, Any]


class MasteryUpdateRequest(BaseModel):
    mastered: bool


class ReviewRequest(BaseModel):
    correct: bool | None = None


# ==============================================================
# 后台：课程
# ==============================================================
class CourseCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(default="", max_length=100)
    description: str = Field(default="")
    question_focus: str = Field(default="")


class CourseUpdateRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    question_focus: str | None = None


class CourseMergeRequest(BaseModel):
    from_course_id: int
    to_course_id: int
    merged_by: str = ""


class DashboardResponse(BaseModel):
    course_count: int
    material_count: int
    pending_classification_count: int
    question_count: int
    llm_calls_today: int


# ==============================================================
# 后台：解析任务
# ==============================================================
class ParseTaskResponse(BaseModel):
    id: int
    source_file: str
    status: str
    progress: int
    stage: str | None = None
    page_count: int = 0
    chunk_count: int = 0
    ocr_used: bool = False
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str | None = None


class ParseTaskListResponse(BaseModel):
    tasks: list[ParseTaskResponse]
    total: int


# ==============================================================
# 后台：资料分类
# ==============================================================
class MaterialResponse(BaseModel):
    """资料条目。"""

    id: int
    source_file: str
    course_id: int | None = None
    kind: str
    upload_type: str = "supplement"
    chapter_classified: bool = False
    chunk_count: int = 0
    page_count: int = 0
    ocr_used: bool = False
    detected_course_name: str | None = None
    detected_knowledge_points: list[dict[str, Any]] = Field(default_factory=list)
    detection_confidence: float | None = None
    detection_reasoning: str | None = None
    detection_status: str = "pending"
    uploaded_at: str | None = None
    parsed_at: str | None = None


class MaterialClassifyRequest(BaseModel):
    """触发 LLM 识别的请求。"""

    doc_title: str = Field(default="", description="文档标题（可选）")
    sample_text: str = Field(default="", description="样本文本（可选；不传则从已有 chunk 里取）")


class MaterialConfirmRequest(BaseModel):
    """确认资料归属。"""

    course_id: int = Field(..., description="确认归属的课程 id")
    create_knowledge_points: bool = Field(
        default=True,
        description="是否把识别出的知识点也建到课程下",
    )
    confirmed_by: str = Field(default="", description="确认人")


class MaterialMergeRequest(BaseModel):
    """多份资料合并到同一课程。"""

    material_ids: list[int] = Field(..., min_length=1)
    target_course_id: int
    create_knowledge_points: bool = True
    confirmed_by: str = ""


# ==============================================================
# 后台：题库
# ==============================================================
class QuestionBankItemResponse(BaseModel):
    """题库条目（简化版，前端只用部分字段）。"""

    id: int
    course_id: int
    knowledge_point: str
    question_type: str
    difficulty: str
    source: str
    status: str
    quality_score: float = 0.0
    usage_count: int = 0
    prompt_version: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


# ==============================================================
# 通用
# ==============================================================
class ErrorResponse(BaseModel):
    error: dict[str, Any]


class SuccessResponse(BaseModel):
    success: bool = True
    message: str = ""
    data: dict[str, Any] | None = None



# ==============================================================
# 章节
# ==============================================================
class ChapterCreateRequest(BaseModel):
    course_id: int
    name: str = Field(..., min_length=1, max_length=200)
    parent_id: int | None = None
    summary: str = ""
    sort_order: int = 0


class ChapterUpdateRequest(BaseModel):
    name: str | None = None
    summary: str | None = None
    sort_order: int | None = None


class ChapterResponse(BaseModel):
    id: int
    course_id: int
    parent_id: int | None = None
    name: str
    summary: str | None = None
    sort_order: int = 0
    children: list["ChapterResponse"] = Field(default_factory=list)


class ChapterMatchRequest(BaseModel):
    course_id: int
    input_text: str = Field(..., min_length=1, max_length=500)


class ChapterMatchResponse(BaseModel):
    chapter_id: int | None = None
    chapter_name: str | None = None
    chapter_summary: str | None = None
    reply_text: str = ""


class ChatRequest(BaseModel):
    """用户练习对话请求"""
    course_id: int
    session_id: str = Field(default="default")
    message: str = Field(..., min_length=1, max_length=500)


class ChatResponse(BaseModel):
    """对话响应：含章节匹配 + 出题结果 + 配额"""
    reply: str
    chapter_id: int | None = None
    chapter_name: str | None = None
    chapter_summary: str | None = None
    questions: list[dict[str, Any]] = Field(default_factory=list)
    source_stats: dict[str, int] = Field(default_factory=dict)
    quota: dict[str, int] = Field(default_factory=dict)


class QuotaResponse(BaseModel):
    """出题配额"""
    choice_used: int = 0
    choice_limit: int = 50
    short_answer_used: int = 0
    short_answer_limit: int = 10


class ChunkClassificationResponse(BaseModel):
    chunk_id: str
    chapter_id: int | None = None
    chapter_name: str | None = None
    confidence: float | None = None
    reasoning: str | None = None
    is_confirmed: bool = False
    text: str | None = None


class ChunkChapterUpdateRequest(BaseModel):
    chapter_id: int


# ==============================================================
# 收藏与笔记
# ==============================================================
class NoteRequest(BaseModel):
    content: str = Field(..., min_length=1)


class NoteResponse(BaseModel):
    question_id: int
    content: str


# ==============================================================
# 学习统计
# ==============================================================
class StatsOverviewResponse(BaseModel):
    total_answered: int
    total_correct: int
    accuracy: float
    wrong_count: int
    mastered_count: int
    total_questions: int
    study_days: int


class StatsTrendItem(BaseModel):
    date: str
    count: int
    accuracy: float


class StatsKnowledgePointItem(BaseModel):
    knowledge_point: str
    total: int
    correct: int
    accuracy: float


class MaterialDeletePreviewResponse(BaseModel):
    """删除资料前的预览。"""

    material_id: int
    source_file: str
    chunk_count: int = Field(..., description="会被清理的 chunk 数")
    question_count: int = Field(..., description="来自这份资料的题目数（不会被删）")
    running_tasks: int = Field(..., description="正在执行的解析任务数")
    can_delete: bool = Field(..., description="是否可以删除")
    block_reason: str | None = Field(default=None, description="不能删除时的原因")


# ==============================================================
# 后台：课程删除预览
# ==============================================================
class CourseDeletePreviewResponse(BaseModel):
    """彻底删除课程前的预览。"""

    course_id: int
    name: str
    display_name: str
    is_active: bool
    knowledge_point_count: int = Field(..., description="会被删的知识点数")
    question_count: int = Field(..., description="会被删的题目数")
    wrong_question_count: int = Field(..., description="会被删的错题数")
    paper_count: int = Field(..., description="会被删的试卷数")
    material_count: int = Field(..., description="归属这门课的资料数（不会被删）")
    can_delete: bool = True