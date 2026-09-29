-- ============================================================
-- 文件：011_seed_admin.sql
-- 用途：插入初始管理员账号
--
-- 【初始密码】admin123
-- 【强制改密】must_change_password = 1，首次登录后必须改
--
-- 【为什么用 INSERT ... ON DUPLICATE KEY UPDATE】
--   这个脚本可能被重复执行（比如重跑 init_mysql.py）。
--   如果直接 INSERT，第二次跑会因为 username 唯一约束报错。
--   加 ON DUPLICATE KEY UPDATE 后，重复执行不会报错，
--   但也不会把已经改过的密码重置回去（只更新 display_name）。
--
-- 【bcrypt 哈希是怎么来的】
--   明文 "admin123" 用 bcrypt 加密后的结果。
--   每次加密结果都不一样（bcrypt 加随机盐），
--   这里预先算好一个，用于初始化。
--   登录时用 bcrypt.verify("admin123", 哈希) 校验。
-- ============================================================

INSERT INTO admin_users (username, password_hash, display_name, must_change_password)
VALUES (
    'admin',
    -- 明文是 admin123，bcrypt cost=12
    -- 【注意】这个哈希字符串不能换行，MySQL 会把换行当成字符串的一部分
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewKyZOA9Vv/Ox8Hy',
    '系统管理员',
    1
)
ON DUPLICATE KEY UPDATE
    -- 已存在就只更新显示名，不动密码和强制改密标记
    -- 为什么不动密码：用户可能已经改过密码了，
    -- 重跑脚本不该把人家改的密码重置回默认。
    display_name = VALUES(display_name);