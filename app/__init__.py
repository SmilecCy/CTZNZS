# -*- coding: utf-8 -*-
"""app 包：司法考试 AI 辅助学习系统 · 业务层。

【分层说明】
    ai/       —— AI 域（LLM 客户端 / 出题 / 判分 / 章节匹配 / 分类器 / 向量化）
    pipeline/ —— 资料处理域（解析 / 切分 / 索引 / 编排 / 异步解析）
    database/ —— 数据访问域（MySQL 连接池 / Redis / 缓存 / 各域 DAO）
    auth/     —— 认证域（JWT 签发验证 / 用户注册登录）
    frontend/ —— Streamlit 管理员内部工具（6 个标签页）
    prompts/  —— LLM 提示词库（按模块+版本管理）

【架构】
    表现层：React（学生端） + Streamlit（管理员工具）
    接口层：FastAPI（api/）
    业务层：本包
    数据层：MySQL（持久）+ Redis（缓存）+ FAISS（向量）
"""

__version__ = "4.0.0"