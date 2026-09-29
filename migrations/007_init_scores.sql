-- ============================================================
-- 文件：007_init_scores.sql
-- 用途：成绩表
--
-- 【什么时候写这张表】
--   只有"交卷"才写。自由练习不写——自由练习没有"满分"概念，
--   写进去反而污染成绩统计。
--
-- 【为什么 paper_id 允许 NULL】
--   允许"自由练习交卷"这个场景：学生自己挑几道题做完，
--   也可以算一次成绩。这种没有试卷 id。
-- ============================================================

CREATE TABLE IF NOT EXISTS scores (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '成绩主键。用 BIGINT 因为会一直增长',

    user_id         INT NOT NULL
                    COMMENT '学生 id',

    course_id       INT NOT NULL
                    COMMENT '课程 id',

    paper_id        INT NULL
                    COMMENT '试卷 id。NULL 表示自由练习的成绩汇总',

    total_score     DECIMAL(6,2) NOT NULL DEFAULT 0.00
                    COMMENT '得分',

    full_score      DECIMAL(6,2) NOT NULL DEFAULT 0.00
                    COMMENT '满分',

    correct_count   INT NOT NULL DEFAULT 0
                    COMMENT '答对题数',

    total_count     INT NOT NULL DEFAULT 0
                    COMMENT '总题数',

    submitted_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '交卷时间',

    -- 索引：
    --   idx_scores_user_course  查"某学生某课程的成绩单"
    --   idx_scores_paper        查"某张试卷所有人的成绩"
    --   idx_scores_time         按时间排（最近的成绩单）
    KEY idx_scores_user_course (user_id, course_id),
    KEY idx_scores_paper (paper_id),
    KEY idx_scores_time (submitted_at),

    CONSTRAINT fk_scores_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_scores_course
        FOREIGN KEY (course_id) REFERENCES courses(id)
        ON DELETE CASCADE,

    -- 试卷被删 → 成绩不删，paper_id 置 NULL
    -- 成绩是学生历史，不能因为试卷删了就消失。
    CONSTRAINT fk_scores_paper
        FOREIGN KEY (paper_id) REFERENCES papers(id)
        ON DELETE SET NULL

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='成绩表';