# -*- coding: utf-8 -*-
"""解析任务执行器：在后台线程里跑 M0 解析。

【为什么用后台线程】

    上传一份 PDF，解析可能要几十秒（抽取、OCR、向量化）。
    如果同步等，用户界面会卡住，且 HTTP 请求容易超时。

    后台线程的做法：
      1. HTTP 请求立即返回 task_id
      2. 线程池里跑实际解析
      3. 前端轮询进度

【为什么不用 Celery / RQ】

    项目规模小，引入消息队列需要：
      - 装 Redis broker
      - 起独立的 worker 进程
      - 配任务序列化、结果后端
    成本远大于收益。

    单进程内的线程池对这个规模的项目够用。
    缺点：服务重启会丢失正在跑的任务——但 parse_task.cleanup_zombie_tasks
    已经处理了这个问题（重启时标记为 failed，用户可重试）。

【线程池设计】

    ThreadPoolExecutor 默认线程数 = CPU 核数。
    但我们的任务主要是 IO（读文件、调 embedder、写 FAISS），
    所以设成 2~4 个并发就够了。太多反而会争抢内存（embedder 模型很大）。
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

from app.pipeline import indexer
from app.database import parse_tasks as parse_task
from app.pipeline import orchestrator as pipeline


# ==============================================================
# 线程池（进程级单例）
# ==============================================================
# max_workers=2：同时最多 2 个解析任务。
# 为什么不设更多：
#   - embedder 加载的模型占内存（几百 MB）
#   - 同时跑太多任务会 OOM（尤其是 OCR）
#   - 用户通常一次只上传一两份资料
_EXECUTOR: concurrent.futures.ThreadPoolExecutor | None = None


def _get_executor() -> concurrent.futures.ThreadPoolExecutor:
    """获取（惰性创建）线程池。"""
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = concurrent.futures.ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="parse_worker",
        )
    return _EXECUTOR


# ==============================================================
# 提交任务
# ==============================================================
def submit_task(task_id: int) -> None:
    """提交一个任务到线程池。

    【注意】本函数**立即返回**，不等待执行完成。
        实际执行在后台线程里。

    Args:
        task_id: parse_tasks 里的任务 id。
    """
    executor = _get_executor()
    executor.submit(_run_task, task_id)


# ==============================================================
# 内部：实际执行
# ==============================================================
def _run_task(task_id: int) -> None:
    """实际执行解析任务。

    【执行流程】
        1. 标记 running
        2. 调 pipeline.ingest_document 跑 M0
        3. 注册资料到 materials 表
        4. 标记 done
        5. 任何异常都标记 failed

    【为什么整个函数体包在 try/except 里】
        后台线程的异常不会传播到主线程。
        如果这里不捕获，任务会永远停在 running，用户看不到任何错误。
    """
    try:
        task = parse_task.get_task(task_id)
        if task is None:
            return

        parse_task.mark_running(task_id)

        # 进度回调：把 pipeline 的上报转换为对数据库的更新
        def on_progress(stage: str, current: int, total: int) -> None:
            # 三个阶段权重分配（粗略估算）：
            #   解析 40% / 切分 5% / 索引 55%
            # 这样进度条在向量化阶段不会突然跳到 100%
            stage_weight = {"解析": 40, "切分": 5, "索引": 55}
            base = sum(
                stage_weight[s]
                for s in ("解析", "切分", "索引")
                if list(stage_weight).index(s) < list(stage_weight).index(stage)
            ) if stage in stage_weight else 0
            current_weight = stage_weight.get(stage, 0)

            pct = base + int(current_weight * (current / max(total, 1)))
            parse_task.update_progress(task_id, min(pct, 99), stage)

        # 跑 M0（这一步很慢，几十秒）
        result = pipeline.ingest_document(
            path=task["file_path"],
            course=task.get("course_key") or "unknown",
            progress=on_progress,
        )

        # 登记到 materials 表
        # 【为什么登记放在这里而不是 pipeline 里】
        #   pipeline 保持纯粹（只做文件 → 向量），不碰数据库。
        #   数据库操作由调用方负责。
        if result.ok:
            try:
                from app.database import materials as material_store

                upload_type = task.get("upload_type") or "supplement"
                course_key = task.get("course_key")

                course_id = None
                if course_key:
                    from app.database import courses as course_store
                    c = course_store.get_by_name(course_key)
                    if c:
                        course_id = int(c["id"])

                material_id = material_store.upsert(
                    source_file=result.source_file,
                    kind=result.kind,
                    upload_type=upload_type,
                    chunk_count=result.chunk_count,
                    page_count=result.page_count,
                    ocr_used=result.ocr_used,
                    course_id=course_id,
                )

                if upload_type == "textbook" and course_id is not None:
                    try:
                        from app.pipeline.doc_parser import save_to_markdown
                        md_path = save_to_markdown(
                            result.parsed,
                            course_id=course_id,
                            material_id=material_id,
                        )
                        material_store.update_markdown_path(
                            material_id, str(md_path),
                        )
                        result.warnings.append(f"Markdown 已保存至：{md_path}")
                    except Exception as exc:  # noqa: BLE001
                        result.warnings.append(f"Markdown 保存失败：{exc}")

            except Exception as exc:  # noqa: BLE001
                # 登记失败不影响解析结果，只记个警告
                result.warnings.append(f"资料登记到数据库失败：{exc}")

        # 教材解析成功后，如果指定了 course_key，尝试自动抽取章节
        if result.ok and task.get("upload_type") == "textbook":
            _maybe_auto_extract_chapters(task, result)

        # 标记完成
        parse_task.mark_done(
            task_id=task_id,
            page_count=result.page_count,
            chunk_count=result.chunk_count,
            ocr_used=result.ocr_used,
            warnings=result.warnings,
        )

    except Exception as exc:  # noqa: BLE001 - 见 docstring：必须捕获一切
        import traceback
        traceback.print_exc()

        try:
            parse_task.mark_failed(
                task_id=task_id,
                error=f"{type(exc).__name__}: {exc}",
            )
        except Exception:  # noqa: BLE001 - 标记失败也不该崩
            pass


# ==============================================================
# 自动章节抽取（教材解析完成后）
# ==============================================================
def _maybe_auto_extract_chapters(task: dict, result: Any) -> None:
    """教材解析完成后，如果指定了 course_key，尝试自动抽取章节。

    这是 best-effort 操作：失败不报错，不影响解析流程。
    course_key 对应的课程必须已存在，否则跳过（课程创建是分类流程的事）。
    """
    import traceback

    course_key = (task.get("course_key") or "").strip()
    if not course_key or course_key == "unknown":
        return

    try:
        from app.database import courses as course
        course_row = course.get_by_name(course_key)
        if course_row is None:
            return
        course_id = int(course_row["id"])
    except Exception:
        return

    # 获取教材全文
    chunks = getattr(result, "chunks", []) or []
    if not chunks:
        return
    full_text = "\n\n".join(getattr(c, "text", "") or "" for c in chunks)
    if not full_text.strip():
        return

    try:
        from app.database.chapters import bulk_create_chapters
        from app.ai.chapter_extractor import extract_chapters_from_textbook
        from app.ai.llm_client import LLMClient

        llm = LLMClient()
        extracted = extract_chapters_from_textbook(full_text, course_id, llm)
        ids = bulk_create_chapters(course_id, extracted)
        print(f"[章节自动抽取] task={task.get('id')} 创建了 {len(ids)} 个章节")
    except Exception as exc:
        print(f"[章节自动抽取跳过] task={task.get('id')}: {type(exc).__name__}: {exc}")
        traceback.print_exc()


# ==============================================================
# 关闭
# ==============================================================
def shutdown(wait: bool = False) -> None:
    """关闭线程池。

    【什么时候调用】
        应用退出时（FastAPI 的 lifespan 事件里）。

    Args:
        wait: True 表示等待正在跑的任务完成；False 表示立即返回。
            生产环境应该传 True（让正在跑的任务跑完），
            但开发环境传 False 更快（不阻塞 Ctrl+C）。
    """
    global _EXECUTOR
    if _EXECUTOR is not None:
        _EXECUTOR.shutdown(wait=wait)
        _EXECUTOR = None