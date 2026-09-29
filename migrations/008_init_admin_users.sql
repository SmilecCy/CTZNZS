-- ============================================================
-- 文件：008_init_admin_users.sql
-- 用途：管理员账号表
--
-- 【与 users 表的区别】
--   users：学生表。可以自助注册。
--   admin_users：管理员表。不能自助注册，只能由初始脚本
--                或已有管理员创建。
--   为什么不合成一张表加个 role 字段：
--     1. 权限模型完全独立——学生只能看自己的数据，管理员能看全部。
--        分开表可以从物理上隔离，避免"学生把自己改成管理员"这类漏洞。
--     2. 管理员需要"强制改密"标记，学生不需要。
-- ============================================================

CREATE TABLE IF NOT EXISTS admin_users (
    id                  INT AUTO_INCREMENT PRIMARY KEY
                    COMMENT '管理员主键',

    username            VARCHAR(50) NOT NULL
                    COMMENT '用户名。唯一',

    password_hash       VARCHAR(200) NOT NULL
                    COMMENT '密码哈希（bcrypt）',

    display_name        VARCHAR(100)
                    COMMENT '显示名',

    is_active           TINYINT(1) NOT NULL DEFAULT 1
                    COMMENT '是否启用',

    must_change_password TINYINT(1) NOT NULL DEFAULT 1
                    COMMENT '是否强制改密。初始账号为 1，首次登录后改',

    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    COMMENT '创建时间',

    last_login_at       TIMESTAMP NULL
                    COMMENT '最近登录时间',

    UNIQUE KEY uk_admin_username (username)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='管理员账号表';