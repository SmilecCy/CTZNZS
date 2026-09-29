# -*- coding: utf-8 -*-
"""MySQL 建表脚本：按顺序执行 migrations/ 下的所有 SQL 文件。

用法（在项目根目录执行）::

    python scripts/init_mysql.py

【为什么单独写一个脚本，而不是用 docker-entrypoint-initdb.d】

    Docker 官方镜像支持把 SQL 挂载到 /docker-entrypoint-initdb.d/ 自动执行，
    但那个机制**只在容器第一次启动时生效**。这意味着：
      - 改了 SQL 文件想重跑，得先删容器和数据卷
      - 开发阶段反复改表结构会很痛苦

    自己写脚本随时可跑，SQL 改了直接重跑，重复执行也安全
    （所有 CREATE TABLE 都带 IF NOT EXISTS）。

【执行顺序为什么重要】

    文件按数字前缀排序执行。courses 必须最先建，因为其他表都引用它。
    这是硬约束，不是约定。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 把项目根目录加入 sys.path，这样才能 import app.config
# 为什么需要这行：脚本在 scripts/ 目录下，直接运行的话
# Python 只会把 scripts/ 加入 sys.path，找不到 app 包。
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 在 import 任何 app 模块之前加载 .env
# 因为 app.config 在导入时就会读环境变量，晚了就读不到。
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import pymysql  # noqa: E402
from pymysql.constants import CLIENT  # noqa: E402


# SQL 文件所在目录
MIGRATIONS_DIR = ROOT / "migrations"


def _connect() -> pymysql.connections.Connection:
    """建立到 MySQL 的连接。

    【为什么用 pymysql 而不是 mysql-connector-python】
    pymysql 是纯 Python 实现，装起来不需要编译。
    mysql-connector 在某些环境下要装 MySQL 客户端库，麻烦。
    """
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "9999")),
        user=os.getenv("MYSQL_USER", "study_user"),
        password=os.getenv("MYSQL_PASSWORD", "study_pass"),
        database=os.getenv("MYSQL_DATABASE", "study_db"),
        charset="utf8mb4",
        # autocommit=True：每个 SQL 执行完立即提交。
        # 建表脚本不需要事务，一条条执行更直观。
        autocommit=True,
        # 支持一次执行多条 SQL（用分号分隔）。
        # 【为什么需要】SQL 文件里有 DELIMITER 段和存储过程，
        # 默认一次只能执行一条语句。
        client_flag=CLIENT.MULTI_STATEMENTS,
    )


def _split_sql_statements(content: str) -> list[str]:
    """把 SQL 文件内容拆成一条条可执行的语句。

    【为什么不能简单地 split(';')】

        MySQL 的存储过程、触发器里也有分号，直接 split 会把
        CREATE PROCEDURE 切成两半。

        这个函数处理 DELIMITER 语法：
            DELIMITER $$
            CREATE PROCEDURE ... $$
            DELIMITER ;

        遇到 DELIMITER 切换分隔符，用新分隔符切。

    Args:
        content: SQL 文件全文。

    Returns:
        可执行语句列表。空行与注释块会被过滤掉。
    """
    statements: list[str] = []
    delimiter = ";"          # 当前分隔符，默认分号
    buffer: list[str] = []   # 累积当前语句

    for raw_line in content.splitlines():
        line = raw_line.rstrip()

        # 跳过纯注释行（-- 开头）和空行
        # 【为什么跳过】这些行单独执行会报语法错误，
        # 但它们是有用的文档，不该删。
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            # 注释行可以保留在语句里，MySQL 会忽略。
            # 但如果当前 buffer 是空的，注释行就没必要加进去。
            if buffer:
                buffer.append(line)
            continue

        # 检测 DELIMITER 切换
        if stripped.upper().startswith("DELIMITER "):
            new_delim = stripped.split(None, 1)[1].strip()
            delimiter = new_delim
            continue

        buffer.append(line)

        # 检查当前累积的内容是否以分隔符结尾
        if stripped.endswith(delimiter):
            statement = "\n".join(buffer).strip()
            # 去掉末尾的分隔符本身
            if statement.endswith(delimiter):
                statement = statement[: -len(delimiter)].rstrip()
            if statement:
                statements.append(statement)
            buffer = []

    # 处理最后一条没有分隔符结尾的语句
    if buffer:
        statement = "\n".join(buffer).strip()
        if statement:
            statements.append(statement)

    return statements


def _run_file(conn: pymysql.connections.Connection, path: Path) -> None:
    """执行一个 SQL 文件。

    Args:
        conn: MySQL 连接。
        path: SQL 文件路径。

    Raises:
        RuntimeError: SQL 执行失败时抛出，带上文件名和原始错误。
    """
    content = path.read_text(encoding="utf-8")
    statements = _split_sql_statements(content)

    with conn.cursor() as cursor:
        for stmt in statements:
            try:
                cursor.execute(stmt)
            except pymysql.err.MySQLError as exc:
                # 【为什么不用 cursor.executemany 或 executescript】
                # pymysql 没有 executescript（那是 sqlite3 的 API）。
                # 而且我们需要逐条执行，这样出错时能精确定位是哪一句。
                raise RuntimeError(
                    f"{path.name} 执行失败：\n"
                    f"  错误：{exc}\n"
                    f"  语句（前 200 字）：{stmt[:200]}"
                ) from exc


def main() -> int:
    """入口：连接 MySQL，按文件名顺序执行 migrations/ 下的所有 .sql 文件。"""
    print("=" * 60)
    print("MySQL 建表脚本")
    print("=" * 60)

    # 检查 migrations 目录
    if not MIGRATIONS_DIR.is_dir():
        print(f"错误：找不到 migrations 目录：{MIGRATIONS_DIR}")
        print("请先在项目根目录创建 migrations/ 目录，并把 SQL 文件放进去。")
        return 1

    # 收集所有 SQL 文件，按文件名排序
    # sorted 保证 001 在 002 前面，这是执行顺序的关键。
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        print(f"错误：{MIGRATIONS_DIR} 下没有 .sql 文件")
        return 1

    # 读连接信息（用于打印）
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "9999")
    user = os.getenv("MYSQL_USER", "study_user")
    database = os.getenv("MYSQL_DATABASE", "study_db")
    print(f"连接：{user}@{host}:{port}/{database}")
    print(f"共 {len(sql_files)} 个 SQL 文件\n")

    # 建立连接
    try:
        conn = _connect()
    except pymysql.err.MySQLError as exc:
        print(f"错误：连接 MySQL 失败\n  {exc}\n")
        print("排查建议：")
        print("  1. 确认 Docker 容器已启动：docker compose ps")
        print("  2. 确认 .env 里的 MYSQL_PORT 和 docker-compose.yml 的端口一致")
        print("  3. 确认 MySQL 已经变成 healthy 状态（首次启动要等十几秒）")
        return 1

    # 逐个执行
    try:
        for idx, sql_file in enumerate(sql_files, start=1):
            print(f"[{idx}/{len(sql_files)}] 执行 {sql_file.name} ... ", end="", flush=True)
            try:
                _run_file(conn, sql_file)
                print("OK")
            except RuntimeError as exc:
                print("失败")
                print(f"\n{exc}\n")
                return 1
    finally:
        conn.close()

    print()
    print("=" * 60)
    print(f"全部完成，共 {len(sql_files)} 个文件")
    print("=" * 60)
    print("\n验证：")
    print("  docker exec -it study_mysql mysql -ustudy_user -pstudy_pass study_db -e 'SHOW TABLES;'")
    return 0


if __name__ == "__main__":
    sys.exit(main())