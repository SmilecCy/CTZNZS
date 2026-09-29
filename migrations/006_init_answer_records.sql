-- ============================================================
-- 文件：006_init_answer_records.sql
-- 用途：全量作答记录（答对答错都记）
--
-- 【与 wrong_questions 的关系】
--   answer_records：流水账。每次作答写一条，答对答错都写。
--   wrong_questions：学习状态。答错时才写，同题去重，记错次和掌握度。
--   两者并存（Q6 决策 A）。为什么要并存：
--     - 流水账用于统计（做了多少题、正确率趋势）
--     - 学习状态用于复习（哪道题还没掌握）
--   合成一张表的话，每次统计都要扫全表，而且"掌握度"这个字段
--   对答对的记录毫无意义（永远是 NULL）。
--
-- 【Q11 决策：允许提交（快照判分）】
--   question_snapshot 字段存的是作答时的题目内容。
--   这样即使题库里那道题后来被改了，学生当时的作答仍然按当时的题目判分。
-- ============================================================

CREATE TABLE IF NOT EXISTS answer_records (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '作答记录主键。用 BIGINT 因为流水量大，INT 可能不够',

    user_id         INT NOT NULL
                    COMMENT '学生 id',

    course_id       INT NOT NULL
                    COMMENT '课程 id',

    question_id     INT NULL
                    COMMENT '题目 id。允许 NULL：题目被删了，记录要留住',

    paper_id        INT NULL
                    COMMENT '试卷 id。NULL 表示不是考试，是自由练习',

    question_type   VARCHAR(20)
                    COMMENT '题型（冗余，避免每次 JOIN 题库）',

    user_answer     TEXT
                    COMMENT '学生的作答',

    is_correct      TINYINT(1) NULL
                    COMMENT '是否正确。NULL 表示没判出对错（简答题评分失败时）',

    score           DECIMAL(5,2) NULL
                    COMMENT '得分比例 0.00~1.00。选择题是 0 或 1',

    question_snapshot TEXT
                    COMMENT '作答时的题目快照 JSON。题目后来改了，这里还能看到原貌',

    graded_by       VARCHAR(20)
                    COMMENT '判分方式：auto（选择题自动比对）/ llm（简答题 LLM 评分）/ manual（人工）',

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '作答时间',

    -- 索引：
    --   idx_ar_user_course   查"某学生某课程的所有作答"（最常用）
    --   idx_ar_question      查"某道题被谁做过"
    --   idx_ar_paper         查"某张试卷的作答"
    --   idx_ar_time          按时间统计（做趋势图）
    KEY idx_ar_user_course (user_id, course_id),
    KEY idx_ar_question (question_id),
    KEY idx_ar_paper (paper_id),
    KEY idx_ar_time (created_at),

    -- 学生被删 → 作答记录跟着删
    CONSTRAINT fk_ar_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,

    -- 课程被删 → 作答记录跟着删
    CONSTRAINT fk_ar_course
        FOREIGN KEY (course_id) REFERENCES courses(id)
        ON DELETE CASCADE,

    -- 题目被删 → 作答记录不删，question_id 置 NULL
    -- 为什么不用 CASCADE：作答记录是历史，学生做过的题不能因为题目被删就消失。
    -- 快照字段（question_snapshot）保证了记录仍然可读。
    CONSTRAINT fk_ar_question
        FOREIGN KEY (question_id) REFERENCES question_bank(id)
        ON DELETE SET NULL,

    -- 试卷被删 → 作答记录不删，paper_id 置 NULL
    -- 理由同上：历史不能因为试卷删了就消失。
    CONSTRAINT fk_ar_paper
        FOREIGN KEY (paper_id) REFERENCES papers(id)
        ON DELETE SET NULL

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='全量作答记录';