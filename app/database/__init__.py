# -*- coding: utf-8 -*-
"""database 包：数据库访问层（DAO）。

【职责】
    所有与 MySQL / Redis 的直接交互都在本层。
    包括：连接管理、缓存、CRUD 操作。

【模块】
    connection      - MySQL 连接池（原 db_mysql）
    redis           - Redis 客户端（原 db_redis）
    cache           - 缓存抽象层
    courses         - 课程 CRUD（原 course）
    chapters        - 章节 CRUD（原 chapter）
    materials       - 资料存储（原 material_store）
    parse_tasks     - 解析任务 CRUD（原 parse_task）
    knowledge_points - 知识点 CRUD（原 knowledge_point）
    questions       - 题库 CRUD（原 question_bank_mysql）
    answers         - 答案 CRUD（原 answer_mysql）
    wrong_book      - 错题本 CRUD（原 wrong_book_mysql）
    notes           - 笔记 CRUD（原 note）
    favorites       - 收藏 CRUD（原 favorite）
    stats           - 统计数据查询（原 stats）
"""