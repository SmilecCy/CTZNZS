-- ============================================================
-- 文件：001_init_courses.sql
-- 用途：课程、知识点、资料-课程关联、合并日志
--
-- 【为什么这是第一个】
--   课程是整个系统的"根"。题库、错题、试卷、预热任务全都挂在课程上。
--   所以建表顺序必须是：课程 → 资料 → 题库 → 其他。
--
-- 【与旧版本的区别】
--   旧版本课程写死在 config.py 的 COURSES 字典里。
--   新版本课程在数据库里，后台可以增删改。config.py 降级为种子数据。
-- ============================================================

-- ---------- 课程主表 ----------
CREATE TABLE IF NOT EXISTS courses (
    id              INT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '课程主键。所有引用课程的地方都用这个 id，不用名字',

    name            VARCHAR(100) NOT NULL
                    COMMENT '课程名（机器用）。例如"商法"。唯一',

    display_name    VARCHAR(100) NOT NULL
                    COMMENT '课程展示名（给人看）。通常和 name 一样',

    description     TEXT
                    COMMENT '课程描述',

    memory_strategy VARCHAR(200)
                    COMMENT '记忆策略说明（保留字段，当前不用）',

    question_focus  VARCHAR(200)
                    COMMENT '出题侧重说明，供提示词参考',

    is_active       TINYINT(1) NOT NULL DEFAULT 1
                    COMMENT '是否启用。删除课程用软删除（置 0），不真的删',

    merged_into     INT NULL
                    COMMENT '若本课程被合并，指向目标课程 id。NULL 表示没被合并',

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '创建时间',

    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP
                    COMMENT '更新时间',

    -- 课程名唯一：同名课程不允许建两个，否则出题时不知道该选哪个
    UNIQUE KEY uk_courses_name (name),

    -- 被合并的目标课程必须存在
    -- ON DELETE SET NULL：目标课程被删了，这个字段自动置 NULL，不留悬空引用
    CONSTRAINT fk_courses_merged_into
        FOREIGN KEY (merged_into) REFERENCES courses(id)
        ON DELETE SET NULL

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='课程主表';


-- ---------- 知识点表 ----------
-- parent_id 预留多级：现在只做一级（parent_id 永远 NULL），
-- 但表结构支持以后做"归责原则 → 过错推定"这种父子关系。
CREATE TABLE IF NOT EXISTS knowledge_points (
    id                  INT AUTO_INCREMENT PRIMARY KEY
                        COMMENT '知识点主键',

    course_id           INT NOT NULL
                        COMMENT '所属课程。知识点是课程级的',

    parent_id           INT NULL
                        COMMENT '父知识点 id。NULL 表示一级知识点。预留多级用',

    name                VARCHAR(200) NOT NULL
                        COMMENT '知识点名。例如"归责原则"',

    description         TEXT
                        COMMENT '知识点说明',

    source_material_id  INT NULL
                        COMMENT '这个知识点从哪份资料抽出来的。NULL 表示人工添加',

    sort_order          INT NOT NULL DEFAULT 0
                        COMMENT '排序权重。数字小的排前面',

    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                        COMMENT '创建时间',

    -- 同一课程下知识点名唯一
    -- 不同课程可以有同名知识点（不同课程的"归责原则"是两回事）
    UNIQUE KEY uk_kp_course_name (course_id, name),

    KEY idx_kp_course (course_id),
    KEY idx_kp_parent (parent_id),

    -- 课程被删 → 知识点跟着删（CASCADE）
    CONSTRAINT fk_kp_course
        FOREIGN KEY (course_id) REFERENCES courses(id)
        ON DELETE CASCADE,

    -- 父知识点被删 → 子知识点不删，parent_id 置 NULL
    -- 为什么不用 CASCADE：删父知识点不该把子知识点也删掉，
    -- 子知识点可能仍然有效，只是失去层级关系。
    CONSTRAINT fk_kp_parent
        FOREIGN KEY (parent_id) REFERENCES knowledge_points(id)
        ON DELETE SET NULL

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='知识点表（预留多级）';


-- ---------- 资料-课程关联表 ----------
-- 一份资料只能归属一门课，所以 material_id 唯一。
-- 一门课可以有多份资料，所以 course_id 不唯一。
CREATE TABLE IF NOT EXISTS material_course_map (
    id              INT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '关联主键',

    material_id     INT NOT NULL
                    COMMENT '资料 id（指向 materials 表）',

    course_id       INT NOT NULL
                    COMMENT '课程 id',

    confirmed_by    VARCHAR(100)
                    COMMENT '确认人。记录是谁把这门资料归到这门课的',

    confirmed_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '确认时间',

    -- 一份资料只能归一门课。防止"同一份资料被归到两门课"的歧义。
    -- 【注意】这里不设外键到 materials，因为 materials 表在 002 里才建。
    --        MySQL 不支持"引用还没建的表"。外键在 002 里补。
    UNIQUE KEY uk_mcm_material (material_id),

    KEY idx_mcm_course (course_id),

    CONSTRAINT fk_mcm_course
        FOREIGN KEY (course_id) REFERENCES courses(id)
        ON DELETE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='资料-课程关联表（一份资料只归一门课）';


-- ---------- 课程合并日志 ----------
-- 合并是不可逆操作，必须留痕。
CREATE TABLE IF NOT EXISTS course_merge_log (
    id              INT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '日志主键',

    from_course_id  INT NOT NULL
                    COMMENT '被合并的课程 id',

    to_course_id    INT NOT NULL
                    COMMENT '合并到的目标课程 id',

    merged_by       VARCHAR(100)
                    COMMENT '操作人',

    merged_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '合并时间',

    detail          TEXT
                    COMMENT '合并详情 JSON：迁移了多少题、去重了多少题等',

    KEY idx_cml_from (from_course_id),
    KEY idx_cml_to (to_course_id)

    -- 【为什么不设外键】
    -- 课程可能被彻底删除（虽然我们推荐软删除），
    -- 但日志要能留住。不能因为课程没了，合并记录就跟着消失——
    -- 那样就没法追溯"当初是谁把 A 合到 B 的"。

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='课程合并日志';