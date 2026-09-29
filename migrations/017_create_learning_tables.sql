-- ============================================================
-- 文件：017_create_learning_tables.sql
-- 用途：学习域新表 — 章节请求日志、收藏、笔记
-- ============================================================

-- ---------- 章节请求日志 ----------
CREATE TABLE IF NOT EXISTS chapter_request_log (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT
                    COMMENT '主键',

    user_id         INT NOT NULL
                    COMMENT '请求用户',

    course_id       INT NOT NULL
                    COMMENT '所属课程',

    chapter_id      INT NULL
                    COMMENT '匹配到的章节 id。NULL 表示未匹配',

    input_text      VARCHAR(500) NOT NULL
                    COMMENT '用户输入的章节标题',

    matched_name    VARCHAR(200)
                    COMMENT '匹配到的章节名',

    reply_text      TEXT
                    COMMENT 'LLM 生成的回复文本',

    llm_model       VARCHAR(100)
                    COMMENT '使用的模型名',

    llm_tokens      INT DEFAULT 0
                    COMMENT '消耗 token 数',

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '请求时间',

    KEY idx_crl_user_course (user_id, course_id),
    KEY idx_crl_chapter (chapter_id),

    CONSTRAINT fk_crl_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_crl_course
        FOREIGN KEY (course_id) REFERENCES courses(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_crl_chapter
        FOREIGN KEY (chapter_id) REFERENCES knowledge_points(id)
        ON DELETE SET NULL

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='章节请求日志';


-- ---------- 题目收藏 ----------
CREATE TABLE IF NOT EXISTS question_favorites (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT
                    COMMENT '主键',

    user_id         INT NOT NULL
                    COMMENT '收藏用户',

    question_id     INT NOT NULL
                    COMMENT '题目 id',

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '收藏时间',

    UNIQUE KEY uk_qf_user_question (user_id, question_id),
    KEY idx_qf_user (user_id),

    CONSTRAINT fk_qf_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_qf_question
        FOREIGN KEY (question_id) REFERENCES question_bank(id)
        ON DELETE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='题目收藏表';


-- ---------- 题目笔记 ----------
CREATE TABLE IF NOT EXISTS question_notes (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT
                    COMMENT '主键',

    user_id         INT NOT NULL
                    COMMENT '笔记作者',

    question_id     INT NOT NULL
                    COMMENT '题目 id',

    content         TEXT NOT NULL
                    COMMENT '笔记内容',

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '创建时间',

    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP
                    COMMENT '更新时间',

    UNIQUE KEY uk_qn_user_question (user_id, question_id),
    KEY idx_qn_user (user_id),

    CONSTRAINT fk_qn_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_qn_question
        FOREIGN KEY (question_id) REFERENCES question_bank(id)
        ON DELETE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='题目笔记表';