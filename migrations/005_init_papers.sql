-- ============================================================
-- 文件：005_init_papers.sql
-- 用途：试卷 + 试卷题目关联
--
-- 【Q5 决策：组卷，引用不复制】
--   试卷只是"从题库挑一组题"，不复制题目内容。
--   所以题库改了会影响试卷——这是有意的：
--   题库里的题有质量分、使用次数，组卷时要挑好题。
--
-- 【如果需要"试卷快照"】
--   另有 answer_records.question_snapshot 字段在作答时存快照。
--   这样即使题库变了，学生当时的作答仍然按当时的题目判分（Q11 决策）。
-- ============================================================

CREATE TABLE IF NOT EXISTS papers (
    id              INT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '试卷主键',

    course_id       INT NOT NULL
                    COMMENT '所属课程',

    title           VARCHAR(200) NOT NULL
                    COMMENT '试卷标题',

    description     TEXT
                    COMMENT '试卷说明',

    total_questions INT NOT NULL DEFAULT 0
                    COMMENT '题目总数（冗余，避免每次 COUNT）',

    total_score     DECIMAL(6,2) NOT NULL DEFAULT 0.00
                    COMMENT '总分',

    created_by      INT NULL
                    COMMENT '创建人（管理员 id）',

    is_active       TINYINT(1) NOT NULL DEFAULT 1
                    COMMENT '是否启用。软删除用',

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '创建时间',

    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP
                    COMMENT '更新时间',

    KEY idx_papers_course (course_id),

    CONSTRAINT fk_papers_course
        FOREIGN KEY (course_id) REFERENCES courses(id)
        ON DELETE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='试卷表';


CREATE TABLE IF NOT EXISTS paper_questions (
    id              INT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '关联主键',

    paper_id        INT NOT NULL
                    COMMENT '试卷 id',

    question_id     INT NOT NULL
                    COMMENT '题库里的题目 id',

    sort_order      INT NOT NULL DEFAULT 0
                    COMMENT '题目在试卷里的顺序',

    score           DECIMAL(6,2) NOT NULL DEFAULT 0.00
                    COMMENT '这道题在本次试卷里的分值',

    KEY idx_pq_paper (paper_id),
    KEY idx_pq_question (question_id),

    -- 同一份试卷里同一道题只能出现一次
    UNIQUE KEY uk_pq_paper_question (paper_id, question_id),

    -- 试卷被删 → 关联跟着删
    CONSTRAINT fk_pq_paper
        FOREIGN KEY (paper_id) REFERENCES papers(id)
        ON DELETE CASCADE,

    -- 题目被删 → 关联跟着删
    -- 这里用 CASCADE 而不是 SET NULL：题目没了，试卷里留个空位没意义，
    -- 反而会让"题目总数"和实际题目对不上。
    CONSTRAINT fk_pq_question
        FOREIGN KEY (question_id) REFERENCES question_bank(id)
        ON DELETE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='试卷-题目关联表';