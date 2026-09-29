-- ============================================================
-- 文件：000_init_users.sql
-- 用途：学生账号表
--
-- 【Q7 决策：学生可以自助注册】
--   所以这张表有 username 唯一约束，防止重复注册。
--   密码用 bcrypt 哈希（不是明文，也不是 MD5），
--   哈希后的字符串约 60 字符，所以用 VARCHAR(200) 留余量。
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id              INT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '学生主键',

    username        VARCHAR(50) NOT NULL
                    COMMENT '用户名。唯一',

    password_hash   VARCHAR(200) NOT NULL
                    COMMENT '密码哈希（bcrypt）。绝不存明文',

    display_name    VARCHAR(100)
                    COMMENT '显示名。没填就用 username',

    email           VARCHAR(200)
                    COMMENT '邮箱。可选',

    is_active       TINYINT(1) NOT NULL DEFAULT 1
                    COMMENT '是否启用。禁用账号用（软删除）',

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '注册时间',

    last_login_at   TIMESTAMP NULL
                    COMMENT '最近登录时间',

    -- 用户名唯一
    UNIQUE KEY uk_users_username (username),

    -- 按启用状态筛（管理员查"被禁用的账号"）
    KEY idx_users_active (is_active)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='学生账号表';