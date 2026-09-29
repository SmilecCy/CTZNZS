-- ============================================================
-- 文件：020_v2.2_materials_md_and_cascade.sql
-- 用途：v2.2 架构补齐 — materials 表加 markdown_path、
--       textbook_course_id 生成列、以及四张关联表级联删除
--
-- 【变更说明】
--   1. materials.markdown_path：教材 PDF 转 MD 后的落盘路径
--   2. materials.textbook_course_id：生成列，保证每课程只有一份教材
--   3. wrong_questions / answer_records 的 question_bank FK
--      从 SET NULL 改为 CASCADE，支持学生硬删题目时级联清理
-- ============================================================

-- ============================================================
-- 一、materials 表加 markdown_path
-- ============================================================
ALTER TABLE materials
    ADD COLUMN markdown_path VARCHAR(500) NULL
        COMMENT '教材 MD 落盘路径（仅教材有值，附属资料为 NULL）'
        AFTER chapter_classified;

-- ============================================================
-- 二、materials 表加 textbook_course_id 生成列 + 唯一索引
--     textbook_course_id = IF(upload_type='textbook', course_id, NULL)
--     这样 UNIQUE 索引只对教材生效，附属资料不受限
-- ============================================================
ALTER TABLE materials
    ADD COLUMN textbook_course_id INT NULL
        GENERATED ALWAYS AS (
            CASE WHEN upload_type = 'textbook' THEN course_id ELSE NULL END
        ) STORED
        COMMENT '生成列：教材时=course_id，附属资料时=NULL。用于唯一约束'
        AFTER upload_type;

ALTER TABLE materials
    ADD UNIQUE KEY uk_materials_textbook_course (textbook_course_id);

-- ============================================================
-- 三、wrong_questions：question_bank FK 从 SET NULL 改为 CASCADE
--     【原因】v2.2 要求：学生硬删题库题目时，错题记录级联删除。
--     旧设计 SET NULL 是因为"题目废弃后仍可复习"，
--     但 v2.2 区分了"废弃"（改 status）和"硬删"（物理 DELETE），
--     废弃不会触发 FK，只有硬删才会，所以 CASCADE 是安全的。
-- ============================================================
ALTER TABLE wrong_questions
    DROP FOREIGN KEY fk_wq_question;

ALTER TABLE wrong_questions
    ADD CONSTRAINT fk_wq_question
        FOREIGN KEY (question_bank_id) REFERENCES question_bank(id)
        ON DELETE CASCADE;

-- ============================================================
-- 四、answer_records：question FK 从 SET NULL 改为 CASCADE
--     【原因】同上。学生硬删题目时，作答流水级联删除。
--     废弃（改 status='deprecated'）不触发 FK，作答记录保留。
-- ============================================================
ALTER TABLE answer_records
    DROP FOREIGN KEY fk_ar_question;

ALTER TABLE answer_records
    ADD CONSTRAINT fk_ar_question
        FOREIGN KEY (question_id) REFERENCES question_bank(id)
        ON DELETE CASCADE;