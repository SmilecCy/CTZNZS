-- ============================================================
-- 文件：003_init_question_bank.sql
-- 用途：题库表
--
-- 【这是系统的核心表】
--   出题时先查这里：
--   - 命中 → 直接返回，不调 LLM（省钱、快、可复现）
--   - 未命中 → 后台预热时已用 LLM 生成并入库
--
-- 【为什么存 question_json 而不是拆成多个字段】
--   简答题和选择题的字段完全不同：
--     简答：题干、参考答案、评分要点
--     选择：题干、选项数组、正确选项下标、解析
--   如果拆成字段，一半会是 NULL。
--   用 JSON 存，两种题型共用一张表，查询时按需解析。
-- ============================================================

CREATE TABLE IF NOT EXISTS question_bank (
    id              INT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '题目主键',

    course_id       INT NOT NULL
                    COMMENT '所属课程 id',

    knowledge_point_id INT NULL
                    COMMENT '所属知识点 id。NULL 表示未分类',

    knowledge_point VARCHAR(200) NOT NULL
                    COMMENT '知识点名（冗余字段）。方便查询和显示，避免每次 JOIN',

    question_type   VARCHAR(20) NOT NULL
                    COMMENT '题型：简答 / 选择',

    difficulty      VARCHAR(10) NOT NULL
                    COMMENT '难度：易 / 中 / 难',

    question_json   TEXT NOT NULL
                    COMMENT '题目完整内容 JSON：题干、选项、答案、评分要点、解析等',

    source          VARCHAR(30) NOT NULL
                    COMMENT '来源：generated（LLM 生成）/ web_search（搜索补充）/ user_imported（资料抽取）',

    source_ref      VARCHAR(500)
                    COMMENT '来源引用：chunk_id 或搜索 URL。用于追溯',

    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                    COMMENT '状态：active（在用）/ deprecated（已废弃）',

    prompt_version  VARCHAR(20)
                    COMMENT '生成时用的提示词版本。用于迭代分析',

    model_version   VARCHAR(100)
                    COMMENT '生成时用的模型版本',

    generated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '生成时间',

    usage_count     INT NOT NULL DEFAULT 0
                    COMMENT '被抽出使用的次数',

    quality_score   DECIMAL(5,2) NOT NULL DEFAULT 0.00
                    COMMENT '质量分。好评 +1，差评 -1。影响抽题权重',

    user_feedback   TEXT
                    COMMENT '用户反馈计数 JSON：{good: n, bad: n, duplicate: n}',

    -- 【索引设计】
    -- 出题时最常见的查询是"某课程某知识点某题型某难度，且 active"。
    -- 这个复合索引正好覆盖它，顺序也按"区分度从高到低"排：
    -- 课程 → 知识点 → 题型 → 难度 → 状态
    KEY idx_qb_query (course_id, knowledge_point, question_type, difficulty, status),

    KEY idx_qb_course (course_id),
    KEY idx_qb_kp (knowledge_point_id),
    KEY idx_qb_status (status),

    -- 课程被删 → 题目跟着删（题目离开课程没意义）
    CONSTRAINT fk_qb_course
        FOREIGN KEY (course_id) REFERENCES courses(id)
        ON DELETE CASCADE,

    -- 知识点被删 → 题目不删，knowledge_point_id 置 NULL
    -- 为什么不用 CASCADE：删一个知识点不该把题目也删了，
    -- 题目可能还要重新归类。
    CONSTRAINT fk_qb_kp
        FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id)
        ON DELETE SET NULL

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='题库表';