-- ============================================================
-- 文件：013_init_parse_tasks.sql
-- 用途：资料解析任务表
--
-- 【为什么需要这张表】
--   上传资料后，M0 解析可能要几十秒（PDF 抽取、OCR、向量化）。
--   如果同步等待，用户界面会卡住。
--
--   所以我们改成异步：
--     1. 上传后立即写一条 parse_task（status=pending）
--     2. 后端起一个后台线程跑解析
--     3. 前端轮询任务状态
--     4. 解析完成 → status=done
--
-- 【为什么不用现有表】
--   和 warmup_jobs 语义不同：
--     warmup_jobs：一次预热任务，涉及"生成 N 道题"
--     parse_tasks：一份资料的解析任务，涉及"解析 + 切分 + 索引"
--   分开更清晰，也方便后续扩展。
-- ============================================================

CREATE TABLE IF NOT EXISTS parse_tasks (
    id              INT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '任务主键',

    source_file     VARCHAR(500) NOT NULL
                    COMMENT '文件名（含扩展名）',

    file_path       VARCHAR(1000) NOT NULL
                    COMMENT '文件在服务器上的完整路径',

    course_key      VARCHAR(100) NULL
                    COMMENT '课程 key（过渡期用），NULL 表示未指定',

    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    COMMENT '状态：pending（待执行）/ running（解析中）/ done（成功）/ failed（失败）',

    progress        INT NOT NULL DEFAULT 0
                    COMMENT '进度百分比 0~100',

    stage           VARCHAR(50)
                    COMMENT '当前阶段：解析 / 切分 / 索引',

    page_count      INT DEFAULT 0
                    COMMENT '解析出的页数',

    chunk_count     INT DEFAULT 0
                    COMMENT '切分出的 chunk 数',

    ocr_used        TINYINT(1) NOT NULL DEFAULT 0
                    COMMENT '是否走了 OCR 通道',

    warnings        TEXT
                    COMMENT '解析过程的警告（JSON 数组）',

    error           VARCHAR(1000)
                    COMMENT '失败原因',

    started_at      TIMESTAMP NULL
                    COMMENT '开始执行时间',

    finished_at     TIMESTAMP NULL
                    COMMENT '完成时间',

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '创建时间',

    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP
                    COMMENT '更新时间',

    -- 按状态筛选（"有多少任务还在跑"）
    KEY idx_status (status),
    -- 按文件名查
    KEY idx_source_file (source_file),
    -- 按时间排序
    KEY idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='资料解析任务表';