-- ============================================================
-- 文件：016_create_chunk_chapter_map.sql
-- 用途：chunk 与章节的关联表
--
-- 【为什么需要这张表】
--   附属资料解析后切成 chunk，需要 LLM 判断每个 chunk 属于哪个章节。
--   分类结果存这里，后续出题时按章节检索 chunk 用。
-- ============================================================

CREATE TABLE IF NOT EXISTS chunk_chapter_map (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT
                    COMMENT '关联主键',

    chunk_id        VARCHAR(200) NOT NULL
                    COMMENT 'Chroma 中的 chunk id',

    chapter_id      INT NOT NULL
                    COMMENT '所属章节 id（指向 knowledge_points）',

    material_id     INT NOT NULL
                    COMMENT '来源资料 id',

    confidence      DECIMAL(3,2)
                    COMMENT 'LLM 分类置信度 0.00~1.00',

    is_confirmed    TINYINT(1) NOT NULL DEFAULT 0
                    COMMENT '是否经人工确认。0=待确认 1=已确认',

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '创建时间',

    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP
                    COMMENT '更新时间',

    UNIQUE KEY uk_ccm_chunk (chunk_id),
    KEY idx_ccm_chapter (chapter_id),
    KEY idx_ccm_material (material_id),
    KEY idx_ccm_confirmed (is_confirmed),

    CONSTRAINT fk_ccm_chapter
        FOREIGN KEY (chapter_id) REFERENCES knowledge_points(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_ccm_material
        FOREIGN KEY (material_id) REFERENCES materials(id)
        ON DELETE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='chunk-章节关联表';