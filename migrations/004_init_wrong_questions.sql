-- ============================================================
-- 文件：004_init_wrong_questions.sql
-- 用途：错题集
--
-- 【核心设计：同题去重】
--   同一道题错多次，只保留一条记录，累加 wrong_count。
--   为什么：错题集的价值在于"哪些知识点我还没拿下"，
--   同一道题出现五遍只会把清单撑爆、看不出真正的问题。
--
-- 【与 answer_records 的关系】
--   answer_records：全量流水账（答对答错都记）
--   wrong_questions：学习状态（错次、掌握度、复习排期）
--   两者并存（Q6 决策 A）。
-- ============================================================

CREATE TABLE IF NOT EXISTS wrong_questions (
    id                INT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '错题主键',

    user_id           INT NOT NULL
                    COMMENT '学生 id',

    course_id         INT NOT NULL
                    COMMENT '课程 id',

    question_bank_id  INT NULL
                    COMMENT '题库里的题目 id。用于去重（同题只留一条）',

    knowledge_point   VARCHAR(200)
                    COMMENT '知识点（冗余，避免每次 JOIN）',

    question_type     VARCHAR(20)
                    COMMENT '题型（冗余）',

    question_json     TEXT NOT NULL
                    COMMENT '题目快照 JSON。存快照而不是只存 id，因为题库可能变化',

    user_answer       TEXT
                    COMMENT '学生最近一次的作答',

    error_tags        TEXT
                    COMMENT '错误原因标签。JSON 数组字符串',

    review_count      INT NOT NULL DEFAULT 0
                    COMMENT '复习了几次',

    correct_count     INT NOT NULL DEFAULT 0
                    COMMENT '复习时答对了几次',

    wrong_count       INT NOT NULL DEFAULT 1
                    COMMENT '错了几次。同题再错只累加这个数',

    last_result       VARCHAR(10)
                    COMMENT '上次复习结果：right / wrong / NULL（没判出对错）',

    last_wrong_at     TIMESTAMP NULL
                    COMMENT '最近一次答错时间',

    last_reviewed     TIMESTAMP NULL
                    COMMENT '最近一次复习时间',

    last_mastered_at  TIMESTAMP NULL
                    COMMENT '最近一次标记为已掌握的时间',

    mastery_status    VARCHAR(20) NOT NULL DEFAULT 'unmastered'
                    COMMENT '掌握状态：unmastered（待复习）/ mastered（已掌握）',

    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '收录时间',

    -- 【关键约束】同一学生、同一课程、同一道题只能有一条错题记录
    -- 这是"同题去重"的实现基础。没有它，同一道题错五次会有五条记录。
    UNIQUE KEY uk_wq_user_question (user_id, course_id, question_bank_id),

    KEY idx_wq_user_course (user_id, course_id, mastery_status),
    KEY idx_wq_question (question_bank_id),

    -- 学生被删 → 错题跟着删
    CONSTRAINT fk_wq_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,

    -- 课程被删 → 错题跟着删
    CONSTRAINT fk_wq_course
        FOREIGN KEY (course_id) REFERENCES courses(id)
        ON DELETE CASCADE,

    -- 题目被删 → 错题不删，question_bank_id 置 NULL
    -- 为什么：错题里存了 question_json 快照，题目没了还能看到原题。
    -- 这是"题目被废弃，学生仍能复习"的保障。
    CONSTRAINT fk_wq_question
        FOREIGN KEY (question_bank_id) REFERENCES question_bank(id)
        ON DELETE SET NULL

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='错题集';