# -*- coding: utf-8 -*-
"""临时诊断：LLM 调用 + 资料分类 + 向量库取 chunk。"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from app.pipeline import indexer; from app.ai import llm_client, material_classifier; from app.database import materials as material_store


def section(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    # ========== 1. LLM 配置 ==========
    section("1. LLM 配置")
    client = llm_client.LLMClient()
    print(f"  已配置: {client.is_configured()}")
    print(f"  Base URL: {client.base_url}")
    print(f"  模型: {client.model}")

    # ========== 2. LLM 真实调用 ==========
    section("2. LLM 真实调用")
    if not client.is_configured():
        print("  [跳过] 未配置 API Key")
    else:
        try:
            resp = client.chat([
                {"role": "user", "content": "只返回这个 JSON，不要任何解释：{\"ok\": true}"}
            ])
            print(f"  [成功] 返回前 100 字: {resp.content[:100]}")
        except Exception as e:
            print(f"  [失败] {type(e).__name__}: {e}")
            traceback.print_exc()

    # ========== 3. 资料 17 ==========
    section("3. 资料 17")
    material = material_store.get_by_id(17)
    if material is None:
        print("  [跳过] 资料 17 不存在")
    else:
        print(f"  文件名: {material['source_file']}")
        print(f"  chunk_count: {material.get('chunk_count')}")
        print(f"  detection_status: {material.get('detection_status')}")

        # ========== 4. 向量库取 chunk ==========
        section("4. 向量库取 chunk")
        try:
            chunks = indexer.get_chunks_by_source(material["source_file"])
            print(f"  [成功] 找到 {len(chunks)} 个 chunk")
            if chunks:
                chunks.sort(key=lambda c: str(c.get("id", "")))
                sample = "\n\n".join(str(c.get("text", "")) for c in chunks[:3])
                print(f"  样本文本长度: {len(sample)}")
                print(f"  前 200 字: {sample[:200]}")

                # ========== 5. 分类调用 ==========
                section("5. 分类调用")
                try:
                    result = material_classifier.classify_material(
                        material_id=17,
                        sample_text=sample,
                        doc_title="",
                    )
                    print(f"  [成功]")
                    print(f"    success: {result.get('success')}")
                    print(f"    course_name: {result.get('course_name')}")
                    print(f"    confidence: {result.get('course_confidence')}")
                    print(f"    knowledge_points: {len(result.get('knowledge_points') or [])} 个")
                    print(f"    error: {result.get('error')}")
                except Exception as e:
                    print(f"  [失败] {type(e).__name__}: {e}")
                    traceback.print_exc()
            else:
                print("  [警告] 向量库里没有这份资料的 chunk")
        except Exception as e:
            print(f"  [失败] {type(e).__name__}: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    main()