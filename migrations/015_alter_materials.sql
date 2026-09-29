-- ============================================================
-- 文件：015_alter_materials.sql
-- 用途：materials 表增加教材/附属资料区分 + 章节分类状态
--
-- 【变更说明】
--   旧版本：不区分教材和附属资料
--   新版本：
--     - upload_type: 'textbook'（教材）/ 'supplement'（附属资料）
--     - chapter_classified: 附属资料是否已完成章节分类
-- ============================================================

ALTER TABLE materials
    ADD COLUMN upload_type VARCHAR(20) NOT NULL DEFAULT 'textbook'
        COMMENT '上传类型：textbook（教材）/ supplement（附属资料）'
        AFTER kind,
    ADD COLUMN chapter_classified TINYINT(1) NOT NULL DEFAULT 0
        COMMENT '附属资料是否已完成章节分类。教材始终为 0'
        AFTER upload_type;

-- 按课程+类型快速查教材或附属资料
ALTER TABLE materials
    ADD KEY idx_materials_course_type (course_id, upload_type);