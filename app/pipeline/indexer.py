# -*- coding: utf-8 -*-
"""M0-v0.2 索引层：FAISS 本地向量库的写入、检索与状态统计。

v0.2 从 Chroma 迁移到 FAISS。
Chroma 的 HNSW 索引反复损坏（Error loading hnsw index / Error finding id），
且 Windows 上文件句柄不释放导致重置失败。FAISS（Meta 维护的 C++ 库）
极其稳定，索引格式十年不变。

对外暴露的函数签名与 v0.1 完全兼容，调用方无需改动。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from app.config import TOP_K, VECTOR_DIR
from app.pipeline.chunker import Chunk
from app.ai.embedder import embed_query, embed_texts

# ---------------------------------------------------------------
# 常量
# ---------------------------------------------------------------
_MATERIALS_DIR: Path = VECTOR_DIR / "materials"
_DEDUP_DIR: Path = VECTOR_DIR / "dedup"

# BGE-small-zh-v1.5 输出维度。
_DIM: int = 512

# 搜索时为元数据过滤留出余量：搜 top_k * 这个倍数条，
# 然后按 course / source_file 过滤，保证最终至少有 top_k 条。
_SEARCH_MULTIPLIER: int = 10


class VectorStoreUnavailableError(RuntimeError):
    """向量库不可用：faiss-cpu 未安装，或磁盘上的索引文件损坏。"""


# =================================================================
# 内部：索引与元数据的持久化
# =================================================================

def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _make_index() -> Any:
    """创建一个新的 FAISS 索引。

    IndexFlatIP + L2 归一化向量 = 余弦相似度。
    内积越接近 1 表示越相似。
    """
    try:
        import faiss  # noqa: PLC0415
    except ImportError as exc:
        raise VectorStoreUnavailableError(
            "需要向量库但未安装 faiss-cpu。请执行：\n"
            "    pip install faiss-cpu"
        ) from exc

    return faiss.IndexIDMap(faiss.IndexFlatIP(_DIM))


def _faiss_read_index(filepath: str) -> Any:
    """读取 FAISS 索引，通过临时文件绕过中文路径问题（FAISS C++ 层不支持 UTF-8 路径）。"""
    import faiss  # noqa: PLC0415

    try:
        return faiss.read_index(filepath)
    except RuntimeError:
        # 中文路径 → 复制到临时目录再读
        with tempfile.NamedTemporaryFile(suffix=".faiss", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            shutil.copy2(filepath, tmp_path)
            return faiss.read_index(tmp_path)
        finally:
            os.unlink(tmp_path)


def _faiss_write_index(index: Any, filepath: str) -> None:
    """写入 FAISS 索引，通过临时文件绕过中文路径问题。"""
    import faiss  # noqa: PLC0415

    try:
        faiss.write_index(index, filepath)
        return
    except RuntimeError:
        pass

    # 中文路径 → 先写临时文件再 move
    with tempfile.NamedTemporaryFile(suffix=".faiss", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        faiss.write_index(index, tmp_path)
        shutil.move(tmp_path, filepath)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _load_faiss(index_dir: Path) -> Any:
    """加载 FAISS 索引；目录为空时创建新索引。"""
    path = index_dir / "index.faiss"
    if path.exists():
        try:
            return _faiss_read_index(str(path))
        except Exception as exc:
            raise VectorStoreUnavailableError(
                f"FAISS 索引文件损坏：{exc}\n"
                "索引是派生数据，删掉重建不会丢任何东西。\n"
                "到「资料管理」页点「重置向量库」，然后重新解析资料即可。"
            ) from exc
    return _make_index()


def _save_faiss(index_dir: Path, index: Any) -> None:
    """持久化 FAISS 索引。"""
    _ensure_dir(index_dir)
    _faiss_write_index(index, str(index_dir / "index.faiss"))


def _load_meta(meta_path: Path) -> tuple[dict[int, dict], dict[str, int], int]:
    """加载元数据 JSON。

    Returns:
        (metas, id_map, next_id)
        - metas: {faiss_id(int): metadata(dict)}
        - id_map: {chunk_id(str): faiss_id(int)}
        - next_id: 下一个可用的 faiss 内部 id
    """
    if meta_path.exists():
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return (
            {int(k): v for k, v in data.get("metas", {}).items()},
            data.get("id_map", {}),
            data.get("next_id", 0),
        )
    return {}, {}, 0


def _save_meta(meta_path: Path, metas: dict[int, dict], id_map: dict[str, int], next_id: int) -> None:
    """原子写入元数据 JSON（先写临时文件再 replace）。"""
    data = {
        "metas": {str(k): v for k, v in metas.items()},
        "id_map": id_map,
        "next_id": next_id,
    }
    tmp = meta_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # Windows 上 rename 在目标存在时会抛 FileExistsError，用 replace 替代
    tmp.replace(meta_path)


def _load_state(index_dir: Path) -> tuple[Any, dict[int, dict], dict[str, int], int]:
    """加载索引 + 元数据。

    Returns:
        (index, metas, id_map, next_id)
    """
    _ensure_dir(index_dir)
    index = _load_faiss(index_dir)
    metas, id_map, next_id = _load_meta(index_dir / "metadata.json")
    return index, metas, id_map, next_id


def _save_state(index_dir: Path, index: Any, metas: dict[int, dict], id_map: dict[str, int], next_id: int) -> None:
    """持久化索引 + 元数据。"""
    _ensure_dir(index_dir)
    _save_faiss(index_dir, index)
    _save_meta(index_dir / "metadata.json", metas, id_map, next_id)


# =================================================================
# 公开 API ：资料索引
# =================================================================

def index_chunks(chunks: list[Chunk], course: str) -> int:
    """把 chunk 向量化后写入向量库。

    upsert 语义：同 id 重复索引会覆盖而非报错，支持"重新解析同一份资料"。

    Args:
        chunks: 切分结果。
        course: 课程 key，作为可过滤字段写入元数据。

    Returns:
        实际写入的 chunk 数量。
    """
    if not chunks:
        return 0

    import faiss  # noqa: PLC0415

    index_dir = _MATERIALS_DIR
    index, metas, id_map, next_id = _load_state(index_dir)

    # 1. 找出需要更新的旧条目
    remove_faiss_ids: list[int] = []
    removed_chunk_ids: set[str] = set()

    for chunk in chunks:
        cid = str(chunk.id)
        if cid in id_map:
            remove_faiss_ids.append(id_map[cid])
            removed_chunk_ids.add(cid)

    # 2. 删除旧条目
    if remove_faiss_ids:
        selector = faiss.IDSelectorBatch(np.array(remove_faiss_ids, dtype=np.int64))
        index.remove_ids(selector)
        for fid in remove_faiss_ids:
            metas.pop(fid, None)
        for cid in removed_chunk_ids:
            id_map.pop(cid, None)

    # 3. 批量向量化
    texts = [c.text for c in chunks]
    embeddings = embed_texts(texts)

    # 4. 写入新条目
    vectors: list[list[float]] = []
    add_ids: list[int] = []
    new_metas: dict[int, dict] = {}

    for chunk, emb in zip(chunks, embeddings):
        fid = next_id
        next_id += 1
        id_map[str(chunk.id)] = fid

        new_metas[fid] = {
            "id": str(chunk.id),
            "text": chunk.text,
            "source_file": chunk.metadata.get("source_file", ""),
            "course": course,
            "page": chunk.metadata.get("page", 0),
            "section_title": chunk.metadata.get("section_title", ""),
        }
        vectors.append(emb)
        add_ids.append(fid)

    if vectors:
        vecs = np.array(vectors, dtype=np.float32)
        ids_arr = np.array(add_ids, dtype=np.int64)
        index.add_with_ids(vecs, ids_arr)
        metas.update(new_metas)

    _save_state(index_dir, index, metas, id_map, next_id)
    return len(chunks)


def search(
    query: str,
    course: str | None = None,
    top_k: int = TOP_K,
    source_file: str | None = None,
) -> list[dict]:
    """按语义检索资料片段。

    FAISS 不支持元数据过滤，因此先搜 top_k * 10 条，
    再在 Python 侧按 course / source_file 过滤，保证最终至少有 top_k 条。

    Args:
        query: 查询文本。
        course: 限定课程；None 表示跨课程检索。
        top_k: 返回条数。
        source_file: 限定只在某份资料内检索。

    Returns:
        列表，每项含 id / text / source_file / page / section_title /
        course / similarity（0~1，越大越相关）。
    """
    _, metas, _, _ = _load_state(_MATERIALS_DIR)
    total = len(metas)
    if total == 0:
        return []

    index, _, _, _ = _load_state(_MATERIALS_DIR)

    q_vec = embed_query(query)
    search_k = min(top_k * _SEARCH_MULTIPLIER, total)
    scores, labels = index.search(np.array([q_vec], dtype=np.float32), search_k)

    hits: list[dict] = []
    for score, label in zip(scores[0], labels[0]):
        fid = int(label)
        if fid < 0:
            continue
        meta = metas.get(fid)
        if meta is None:
            continue
        if course and meta.get("course") != course:
            continue
        if source_file and meta.get("source_file") != source_file:
            continue

        hits.append({
            "id": meta["id"],
            "text": meta["text"],
            "source_file": meta["source_file"],
            "course": meta["course"],
            "page": meta.get("page", 0),
            "section_title": meta.get("section_title", ""),
            "similarity": round(float(score), 4),
        })

        if len(hits) >= top_k:
            break

    return hits


def index_stats() -> dict:
    """返回索引状态，供界面展示。

    这个函数绝不能往外抛异常。侧边栏在每个页面都会调它。
    """
    try:
        _, metas, _, _ = _load_state(_MATERIALS_DIR)
        total = len(metas)

        if total == 0:
            return {"chunks": 0, "courses": {}, "available": True, "error": None}

        counts: dict[str, int] = {}
        for meta in metas.values():
            key = meta.get("course", "unknown")
            counts[key] = counts.get(key, 0) + 1

        return {"chunks": total, "courses": counts, "available": True, "error": None}

    except VectorStoreUnavailableError as exc:
        return {"chunks": 0, "courses": {}, "available": False, "error": str(exc)}
    except Exception as exc:
        return {
            "chunks": 0, "courses": {}, "available": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def prune_source(source_file: str, keep_ids: set[str]) -> int:
    """删掉某份资料下不在 keep_ids 里的旧 chunk。

    先写后清：新数据先落进去（upsert），清理只是收尾。
    清理失败不影响新数据的可用性。

    Args:
        source_file: 资料文件名。
        keep_ids: 本次写入的 chunk id 集合。

    Returns:
        删掉的旧 chunk 数量。
    """
    import faiss  # noqa: PLC0415

    index_dir = _MATERIALS_DIR
    index, metas, id_map, next_id = _load_state(index_dir)

    keep_set = {str(k) for k in keep_ids}
    remove_faiss_ids: list[int] = []
    remove_chunk_ids: list[str] = []

    for fid, meta in metas.items():
        if meta.get("source_file") == source_file and meta["id"] not in keep_set:
            remove_faiss_ids.append(fid)
            remove_chunk_ids.append(meta["id"])

    if remove_faiss_ids:
        selector = faiss.IDSelectorBatch(np.array(remove_faiss_ids, dtype=np.int64))
        index.remove_ids(selector)
        for fid in remove_faiss_ids:
            metas.pop(fid, None)
        for cid in remove_chunk_ids:
            id_map.pop(cid, None)
        _save_state(index_dir, index, metas, id_map, next_id)

    return len(remove_faiss_ids)


def reset_store() -> dict:
    """整个清空向量库。

    FAISS 在每次调用后不会持有文件句柄，因此无需像 Chroma 那样
    先 released。直接删目录即可。

    不会碰到原始资料，也不动题库、错题、闪卡——它们都在 MySQL 里。

    Returns:
        {"removed": 删掉几项, "failed": [删不掉的项及原因],
         "ok": 是否全部删掉, "path": 目录路径}
    """
    removed = 0
    failed: list[str] = []

    if VECTOR_DIR.exists():
        for child in VECTOR_DIR.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
                removed += 1
            except OSError as exc:
                failed.append(f"{child.name}（{exc.strerror or exc}）")

    VECTOR_DIR.mkdir(parents=True, exist_ok=True)

    return {
        "removed": removed,
        "failed": failed,
        "ok": not failed,
        "path": str(VECTOR_DIR),
    }


def get_chunks_by_source(source_file: str) -> list[dict]:
    """取回某份资料的 chunk（供解析结果预览页展示与修正）。"""
    _, metas, _, _ = _load_state(_MATERIALS_DIR)
    return [
        {"id": meta["id"], "text": meta["text"], **meta}
        for meta in metas.values()
        if meta.get("source_file") == source_file
    ]


def update_section_title(chunk_id: str, new_title: str) -> bool:
    """人工修正某个 chunk 的章节标题。

    Args:
        chunk_id: chunk 主键。
        new_title: 修正后的章节标题。

    Returns:
        是否命中并更新成功。
    """
    index_dir = _MATERIALS_DIR
    index, metas, id_map, next_id = _load_state(index_dir)

    fid = id_map.get(str(chunk_id))
    if fid is None or fid not in metas:
        return False

    metas[fid]["section_title"] = new_title
    metas[fid]["title_edited"] = True
    _save_state(index_dir, index, metas, id_map, next_id)
    return True


def delete_by_source(source_file: str) -> int:
    """删除某份资料在向量库里的所有 chunk。

    用户删除一份资料时，把它在向量库里的所有痕迹清掉，
    避免向量库里残留孤儿数据。

    Args:
        source_file: 资料文件名。

    Returns:
        实际删除的 chunk 数。
    """
    import faiss  # noqa: PLC0415

    index_dir = _MATERIALS_DIR
    index, metas, id_map, next_id = _load_state(index_dir)

    remove_faiss_ids: list[int] = []
    remove_chunk_ids: list[str] = []

    for fid, meta in metas.items():
        if meta.get("source_file") == source_file:
            remove_faiss_ids.append(fid)
            remove_chunk_ids.append(meta["id"])

    if not remove_faiss_ids:
        return 0

    selector = faiss.IDSelectorBatch(np.array(remove_faiss_ids, dtype=np.int64))
    index.remove_ids(selector)
    for fid in remove_faiss_ids:
        metas.pop(fid, None)
    for cid in remove_chunk_ids:
        id_map.pop(cid, None)

    _save_state(index_dir, index, metas, id_map, next_id)
    return len(remove_faiss_ids)


# =================================================================
# M2 题干去重专用集合
# =================================================================

def index_question_stem(question_id: int | str, text: str, course: str) -> None:
    """把题干向量写入去重集合。

    Args:
        question_id: 题库主键。
        text: 题干文本。
        course: 课程 key。
    """
    import faiss  # noqa: PLC0415

    index_dir = _DEDUP_DIR
    index, metas, id_map, next_id = _load_state(index_dir)

    qid = str(question_id)

    # 已有则先删旧
    if qid in id_map:
        old_fid = id_map[qid]
        selector = faiss.IDSelectorBatch(np.array([old_fid], dtype=np.int64))
        index.remove_ids(selector)
        metas.pop(old_fid, None)
        id_map.pop(qid, None)

    emb = embed_texts([text])[0]
    fid = next_id
    next_id += 1

    vecs = np.array([emb], dtype=np.float32)
    ids_arr = np.array([fid], dtype=np.int64)
    index.add_with_ids(vecs, ids_arr)

    id_map[qid] = fid
    metas[fid] = {"question_id": qid, "text": text, "course": course}

    _save_state(index_dir, index, metas, id_map, next_id)


def find_duplicate_question(
    text: str,
    course: str | None = None,
    threshold: float = 0.9,
) -> tuple[str, float] | None:
    """在去重集合中查找与给定题干高度相似的已有题目。

    Args:
        text: 待检查的题干。
        course: 限定课程。
        threshold: 相似度阈值。

    Returns:
        (已有题目 id, 相似度)；无重复时返回 None。
    """
    index, metas, _, _ = _load_state(_DEDUP_DIR)
    total = len(metas)
    if total == 0:
        return None

    q_vec = embed_texts([text])[0]
    scores, labels = index.search(np.array([q_vec], dtype=np.float32), 1)

    if len(labels[0]) == 0:
        return None

    fid = int(labels[0][0])
    if fid < 0:
        return None

    meta = metas.get(fid)
    if meta is None:
        return None

    if course and meta.get("course") != course:
        return None

    similarity = float(scores[0][0])
    if similarity >= threshold:
        return meta["question_id"], round(similarity, 4)

    return None


def delete_question_stem(question_id: int | str) -> None:
    """从去重集合中撤回某道题。"""
    import faiss  # noqa: PLC0415

    index_dir = _DEDUP_DIR
    index, metas, id_map, next_id = _load_state(index_dir)

    qid = str(question_id)
    if qid not in id_map:
        return

    fid = id_map[qid]
    selector = faiss.IDSelectorBatch(np.array([fid], dtype=np.int64))
    index.remove_ids(selector)
    metas.pop(fid, None)
    id_map.pop(qid, None)

    _save_state(index_dir, index, metas, id_map, next_id)