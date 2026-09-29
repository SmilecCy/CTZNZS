-- ============================================================
-- 文件：010_init_logs.sql
-- 用途：四张日志表
--   llm_call_log     LLM 调用审计
--   search_call_log  搜索调用审计
--   serving_log      出题埋点（命中率数据源）
--   extract_log      抽取记录（避免重复付费）
-- ============================================================

-- ---------- LLM 调用审计 ----------
-- 每次调 LLM（含失败）都写一条。
-- 用途：成本审计、排查问题、"预热后不再调用"这条验收标准的证据。
CREATE TABLE IF NOT EXISTS llm_call_log (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '日志主键',

    purpose             VARCHAR(50) NOT NULL
                    COMMENT '用途：generate_question / regen_duplicate / grade_answer / flashcard / graph 等',

    course_id           INT NULL
                    COMMENT '课程 id。有些调用不涉及具体课程，允许 NULL',

    knowledge_point     VARCHAR(200)
                    COMMENT '知识点',

    question_type       VARCHAR(20)
                    COMMENT '题型',

    prompt_version      VARCHAR(20)
                    COMMENT '用的提示词版本。迭代分析用',

    model_version       VARCHAR(100)
                    COMMENT '模型版本',

    prompt_tokens       INT NOT NULL DEFAULT 0
                    COMMENT '输入 token 数',

    completion_tokens   INT NOT NULL DEFAULT 0
                    COMMENT '输出 token 数',

    latency_ms          INT NOT NULL DEFAULT 0
                    COMMENT '耗时（毫秒）',

    success             TINYINT(1) NOT NULL DEFAULT 1
                    COMMENT '是否成功。失败也记，用于排查',

    error               VARCHAR(500)
                    COMMENT '失败原因。成功时为 NULL',

    called_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '调用时间',

    KEY idx_llm_time (called_at),
    KEY idx_llm_course (course_id)

    -- 【为什么不设 course 外键】
    -- 审计日志必须比业务数据活得更久。如果课程被彻底删除，
    -- 日志也跟着消失，就查不出"当初花了多少钱"。
    -- 所以这里存 course_id 但不设外键。

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='LLM 调用审计';


-- ---------- 搜索调用审计 ----------
-- 每次调搜索引擎都写一条。
-- 用途与 llm_call_log 相同，只是统计对象不同。
CREATE TABLE IF NOT EXISTS search_call_log (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '日志主键',

    purpose             VARCHAR(50) NOT NULL
                    COMMENT '用途：supplement_material / verify_fact 等',

    course_id           INT NULL
                    COMMENT '课程 id',

    knowledge_point     VARCHAR(200)
                    COMMENT '知识点',

    query               VARCHAR(500) NOT NULL
                    COMMENT '搜索关键词',

    engine              VARCHAR(30) NOT NULL DEFAULT 'bocha'
                    COMMENT '搜索引擎：bocha / serper / tavily 等',

    result_count        INT NOT NULL DEFAULT 0
                    COMMENT '返回结果条数',

    latency_ms          INT NOT NULL DEFAULT 0
                    COMMENT '耗时（毫秒）',

    success             TINYINT(1) NOT NULL DEFAULT 1
                    COMMENT '是否成功',

    error               VARCHAR(500)
                    COMMENT '失败原因',

    called_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '调用时间',

    KEY idx_search_time (called_at),
    KEY idx_search_course (course_id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='搜索调用审计';


-- ---------- 出题埋点 ----------
-- 每次"向用户真实出题"写一条。
-- 【关键】预热与批量更新不写！
--   预热必然 from_bank=0（因为 force_generate=True 跳过查库），
--   混进来会把命中率曲线压成一条直线，指标就废了。
CREATE TABLE IF NOT EXISTS serving_log (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '埋点主键',

    course_id       INT NOT NULL
                    COMMENT '课程 id',

    knowledge_point VARCHAR(200)
                    COMMENT '知识点',

    question_type   VARCHAR(20)
                    COMMENT '题型',

    difficulty      VARCHAR(10)
                    COMMENT '难度',

    requested       INT NOT NULL DEFAULT 0
                    COMMENT '本次请求几道题',

    from_bank       INT NOT NULL DEFAULT 0
                    COMMENT '其中几道来自题库',

    from_llm        INT NOT NULL DEFAULT 0
                    COMMENT '其中几道来自现场生成',

    served_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '出题时间',

    KEY idx_serving_day (course_id, served_at),
    KEY idx_serving_course (course_id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='出题埋点';


-- ---------- 抽取记录 ----------
-- 记录"哪份资料的哪个分段已经抽过题"。
-- 【为什么需要】不记的话，重跑一次抽取会把同一批分段再问一遍模型，
-- 白花钱。而"重跑"很常见：中途停下、某几段失败、想调低门槛再补一遍……
-- 有了这张表，重跑只处理没做过的分段。
CREATE TABLE IF NOT EXISTS extract_log (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '记录主键',

    course_id   INT NOT NULL
                    COMMENT '课程 id',

    chunk_id    VARCHAR(200) NOT NULL
                    COMMENT '分段 id。例如"侵权责任法讲义_0007"',

    source_file VARCHAR(500) NOT NULL
                    COMMENT '来源文件名',

    extracted   INT NOT NULL DEFAULT 0
                    COMMENT '这段抽到几道题',

    inserted    INT NOT NULL DEFAULT 0
                    COMMENT '其中新入库几道',

    scanned_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '扫描时间',

    -- 同一课程、同一分段只记一条
    UNIQUE KEY uk_extract_course_chunk (course_id, chunk_id),

    -- 查"某份资料已经抽过哪些段"
    KEY idx_extract_file (course_id, source_file)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='资料抽取记录';