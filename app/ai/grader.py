# -*- coding: utf-8 -*-
"""简答题判分：用 LLM 逐要点判定。

【这个模块做什么】

    输入：题目 + 学员作答
    输出：逐要点的判定 + 分数 + 评语

【设计要点】

    1. **空白作答直接判 0 分，不调 LLM** —— 没必要为空白答案付钱
    2. **模型返回的判定会被严格规整** —— 条目数、顺序、hit 取值
    3. **规整不了的条目按"未命中"处理** —— 而不是整批失败
    4. **判分结果可以在界面上被用户推翻** —— 最终以勾选状态为准
       （这一条在 API 层实现，本模块只负责"AI 判分"）
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.prompts import load_rendered, prompt_version
from app.database import connection as db_mysql
from app.ai.llm_client import LLMClient, LLMError, LLMResponseError


# ==============================================================
# 常量
# ==============================================================
GRADE_PROMPT = "m2_all_short_answer_grade_v0.1"


# ==============================================================
# 结果结构
# ==============================================================
@dataclass
class PointJudgement:
    """单个评分要点的判定结果。"""

    point: str          # 评分要点原文
    hit: bool           # 是否命中
    reason: str = ""    # 判定理由


@dataclass
class GradeResult:
    """一次自动判分的完整结果。"""

    point_results: list[PointJudgement] = field(default_factory=list)
    score: float = 0.0          # 0.0~1.0
    comment: str = ""
    model: str = ""
    total_tokens: int = 0
    graded: bool = True         # False 表示"未评分"（如作答为空）

    @property
    def hit_count(self) -> int:
        """命中的要点数。"""
        return sum(1 for p in self.point_results if p.hit)

    @property
    def total_points(self) -> int:
        """要点总数。"""
        return len(self.point_results)

    @property
    def hits(self) -> list[bool]:
        """命中掩码，便于直接喂给界面的勾选框。"""
        return [p.hit for p in self.point_results]


# ==============================================================
# 对外接口
# ==============================================================
def grade_short_answer(
    question: dict,
    user_answer: str,
    llm: LLMClient | None = None,
) -> GradeResult:
    """对一道简答题的作答自动判分。

    Args:
        question: 题目 dict，需含 question / reference_answer / scoring_points。
        user_answer: 学员作答。
        llm: 可注入的 LLM 客户端（测试用）。

    Returns:
        GradeResult。作答为空时返回 graded=False 且 score=0，不调用模型。

    Raises:
        ValueError: 题目缺少评分要点。
        LLMError / LLMResponseError: 调用或解析失败。
    """
    points = [str(p).strip() for p in (question.get("scoring_points") or []) if str(p).strip()]
    if not points:
        raise ValueError("该题没有评分要点，无法自动评分")

    stem = str(question.get("question") or "").strip()
    answer_text = (user_answer or "").strip()

    # 空白作答不必花钱问模型
    if not answer_text:
        return GradeResult(
            point_results=[PointJudgement(point=p, hit=False, reason="未作答") for p in points],
            score=0.0,
            comment="本次未作答，所有要点均未命中。",
            graded=False,
        )

    client = llm if llm is not None else LLMClient()

    # 渲染提示词
    prompt = load_rendered(
        GRADE_PROMPT,
        question=stem,
        reference_answer=str(question.get("reference_answer") or "").strip() or "（未提供）",
        scoring_points="\n".join(f"{i}. {p}" for i, p in enumerate(points, start=1)),
        user_answer=answer_text,
        knowledge_point="、".join(question.get("knowledge_tags") or []) or "（未标注）",
    )

    pv = prompt_version(GRADE_PROMPT)

    # 调 LLM
    try:
        payload, response = client.chat_json([
            {"role": "system", "content": "你是严谨的阅卷教师，只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ])
    except (LLMError, LLMResponseError) as exc:
        # 失败也记审计
        _log_call(
            question=question,
            prompt_version=pv,
            success=False,
            error=str(exc),
        )
        raise

    # 记成功的调用
    _log_call(
        question=question,
        prompt_version=pv,
        success=True,
        usage=response.usage,
    )

    # 规整判定结果
    judgements, score, comment = _normalize(payload, points)

    return GradeResult(
        point_results=judgements,
        score=score,
        comment=comment,
        model=response.usage.model,
        total_tokens=response.usage.total_tokens,
    )


def resolve_result(hits: list[bool], points: list[str]) -> tuple[int, float]:
    """按界面上的最终勾选状态算分。

    【用途】用户在界面上推翻了 AI 判定后，用这个函数重算最终分数。

    Returns:
        ``(命中数, 比例分)``。
    """
    total = len(points)
    hit_count = sum(1 for h in hits if h)
    return hit_count, (round(hit_count / total, 2) if total else 0.0)


# ==============================================================
# 内部工具
# ==============================================================
def _normalize(
    payload: object,
    points: list[str],
) -> tuple[list[PointJudgement], float, str]:
    """把模型返回的判定规整成与本地评分要点一一对应的结构。

    【为什么必须规整】
        模型可能：
          - 少给条目（只判了 2 条，但要点有 3 条）
          - 多给条目（判了 4 条）
          - 改写了要点的措辞
          - 把 hit 写成字符串（"true" / "是"）

        这里以本地要点列表为准，按位置对齐。
        模型没覆盖到的位置一律判为未命中——
        保守处理，界面可手动勾回，不会造成不可挽回的误判。
    """
    raw_items: list = []
    if isinstance(payload, dict):
        raw_items = payload.get("point_results") or payload.get("points") or []
    if not isinstance(raw_items, list):
        raw_items = []

    judgements: list[PointJudgement] = []

    for index, point_text in enumerate(points):
        raw = raw_items[index] if index < len(raw_items) else {}
        if not isinstance(raw, dict):
            raw = {}

        # hit 可能是 bool、字符串、数字
        hit = raw.get("hit")
        if isinstance(hit, str):
            hit = hit.strip().lower() in ("true", "yes", "1", "是", "命中")

        judgements.append(
            PointJudgement(
                # 要点措辞以本地为准（模型改写过的措辞会让界面对不上号）
                point=point_text,
                hit=bool(hit),
                reason=str(raw.get("reason") or "").strip(),
            )
        )

    hit_count = sum(1 for j in judgements if j.hit)
    score = round(hit_count / len(points), 2) if points else 0.0

    comment = ""
    if isinstance(payload, dict):
        comment = str(payload.get("comment") or payload.get("评语") or "").strip()

    return judgements, score, comment


def _log_call(
    question: dict,
    prompt_version: str,
    success: bool,
    usage: object = None,
    error: str = "",
) -> None:
    """写 LLM 调用审计日志。"""
    try:
        db_mysql.execute(
            "INSERT INTO llm_call_log "
            "(purpose, course_id, knowledge_point, question_type, prompt_version, "
            "model_version, prompt_tokens, completion_tokens, latency_ms, success, error) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                "grade_answer",
                question.get("course_id"),
                (question.get("knowledge_tags") or [None])[0],
                question.get("question_type") or "简答",
                prompt_version,
                getattr(usage, "model", "") if usage else "",
                getattr(usage, "prompt_tokens", 0) if usage else 0,
                getattr(usage, "completion_tokens", 0) if usage else 0,
                getattr(usage, "latency_ms", 0) if usage else 0,
                int(success),
                error[:500] if error else None,
            ),
        )
    except Exception:  # noqa: BLE001
        pass