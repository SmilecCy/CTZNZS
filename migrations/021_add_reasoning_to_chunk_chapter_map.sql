-- ============================================================
-- 文件：021_add_reasoning_to_chunk_chapter_map.sql
-- 用途：给 chunk_chapter_map 表增加 reasoning 字段，
--       存储 LLM 分类时的推理说明。
-- ============================================================

ALTER TABLE chunk_chapter_map
    ADD COLUMN reasoning TEXT NULL
    COMMENT 'LLM 分类推理说明'
    AFTER confidence;