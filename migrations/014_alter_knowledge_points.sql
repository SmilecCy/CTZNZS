-- ============================================================
-- 文件：014_alter_knowledge_points.sql
-- 用途：knowledge_points 表增加 chapter/knowledge 两级结构字段
--
-- 【变更说明】
--   旧版本：知识点是平的，parent_id 预留但未启用
--   新版本：
--     - node_type: 'chapter'（章节） / 'knowledge'（知识点）
--     - summary: 章节摘要（LLM 抽取后写入）
--     - 新增索引 idx_kp_course_type
-- ============================================================

ALTER TABLE knowledge_points
    ADD COLUMN node_type VARCHAR(20) NOT NULL DEFAULT 'knowledge'
        COMMENT '节点类型：chapter（章节）/ knowledge（知识点）'
        AFTER course_id,
    ADD COLUMN summary TEXT
        COMMENT '章节摘要（LLM 生成，仅 chapter 节点有值）'
        AFTER description;

-- 将现有数据标记为 'knowledge'（默认值已处理）

-- 新增联合索引：按课程+类型快速查章节/知识点
ALTER TABLE knowledge_points
    ADD KEY idx_kp_course_type (course_id, node_type);