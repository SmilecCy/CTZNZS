# -*- coding: utf-8 -*-
"""ai 包：AI 智能服务层。

【职责】
    所有与大模型（LLM）相关的调用都在本层。
    包括：LLM 客户端、向量嵌入、题目生成、评分、章节抽取/匹配、搜索。

【模块】
    llm_client          - LLM 客户端（DeepSeek 等）
    embedder            - 文本嵌入（sentence-transformers）
    generator           - 题目生成
    grader              - 答案评分
    chapter_extractor   - 章节自动抽取
    chapter_matcher     - 章节模糊匹配
    chunk_classifier    - 分块分类到章节
    material_classifier - 资料类型分类
    search_tool         - 知识检索工具
"""