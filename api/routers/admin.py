# -*- coding: utf-8 -*-
"""后台端路由：课程、章节、资料、分类、题库、自检。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from api import deps
from api.schemas import (
    ChapterCreateRequest,
    ChapterResponse,
    ChapterUpdateRequest,
    ChunkChapterUpdateRequest,
    ChunkClassificationResponse,
    CourseCreateRequest,
    CourseMergeRequest,
    CourseResponse,
    CourseUpdateRequest,
    CourseDeletePreviewResponse,
    DashboardResponse,
    KnowledgePointResponse,
    MaterialClassifyRequest,
    MaterialConfirmRequest,
    MaterialMergeRequest,
    MaterialResponse,
    MaterialDeletePreviewResponse,
    ParseTaskListResponse,
    ParseTaskResponse,
    SuccessResponse,
)
from app.config import UPLOAD_DIR
from app.database import chapters as chapter, connection as db_mysql, courses as course, knowledge_points as knowledge_point, materials as material_store, parse_tasks as parse_task, questions as question_bank_mysql
from app.ai import chapter_extractor, chunk_classifier, material_classifier
from app.pipeline import material_merge, parse_worker


router = APIRouter()


# ==============================================================
# 首页数据
# ==============================================================
@router.get("/dashboard", response_model=DashboardResponse, summary="后台首页数据")
async def get_dashboard(
    current: dict = Depends(deps.require_admin),
) -> DashboardResponse:
    course_count_row = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n FROM courses WHERE is_active = 1"
    )
    material_count_row = db_mysql.fetch_one("SELECT COUNT(*) AS n FROM materials")
    pending_row = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n FROM materials WHERE detection_status IN ('pending', 'suggested')"
    )
    question_row = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n FROM question_bank WHERE status = 'active'"
    )
    llm_today_row = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n FROM llm_call_log WHERE DATE(called_at) = CURDATE()"
    )

    return DashboardResponse(
        course_count=int(course_count_row["n"]) if course_count_row else 0,
        material_count=int(material_count_row["n"]) if material_count_row else 0,
        pending_classification_count=int(pending_row["n"]) if pending_row else 0,
        question_count=int(question_row["n"]) if question_row else 0,
        llm_calls_today=int(llm_today_row["n"]) if llm_today_row else 0,
    )


# ==============================================================
# 课程管理
# ==============================================================
@router.get("/courses", response_model=list[CourseResponse], summary="课程列表")
async def list_all_courses(
    current: dict = Depends(deps.require_admin),
) -> list[CourseResponse]:
    courses = course.list_all(include_inactive=True)
    return [
        CourseResponse(
            id=c["id"],
            name=c["name"],
            display_name=c["display_name"],
            description=c.get("description"),
            question_focus=c.get("question_focus"),
            is_active=int(c.get("is_active", 1)),
        )
        for c in courses
    ]


@router.get(
    "/courses/{course_id}/knowledge-points",
    response_model=list[KnowledgePointResponse],
    summary="按课程查知识点",
    description="后台用。列出某课程下的所有知识点。",
)
async def list_course_knowledge_points(
    course_id: int,
    current: dict = Depends(deps.require_admin),
) -> list[KnowledgePointResponse]:
    """列出某课程的知识点。

    【为什么需要这个接口】
        预热向导、题库浏览等页面都需要"选课程后列出知识点"。
        之前只能手动输入知识点名，容易拼错、也不方便。
    """
    c = course.get_by_id(course_id)
    if c is None:
        raise HTTPException(404, detail={"code": "COURSE_NOT_FOUND", "message": f"课程 {course_id} 不存在"})

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


@router.post(
    "/courses",
    response_model=CourseResponse,
    summary="建课程",
    status_code=status.HTTP_201_CREATED,
)
async def create_course(
    payload: CourseCreateRequest,
    current: dict = Depends(deps.require_admin),
) -> CourseResponse:
    try:
        course_id = course.create(
            name=payload.name,
            display_name=payload.display_name or payload.name,
            description=payload.description,
            question_focus=payload.question_focus,
        )
    except course.CourseNameExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "COURSE_NAME_EXISTS", "message": str(exc)},
        ) from exc
    except course.CourseError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_INPUT", "message": str(exc)},
        ) from exc

    # 查回刚建的课程，用于返回完整信息（含 is_active）
    c = course.get_by_id(course_id)
    if c is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "COURSE_LOOKUP_FAILED", "message": "课程创建后无法查回"},
        )

    return CourseResponse(
        id=c["id"],
        name=c["name"],
        display_name=c["display_name"],
        description=c.get("description"),
        question_focus=c.get("question_focus"),
        is_active=1 if c.get("is_active") is None else int(c["is_active"]),
    )

@router.patch("/courses/{course_id}", response_model=SuccessResponse, summary="改课程")
async def update_course(
    course_id: int,
    payload: CourseUpdateRequest,
    current: dict = Depends(deps.require_admin),
) -> SuccessResponse:
    try:
        course.update(
            course_id=course_id,
            display_name=payload.display_name,
            description=payload.description,
            question_focus=payload.question_focus,
        )
    except course.CourseNotFoundError as exc:
        raise HTTPException(404, detail={"code": "COURSE_NOT_FOUND", "message": str(exc)}) from exc
    return SuccessResponse(message="已更新")


@router.delete("/courses/{course_id}", response_model=SuccessResponse, summary="停用课程")
async def delete_course(
    course_id: int,
    current: dict = Depends(deps.require_admin),
) -> SuccessResponse:
    try:
        course.soft_delete(course_id)
    except course.CourseNotFoundError as exc:
        raise HTTPException(404, detail={"code": "COURSE_NOT_FOUND", "message": str(exc)}) from exc
    return SuccessResponse(message="课程已停用")
@router.post("/courses/{course_id}/restore", response_model=SuccessResponse, summary="启用课程")
async def restore_course(
    course_id: int,
    current: dict = Depends(deps.require_admin),
) -> SuccessResponse:
    """把停用的课程重新启用。"""
    try:
        course.restore(course_id)
    except course.CourseNotFoundError as exc:
        raise HTTPException(404, detail={"code": "COURSE_NOT_FOUND", "message": str(exc)}) from exc
    return SuccessResponse(message="课程已启用")


@router.get(
    "/courses/{course_id}/delete-preview",
    response_model=CourseDeletePreviewResponse,
    summary="彻底删除前的预览",
)
async def preview_hard_delete_course(
    course_id: int,
    current: dict = Depends(deps.require_admin),
) -> CourseDeletePreviewResponse:
    """删除前的预览：告诉用户会删什么。"""
    preview = course.get_delete_preview(course_id)
    return CourseDeletePreviewResponse(**preview)


@router.delete(
    "/courses/{course_id}/hard",
    response_model=SuccessResponse,
    summary="彻底删除课程（危险）",
    description="不可恢复。会连带删除所有题目、错题、试卷。",
)
async def hard_delete_course(
    course_id: int,
    current: dict = Depends(deps.require_admin),
) -> SuccessResponse:
    """物理删除课程。"""
    result = course.hard_delete(course_id)

    if not result["ok"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "DELETE_FAILED", "message": result["error"] or "删除失败"},
        )

    d = result["deleted"]
    message = (
        f"已彻底删除课程「{d['display_name']}」"
        f"（知识点 {d['knowledge_point_count']}、"
        f"题目 {d['question_count']}、"
        f"错题 {d['wrong_question_count']}、"
        f"试卷 {d['paper_count']}）"
    )

    return SuccessResponse(message=message, data=d)

@router.post("/courses/merge", response_model=SuccessResponse, summary="合并课程")
async def merge_courses(
    payload: CourseMergeRequest,
    current: dict = Depends(deps.require_admin),
) -> SuccessResponse:
    try:
        report = course.merge(
            from_course_id=payload.from_course_id,
            to_course_id=payload.to_course_id,
            merged_by=payload.merged_by or current["username"],
        )
    except course.CourseNotFoundError as exc:
        raise HTTPException(404, detail={"code": "COURSE_NOT_FOUND", "message": str(exc)}) from exc
    except course.CourseError as exc:
        raise HTTPException(400, detail={"code": "INVALID_MERGE", "message": str(exc)}) from exc
    return SuccessResponse(
        message=f"合并完成：迁移 {report['moved_questions']} 道题，去重 {report['deduped_questions']} 道",
        data=report,
    )


# ==============================================================
# 章节管理
# ==============================================================
@router.get(
    "/courses/{course_id}/chapters",
    response_model=list[ChapterResponse],
    summary="章节树",
)
async def list_course_chapters(
    course_id: int,
    current: dict = Depends(deps.require_admin),
) -> list[ChapterResponse]:
    """获取课程的章节树。"""
    c = course.get_by_id(course_id)
    if c is None:
        raise HTTPException(404, detail={"code": "COURSE_NOT_FOUND", "message": f"课程 {course_id} 不存在"})

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
    "/chapters",
    response_model=ChapterResponse,
    summary="建章节",
    status_code=status.HTTP_201_CREATED,
)
async def create_chapter(
    payload: ChapterCreateRequest,
    current: dict = Depends(deps.require_admin),
) -> ChapterResponse:
    """创建一个章节（需先有课程）。"""

    try:
        cid = chapter.create_chapter(
            course_id=payload.course_id,
            name=payload.name,
            parent_id=payload.parent_id,
            summary=payload.summary,
            sort_order=payload.sort_order,
        )
    except chapter.ChapterError as exc:
        raise HTTPException(400, detail={"code": "CHAPTER_ERROR", "message": str(exc)}) from exc

    ch = chapter.get_chapter_by_id(cid)
    if ch is None:
        raise HTTPException(500, detail={"code": "LOOKUP_FAILED", "message": "章节创建后无法查回"})

    return ChapterResponse(
        id=ch["id"],
        course_id=ch["course_id"],
        parent_id=ch.get("parent_id"),
        name=ch["name"],
        summary=ch.get("summary"),
        sort_order=ch.get("sort_order", 0),
    )


@router.patch(
    "/chapters/{chapter_id}",
    response_model=SuccessResponse,
    summary="改章节",
)
async def update_chapter(
    chapter_id: int,
    payload: ChapterUpdateRequest,
    current: dict = Depends(deps.require_admin),
) -> SuccessResponse:
    """修改章节名或摘要。"""
    try:
        chapter.update_chapter(
            chapter_id=chapter_id,
            name=payload.name,
            summary=payload.summary,
            sort_order=payload.sort_order,
        )
    except chapter.ChapterError as exc:
        raise HTTPException(400, detail={"code": "CHAPTER_ERROR", "message": str(exc)}) from exc
    return SuccessResponse(message="已更新")


@router.delete(
    "/chapters/{chapter_id}",
    response_model=SuccessResponse,
    summary="删章节",
)
async def delete_chapter(
    chapter_id: int,
    current: dict = Depends(deps.require_admin),
) -> SuccessResponse:
    """删除章节。"""
    ok = chapter.delete_chapter(chapter_id)
    if not ok:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": f"章节 {chapter_id} 不存在"})
    return SuccessResponse(message="已删除")


@router.get(
    "/chapters/{chapter_id}/questions",
    summary="章节题量",
)
async def get_chapter_question_count(
    chapter_id: int,
    current: dict = Depends(deps.require_admin),
) -> dict:
    """查询某章节有多少道题目。"""
    count = chapter.count_questions_by_chapter(chapter_id)
    return {"chapter_id": chapter_id, "question_count": count}


@router.delete(
    "/chapters/{chapter_id}/questions",
    response_model=SuccessResponse,
    summary="清空章节题库",
)
async def clear_chapter_questions(
    chapter_id: int,
    current: dict = Depends(deps.require_admin),
) -> SuccessResponse:
    """清空某章节的所有题目。"""
    deleted = chapter.clear_questions_by_chapter(chapter_id)
    return SuccessResponse(message=f"已删除 {deleted} 道题", data={"deleted": deleted})



# ==============================================================
# 资料上传与解析任务
# ==============================================================
_ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".txt", ".md",
    ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp",
}
_MAX_FILE_SIZE = 50 * 1024 * 1024


async def _save_upload_file(file: UploadFile) -> Path:
    """保存上传文件到磁盘，返回目标路径。"""
    if not file.filename:
        raise HTTPException(400, detail={"code": "INVALID_FILENAME", "message": "文件名为空"})

    filename = Path(file.filename).name
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, detail={"code": "UNSUPPORTED_FORMAT", "message": f"不支持 {ext}"})

    target_path = UPLOAD_DIR / filename
    try:
        size = 0
        with target_path.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > _MAX_FILE_SIZE:
                    f.close()
                    target_path.unlink(missing_ok=True)
                    raise HTTPException(413, detail={"code": "FILE_TOO_LARGE", "message": "超过 50MB"})
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, detail={"code": "SAVE_FAILED", "message": str(exc)}) from exc

    return target_path


async def _create_upload_task(
    filename: str,
    target_path: Path,
    upload_type: str,
    course_key: str | None,
) -> ParseTaskResponse:
    """创建解析任务并提交到后台。"""
    try:
        task_id = parse_task.create_task(
            source_file=filename,
            file_path=str(target_path),
            course_key=course_key,
            upload_type=upload_type,
        )
        parse_worker.submit_task(task_id)
    except Exception as exc:
        raise HTTPException(500, detail={"code": "TASK_CREATE_FAILED", "message": str(exc)}) from exc

    return _to_parse_task_response(parse_task.get_task(task_id))


@router.post("/textbooks/upload", response_model=ParseTaskResponse, summary="上传教材")
async def upload_textbook(
    file: UploadFile = File(...),
    course_key: str | None = Query(default=None),
    current: dict = Depends(deps.require_admin),
) -> ParseTaskResponse:
    """上传一份教材（textbook）。

    【教材 vs 附属资料的区别】
        教材是课程的主干资料，有完整的章节结构。
        每门课只能有一本教材（由数据库 UNIQUE 约束保证）。
        附属资料是对教材的补充（讲义、参考资料、习题集等），
        与教材共享同一个上传与解析管道，但数据库标记不同。
    """
    target_path = await _save_upload_file(file)
    return await _create_upload_task(
        filename=Path(file.filename).name,
        target_path=target_path,
        upload_type="textbook",
        course_key=course_key,
    )


@router.post("/supplements/upload", response_model=ParseTaskResponse, summary="上传附属资料")
async def upload_supplement(
    file: UploadFile = File(...),
    course_key: str | None = Query(default=None),
    current: dict = Depends(deps.require_admin),
) -> ParseTaskResponse:
    """上传一份附属资料（supplement）。

    【附属资料是什么】
        除了教材之外的一切补充资料：
          - 讲课讲义、PPT 转的 PDF
          - 参考书目、法条原文
          - 习题集、案例分析
          - 任何有助于学习的资料

    与教材不同，附属资料可以有任意多份，没有"每门课一份"的限制。
    附属资料上传后也需要 LLM 识别归属，流程和教材一致。
    """
    target_path = await _save_upload_file(file)
    return await _create_upload_task(
        filename=Path(file.filename).name,
        target_path=target_path,
        upload_type="supplement",
        course_key=course_key,
    )


@router.post("/materials/upload", response_model=ParseTaskResponse, summary="上传资料（兼容旧路径）",
             deprecated=True)
async def upload_material_legacy(
    file: UploadFile = File(...),
    course_key: str | None = Query(default=None),
    upload_type: str = Query(default="supplement", description="textbook / supplement"),
    current: dict = Depends(deps.require_admin),
) -> ParseTaskResponse:
    """上传资料（兼容旧路径，建议使用 /textbooks/upload 或 /supplements/upload）。"""
    if upload_type not in ("textbook", "supplement"):
        upload_type = "supplement"
    target_path = await _save_upload_file(file)
    return await _create_upload_task(
        filename=Path(file.filename).name,
        target_path=target_path,
        upload_type=upload_type,
        course_key=course_key,
    )


@router.get("/materials/tasks", response_model=ParseTaskListResponse, summary="任务列表")
async def list_parse_tasks(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = 50,
    current: dict = Depends(deps.require_admin),
) -> ParseTaskListResponse:
    rows = parse_task.list_tasks(status=status_filter, limit=limit)
    return ParseTaskListResponse(
        tasks=[_to_parse_task_response(r) for r in rows],
        total=len(rows),
    )


@router.get("/materials/tasks/{task_id}", response_model=ParseTaskResponse, summary="单任务")
async def get_parse_task(
    task_id: int,
    current: dict = Depends(deps.require_admin),
) -> ParseTaskResponse:
    task = parse_task.get_task(task_id)
    if task is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": f"任务 {task_id} 不存在"})
    return _to_parse_task_response(task)


@router.post("/materials/tasks/{task_id}/retry", response_model=ParseTaskResponse, summary="重试任务")
async def retry_parse_task(
    task_id: int,
    current: dict = Depends(deps.require_admin),
) -> ParseTaskResponse:
    task = parse_task.get_task(task_id)
    if task is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": str(task_id)})

    if task["status"] != parse_task.STATUS_FAILED:
        raise HTTPException(400, detail={"code": "INVALID_STATUS", "message": "只有 failed 能重试"})

    file_path = Path(task["file_path"])
    if not file_path.is_file():
        raise HTTPException(400, detail={"code": "FILE_MISSING", "message": "文件不存在"})

    db_mysql.execute(
        "UPDATE parse_tasks SET status='pending', progress=0, stage=NULL, "
        "error=NULL, started_at=NULL, finished_at=NULL WHERE id=%s",
        (task_id,),
    )
    parse_worker.submit_task(task_id)
    return _to_parse_task_response(parse_task.get_task(task_id))


def _to_parse_task_response(task: dict) -> ParseTaskResponse:
    return ParseTaskResponse(
        id=task["id"],
        source_file=task["source_file"],
        status=task["status"],
        progress=task["progress"],
        stage=task.get("stage"),
        page_count=task.get("page_count") or 0,
        chunk_count=task.get("chunk_count") or 0,
        ocr_used=bool(task.get("ocr_used")),
        warnings=task.get("warnings") or [],
        error=task.get("error"),
        started_at=str(task["started_at"]) if task.get("started_at") else None,
        finished_at=str(task["finished_at"]) if task.get("finished_at") else None,
        created_at=str(task["created_at"]) if task.get("created_at") else None,
    )


# ==============================================================
# 资料分类
# ==============================================================
@router.get("/materials", response_model=list[MaterialResponse], summary="资料列表")
async def list_materials(
    course_id: int | None = None,
    detection_status: str | None = None,
    upload_type: str | None = None,
    current: dict = Depends(deps.require_admin),
) -> list[MaterialResponse]:
    rows = material_store.list_all(
        course_id=course_id, detection_status=detection_status,
        upload_type=upload_type, limit=200,
    )
    return [_to_material_response(r) for r in rows]


@router.get("/materials/pending", response_model=list[MaterialResponse], summary="待分类资料")
async def list_pending_materials(
    current: dict = Depends(deps.require_admin),
) -> list[MaterialResponse]:
    rows = material_store.list_pending_classification()
    return [_to_material_response(r) for r in rows]


@router.post(
    "/materials/{material_id}/classify",
    response_model=MaterialResponse,
    summary="触发 LLM 识别",
)
async def classify_material(
    material_id: int,
    payload: MaterialClassifyRequest,
    current: dict = Depends(deps.require_admin),
) -> MaterialResponse:
    material = material_store.get_by_id(material_id)
    if material is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": f"资料 {material_id} 不存在"})

    sample_text = payload.sample_text.strip()
    if not sample_text:
        from app.pipeline import indexer
        try:
            chunks = indexer.get_chunks_by_source(material["source_file"])
            chunks.sort(key=lambda c: str(c.get("id", "")))
            sample_text = "\n\n".join(str(c.get("text", "")) for c in chunks[:3])
        except Exception as exc:
            raise HTTPException(500, detail={"code": "CHUNK_READ_FAILED", "message": str(exc)}) from exc

    if not sample_text.strip():
        raise HTTPException(400, detail={"code": "NO_SAMPLE", "message": "资料无可用文本"})

    result = material_classifier.classify_material(
        material_id=material_id,
        sample_text=sample_text,
        doc_title=payload.doc_title,
    )

    if not result.get("success"):
        raise HTTPException(500, detail={"code": "CLASSIFY_FAILED", "message": result.get("error") or "识别失败"})

    return _to_material_response(material_store.get_by_id(material_id))


@router.post("/materials/{material_id}/confirm", response_model=SuccessResponse, summary="确认归属")
async def confirm_material(
    material_id: int,
    payload: MaterialConfirmRequest,
    current: dict = Depends(deps.require_admin),
) -> SuccessResponse:
    material = material_store.get_by_id(material_id)
    if material is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": str(material_id)})

    try:
        material_store.confirm_classification(
            material_id=material_id,
            course_id=payload.course_id,
            confirmed_by=payload.confirmed_by or current["username"],
        )
    except ValueError as exc:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": str(exc)}) from exc

    created_kp = 0
    if payload.create_knowledge_points:
        kp_list = material.get("detected_knowledge_points") or []
        names = [str(item.get("name", "")).strip() for item in kp_list if item.get("name")]
        if names:
            try:
                ids = knowledge_point.bulk_create(
                    payload.course_id, names, source_material_id=material_id,
                )
                created_kp = len(ids)
            except Exception as exc:
                print(f"[警告] 建知识点失败：{exc}")

    # 教材确认归属后，自动触发章节抽取（后台线程）
    if material.get("upload_type") == "textbook" and material.get("source_file"):
        _auto_extract_chapters_bg(material_id, payload.course_id, material["source_file"])

    if material.get("upload_type") == "textbook":
        msg = "已绑定教材"
    elif created_kp > 0:
        msg = f"资料已归到课程，建了 {created_kp} 个知识点"
    else:
        msg = "资料已归到课程"

    return SuccessResponse(
        message=msg,
        data={"created_knowledge_points": created_kp},
    )


@router.post("/materials/merge", response_model=SuccessResponse, summary="合并资料")
async def merge_materials(
    payload: MaterialMergeRequest,
    current: dict = Depends(deps.require_admin),
) -> SuccessResponse:
    result = material_merge.merge_materials_to_course(
        material_ids=payload.material_ids,
        target_course_id=payload.target_course_id,
        confirmed_by=payload.confirmed_by or current["username"],
        create_missing_knowledge_points=payload.create_knowledge_points,
    )
    if not result["success"]:
        return SuccessResponse(
            success=False,
            message=f"部分失败：成功 {result['merged_count']} 份",
            data={"failed": result["failed"]},
        )
    return SuccessResponse(message=f"合并完成：{result['merged_count']} 份资料", data=result)
@router.get(
    "/materials/{material_id}/delete-preview",
    response_model=MaterialDeletePreviewResponse,
    summary="删除资料前的预览",
    description="告诉用户会删什么、不会删什么、能不能删。",
)
async def preview_delete_material(
    material_id: int,
    current: dict = Depends(deps.require_admin),
) -> MaterialDeletePreviewResponse:
    """删除前的预览。"""
    preview = material_store.get_delete_preview(material_id)
    return MaterialDeletePreviewResponse(**preview)


@router.delete(
    "/materials/{material_id}",
    response_model=SuccessResponse,
    summary="删除资料",
    description=(
        "从磁盘、向量库、数据库中彻底删除这份资料。"
        "从它出的题目不会删除（可以在题库浏览里手动废弃）。"
    ),
)
async def delete_material(
    material_id: int,
    current: dict = Depends(deps.require_admin),
) -> SuccessResponse:
    """删除一份资料。"""
    result = material_store.delete_material(material_id, delete_file=True)

    if not result["ok"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "DELETE_FAILED", "message": result["error"] or "删除失败"},
        )

    message = (
        f"已删除：{result['source_file']}（"
        f"文件 {'已删' if result['deleted_file'] else '未删'}，"
        f"chunk {result['deleted_chunks']} 个，"
        f"任务 {result['deleted_tasks']} 条）"
    )

    return SuccessResponse(
        message=message,
        data={
            "source_file": result["source_file"],
            "deleted_chunks": result["deleted_chunks"],
            "deleted_file": result["deleted_file"],
            "deleted_tasks": result["deleted_tasks"],
            "warnings": result["warnings"],
        },
    )

def _to_material_response(row: dict) -> MaterialResponse:
    return MaterialResponse(
        id=row["id"],
        source_file=row["source_file"],
        course_id=row.get("course_id"),
        kind=row.get("kind") or "",
        upload_type=row.get("upload_type") or "supplement",
        chapter_classified=bool(row.get("chapter_classified")),
        chunk_count=row.get("chunk_count") or 0,
        page_count=row.get("page_count") or 0,
        ocr_used=bool(row.get("ocr_used")),
        detected_course_name=row.get("detected_course_name"),
        detected_knowledge_points=row.get("detected_knowledge_points") or [],
        detection_confidence=float(row["detection_confidence"]) if row.get("detection_confidence") is not None else None,
        detection_reasoning=row.get("detection_reasoning"),
        detection_status=row.get("detection_status") or "pending",
        uploaded_at=str(row["uploaded_at"]) if row.get("uploaded_at") else None,
        parsed_at=str(row["parsed_at"]) if row.get("parsed_at") else None,
    )


# ---------- 中文序数辅助 ----------
_CHINESE_DIGITS = "零一二三四五六七八九十"


def _to_chinese_ordinal(n: int) -> str:
    """整数转中文序数。1→一 2→二 10→十 11→十一 20→二十"""
    if n <= 0:
        return str(n)
    if n <= 10:
        return _CHINESE_DIGITS[n]
    if n < 20:
        return "十" + _CHINESE_DIGITS[n - 10]
    tens = n // 10
    ones = n % 10
    if ones == 0:
        return _CHINESE_DIGITS[tens] + "十"
    return _CHINESE_DIGITS[tens] + "十" + _CHINESE_DIGITS[ones]


# ==============================================================
# 章节抽取与 Chunk 分类
# ==============================================================
@router.post(
    "/materials/{material_id}/extract-chapters",
    response_model=list[ChapterResponse],
    summary="从资料抽取章节",
)
async def extract_chapters(
    material_id: int,
    current: dict = Depends(deps.require_admin),
) -> list[ChapterResponse]:
    """从解析后的资料中抽取章节结构。"""
    from app.ai.llm_client import LLMClient, LLMError
    from app.config import (
        LLM_API_KEY,
        LLM_BASE_URL,
        LLM_MODEL,
        LLM_TEMPERATURE,
        LLM_TIMEOUT,
    )

    material = material_store.get_by_id(material_id)
    if material is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": f"资料 {material_id} 不存在"})

    if not material.get("course_id"):
        raise HTTPException(400, detail={"code": "NO_COURSE", "message": "资料尚未归到任何课程，请先确认归属"})

    course_id = material["course_id"]

    from app.pipeline import indexer
    chunks = indexer.get_chunks_by_source(material["source_file"])
    chunks.sort(key=lambda c: str(c.get("id", "")))
    full_text = "\n\n".join(str(c.get("text", "")) for c in chunks)

    if not full_text.strip():
        raise HTTPException(400, detail={"code": "NO_TEXT", "message": "资料无可用文本"})

    llm = LLMClient(
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY,
        model=LLM_MODEL,
        timeout=LLM_TIMEOUT,
        temperature=LLM_TEMPERATURE,
    )

    try:
        extracted = chapter_extractor.extract_chapters_from_textbook(full_text, course_id, llm)
    except LLMError as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, detail={"code": "LLM_ERROR", "message": str(exc)}) from exc
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, detail={"code": "EXTRACT_FAILED", "message": str(exc)}) from exc

    # 使用 bulk_create_chapters 支持递归子章节（章→节→小节）
    # 去重：同名字段跳过
    chapter.bulk_create_chapters(course_id, extracted)

    # 返回完整的章节树（含子章节）
    tree = chapter.get_chapter_tree(course_id)
    return [
        ChapterResponse(
            id=ch["id"],
            course_id=ch["course_id"],
            parent_id=ch.get("parent_id"),
            name=ch["name"],
            summary=ch.get("summary"),
            sort_order=ch.get("sort_order", 0),
            children=[ChapterResponse(
                id=c["id"],
                course_id=c["course_id"],
                parent_id=c.get("parent_id"),
                name=c["name"],
                summary=c.get("summary"),
                sort_order=c.get("sort_order", 0),
                children=_to_chapter_tree(c.get("children", [])),
            ) for c in ch.get("children", [])],
        )
        for ch in tree
    ]


@router.post(
    "/materials/{material_id}/classify-to-chapters",
    response_model=list[ChunkClassificationResponse],
    summary="Chunk 分类到章节",
)
async def classify_chunks_to_chapters(
    material_id: int,
    current: dict = Depends(deps.require_admin),
) -> list[ChunkClassificationResponse]:
    """将资料的所有 chunk 分类到对应章节。"""
    from app.ai.llm_client import LLMClient, LLMError
    from app.config import (
        LLM_API_KEY,
        LLM_BASE_URL,
        LLM_MODEL,
        LLM_TEMPERATURE,
        LLM_TIMEOUT,
    )

    material = material_store.get_by_id(material_id)
    if material is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": f"资料 {material_id} 不存在"})

    if not material.get("course_id"):
        raise HTTPException(400, detail={"code": "NO_COURSE", "message": "资料尚未归到任何课程"})

    course_id = material["course_id"]

    from app.pipeline import indexer
    chunks = indexer.get_chunks_by_source(material["source_file"])

    llm = LLMClient(
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY,
        model=LLM_MODEL,
        timeout=LLM_TIMEOUT,
        temperature=LLM_TEMPERATURE,
    )

    try:
        results = chunk_classifier.classify_chunks_to_chapters(
            material_id=material_id,
            course_id=course_id,
            chunks=chunks,
            llm=llm,
        )
    except LLMError as exc:
        raise HTTPException(500, detail={"code": "LLM_ERROR", "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(500, detail={"code": "CLASSIFY_FAILED", "message": str(exc)}) from exc

    chunk_classifier.save_classification_results(material_id, results)

    # 构建章节映射，格式：第X章 章节名
    chapters = chapter.list_chapters(course_id)
    chapter_map: dict[int, str] = {}
    for ch in chapters:
        sort_order = int(ch.get("sort_order", 0))
        chapter_num = _to_chinese_ordinal(sort_order + 1)
        chapter_map[int(ch["id"])] = f"第{chapter_num}章 {ch['name']}"

    # 构建 chunk_id → text 映射，前端展示用
    chunk_text_map: dict[str, str] = {
        str(c.get("id", "")): str(c.get("text", "")) for c in chunks
    }

    return [
        ChunkClassificationResponse(
            chunk_id=r["chunk_id"],
            chapter_id=r["chapter_id"],
            chapter_name=chapter_map.get(r["chapter_id"]),
            confidence=r["confidence"],
            reasoning=r.get("reasoning", ""),
            is_confirmed=True,
            text=chunk_text_map.get(r["chunk_id"], ""),
        )
        for r in results
    ]


@router.get(
    "/materials/{material_id}/chunk-classification",
    response_model=list[ChunkClassificationResponse],
    summary="查看 Chunk 分类结果",
)
async def get_chunk_classification(
    material_id: int,
    current: dict = Depends(deps.require_admin),
) -> list[ChunkClassificationResponse]:
    """查看某资料的 chunk 分类结果。"""
    material = material_store.get_by_id(material_id)
    if material is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": f"资料 {material_id} 不存在"})

    records = chunk_classifier.get_classification_by_material(material_id)

    chapter_map: dict[int, str] = {}
    if material.get("course_id"):
        chapters = chapter.list_chapters(material["course_id"])
        for ch in chapters:
            sort_order = int(ch.get("sort_order", 0))
            chapter_num = _to_chinese_ordinal(sort_order + 1)
            chapter_map[int(ch["id"])] = f"第{chapter_num}章 {ch['name']}"

    # 从索引器获取 chunk 文本
    from app.pipeline import indexer
    try:
        chunks = indexer.get_chunks_by_source(material["source_file"])
        chunk_text_map: dict[str, str] = {
            str(c.get("id", "")): str(c.get("text", "")) for c in chunks
        }
    except Exception:
        chunk_text_map = {}

    return [
        ChunkClassificationResponse(
            chunk_id=r["chunk_id"],
            chapter_id=r.get("chapter_id"),
            chapter_name=chapter_map.get(r.get("chapter_id")) if r.get("chapter_id") else None,
            confidence=r.get("confidence"),
            reasoning=r.get("reasoning", ""),
            is_confirmed=bool(r.get("is_confirmed")),
            text=chunk_text_map.get(r["chunk_id"], ""),
        )
        for r in records
    ]


@router.patch(
    "/chunks/{chunk_id}/chapter",
    response_model=SuccessResponse,
    summary="手动修改 Chunk 归属",
)
async def update_chunk_chapter(
    chunk_id: str,
    payload: ChunkChapterUpdateRequest,
    current: dict = Depends(deps.require_admin),
) -> SuccessResponse:
    """手动修改一个 chunk 归属的章节。"""
    ok = chunk_classifier.update_chunk_chapter(chunk_id, payload.chapter_id)
    if not ok:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": f"chunk {chunk_id} 不存在"})
    return SuccessResponse(message="已更新")


# ==============================================================
# 题库管理
# ==============================================================
@router.get("/question-bank", summary="题库浏览")
async def list_questions(
    course_id: int,
    knowledge_point: str | None = None,
    question_type: str | None = None,
    difficulty: str | None = None,
    status_filter: str = Query(default="active", alias="status"),
    limit: int = 50,
    current: dict = Depends(deps.require_admin),
) -> list[dict]:
    return question_bank_mysql.query_questions(
        course_id=course_id,
        knowledge_point=knowledge_point,
        question_type=question_type,
        difficulty=difficulty,
        status=status_filter,
        limit=limit,
    )


@router.get("/question-bank/stats", summary="题库统计")
async def question_bank_stats(
    course_id: int,
    current: dict = Depends(deps.require_admin),
) -> dict:
    """题库统计（用于看板）。"""
    return question_bank_mysql.bank_stats(course_id)


@router.delete("/question-bank/{question_id}", response_model=SuccessResponse, summary="废弃题目")
async def deprecate_question(
    question_id: int,
    current: dict = Depends(deps.require_admin),
) -> SuccessResponse:
    ok = question_bank_mysql.deprecate_question(question_id, reason="admin")
    if not ok:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": f"题目 {question_id} 不存在"})
    return SuccessResponse(message="已废弃")


@router.post("/question-bank/{question_id}/restore", response_model=SuccessResponse, summary="恢复题目")
async def restore_question(
    question_id: int,
    current: dict = Depends(deps.require_admin),
) -> SuccessResponse:
    ok = question_bank_mysql.restore_question(question_id)
    if not ok:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": str(question_id)})
    return SuccessResponse(message="已恢复")


# ==============================================================
# 系统自检
# ==============================================================
@router.get("/selftest", summary="系统自检")
async def selftest(
    current: dict = Depends(deps.require_admin),
) -> dict:
    from app.database import redis as db_redis

    mysql_status = db_mysql.health_check()
    redis_status = db_redis.health_check()

    bank_rows = db_mysql.fetch_all(
        "SELECT course_id, COUNT(*) AS n FROM question_bank "
        "WHERE status = 'active' GROUP BY course_id"
    )

    llm_row = db_mysql.fetch_one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(prompt_tokens + completion_tokens), 0) AS tokens "
        "FROM llm_call_log WHERE called_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
    )

    return {
        "mysql": mysql_status,
        "redis": redis_status,
        "question_bank": {
            "by_course": {str(r["course_id"]): int(r["n"]) for r in bank_rows},
        },
        "llm_last_7_days": {
            "calls": int(llm_row["n"]) if llm_row else 0,
            "total_tokens": int(llm_row["tokens"]) if llm_row else 0,
        },
    }


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


def _auto_extract_chapters_bg(
    material_id: int,
    course_id: int,
    source_file: str,
) -> None:
    """后台线程：从已解析的教材中自动抽取章节结构。"""
    import traceback

    def _run() -> None:
        try:
            from app.pipeline import indexer
            from app.database.chapters import bulk_create_chapters
            from app.ai.chapter_extractor import extract_chapters_from_textbook
            from app.ai.llm_client import LLMClient
            from app.config import (
                LLM_API_KEY,
                LLM_BASE_URL,
                LLM_MODEL,
                LLM_TEMPERATURE,
                LLM_TIMEOUT,
            )

            # 获取教材全文
            chunks = indexer.get_chunks_by_source(source_file)
            if not chunks:
                print(f"[章节自动抽取] 资料 {material_id} 无 chunk，跳过")
                return
            chunks.sort(key=lambda c: str(c.get("id", "")))
            full_text = "\n\n".join(str(c.get("text", "")) for c in chunks)
            if not full_text.strip():
                print(f"[章节自动抽取] 资料 {material_id} 无文本，跳过")
                return

            # LLM 抽取
            llm = LLMClient(
                base_url=LLM_BASE_URL,
                api_key=LLM_API_KEY,
                model=LLM_MODEL,
                timeout=LLM_TIMEOUT,
                temperature=LLM_TEMPERATURE,
            )
            extracted = extract_chapters_from_textbook(full_text, course_id, llm)

            # 写入数据库
            ids = bulk_create_chapters(course_id, extracted)
            print(f"[章节自动抽取] 资料 {material_id} 创建了 {len(ids)} 个章节")

        except Exception as exc:
            print(f"[章节自动抽取失败] 资料 {material_id}: {type(exc).__name__}: {exc}")
            traceback.print_exc()

    import threading
    t = threading.Thread(target=_run, name=f"auto-chapter-{material_id}", daemon=True)
    t.start()