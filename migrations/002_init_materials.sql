-- ============================================================
-- 文件：002_init_materials.sql
-- 用途：资料表（含 LLM 识别字段）
--
-- 【为什么资料表这么重要】
--   整个系统的知识来源就是资料。资料上传后：
--   1. M0 解析：抽出文本、切分、向量化
--   2. LLM 识别：判断它属于哪门课、有哪些知识点
--   3. 人工确认：确认或修正识别结果
--   4. 归属入库：正式挂到某门课程下
-- ============================================================

CREATE TABLE IF NOT EXISTS materials (
    id                          INT AUTO_INCREMENT PRIMARY KEY
                                COMMENT '资料主键',

    source_file                 VARCHAR(500) NOT NULL
                                COMMENT '原始文件名（含扩展名）。唯一',

    course_id                   INT NULL
                                COMMENT '正式归属的课程 id。NULL 表示还没确认归属',

    kind                        VARCHAR(20) NOT NULL
                                COMMENT '文件类型：pdf / docx / image / text',

    chunk_count                 INT NOT NULL DEFAULT 0
                                COMMENT '切分出的 chunk 数',

    page_count                  INT NOT NULL DEFAULT 0
                                COMMENT '页数',

    ocr_used                    TINYINT(1) NOT NULL DEFAULT 0
                                COMMENT '是否走了 OCR 通道。扫描件才会走',

    -- ---------- LLM 识别字段 ----------
    detected_course_name        VARCHAR(100)
                                COMMENT 'LLM 建议的课程名',

    detected_knowledge_points   TEXT
                                COMMENT 'LLM 建议的知识点。JSON 数组字符串',

    detection_confidence        DECIMAL(3,2)
                                COMMENT 'LLM 识别的置信度。0.00~1.00',

    detection_reasoning         TEXT
                                COMMENT 'LLM 的判断理由，供人工参考',

    detection_status            VARCHAR(20) NOT NULL DEFAULT 'pending'
                                COMMENT '识别状态：pending / suggested / confirmed / rejected',

    detection_at                TIMESTAMP NULL
                                COMMENT '识别时间',

    -- ---------- 时间 ----------
    uploaded_at                 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                                COMMENT '上传时间',

    parsed_at                   TIMESTAMP NULL
                                COMMENT '解析完成时间',

    updated_at                  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP
                                COMMENT '更新时间',

    -- 文件名唯一：同一份文件不重复上传
    UNIQUE KEY uk_materials_file (source_file),

    KEY idx_materials_course (course_id),
    KEY idx_materials_status (detection_status),

    -- 课程被删 → 资料不删，course_id 置 NULL
    -- 为什么不用 CASCADE：资料是用户上传的原始文件，很宝贵。
    -- 删课程不该把资料也删掉，用户可能想重新归类到别的课。
    CONSTRAINT fk_materials_course
        FOREIGN KEY (course_id) REFERENCES courses(id)
        ON DELETE SET NULL

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='资料表';


-- ---------- 补 001 里没设的外键 ----------
-- 001 里 material_course_map 引用 materials，但那时 materials 还没建。
-- 现在 materials 建好了，把外键补上。
--
-- 【为什么用存储过程】
--   MySQL 没有 "ADD CONSTRAINT IF NOT EXISTS" 语法。
--   如果外键已存在，直接 ALTER 会报错。
--   用 INFORMATION_SCHEMA 先查一下，就不怕重复执行。
DROP PROCEDURE IF EXISTS add_mcm_material_fk;

DELIMITER $$
CREATE PROCEDURE add_mcm_material_fk()
BEGIN
    -- 查一下这个外键是不是已经存在了
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'material_course_map'
          AND CONSTRAINT_NAME = 'fk_mcm_material'
    ) THEN
        -- 不存在才加
        ALTER TABLE material_course_map
            ADD CONSTRAINT fk_mcm_material
            FOREIGN KEY (material_id) REFERENCES materials(id)
            ON DELETE CASCADE;
    END IF;
END$$
DELIMITER ;

CALL add_mcm_material_fk();
DROP PROCEDURE add_mcm_material_fk;