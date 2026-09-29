# -*- coding: utf-8 -*-
"""pipeline 包：文档处理流水线。

【职责】
    文档解析 → 分块 → 索引 的端到端流程。
    不依赖 HTTP 框架，可被 API 或命令行调用。

【模块】
    doc_parser      - 文档解析（PDF/DOCX/图片/TXT）
    chunker         - 文本分块
    indexer         - FAISS 向量索引
    orchestrator    - 流水线编排（原 pipeline）
    material_merge  - 资料合并
    parse_worker    - 异步解析工作器
"""