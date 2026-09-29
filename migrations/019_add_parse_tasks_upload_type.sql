-- ============================================================
-- 文件：019_add_parse_tasks_upload_type.sql
-- 用途：parse_tasks 表增加 upload_type 字段
--
-- 【变更说明】
--   旧版本：parse_tasks 不区分教材/附属资料
--   新版本：新增 upload_type 列
--     - 'textbook'：教材
--     - 'supplement'：附属资料（默认值）
--
--   这个字段的作用：
--     worker 完成任务后，把 upload_type 传给 material_store.upsert()，
--     这样 materials 表就知道这份资料是教材还是附属资料。
-- ============================================================

ALTER TABLE parse_tasks
    ADD COLUMN upload_type VARCHAR(20) NOT NULL DEFAULT 'supplement'
        COMMENT '上传类型：textbook（教材）/ supplement（附属资料）'
        AFTER course_key;