# -*- coding: utf-8 -*-
"""项目启动器 —— 统一入口。

用法::

    python app.py              交互式菜单
    python app.py dev           一键启动前后端（API + Web）★ 推荐
    python app.py api           单独启动 FastAPI 后端（http://localhost:5174）
    python app.py web           单独启动 React 前端开发服务器（http://localhost:5173）
    python app.py init          初始化 MySQL 数据库（建表 + 种子数据）
    python app.py model         下载向量模型到本地（解决 HuggingFace 网络问题）
    python app.py check         系统环境检查（Python / Node / MySQL / Redis）
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

# 项目根目录
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 加载 .env
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


# ==============================================================
# 工具函数
# ==============================================================

def _heading(title: str) -> None:
    """打印节标题。"""
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)
    print()


def _ok(msg: str) -> None:
    """打印成功消息。"""
    print(f"  [OK] {msg}")


def _warn(msg: str) -> None:
    """打印警告消息。"""
    print(f"  [WARN] {msg}")


def _fail(msg: str) -> None:
    """打印失败消息。"""
    print(f"  [FAIL] {msg}")


def _which(cmd: str) -> str | None:
    """检查命令是否在 PATH 中，返回路径或 None。"""
    return shutil.which(cmd)


def _python_exe() -> str:
    """返回应当使用的 Python 解释器路径。

    优先使用项目 .venv 中的 Python，确保依赖齐全。
    """
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


# ==============================================================
# 各子命令的实现
# ==============================================================

def cmd_api() -> None:
    """启动 FastAPI 后端。"""
    _heading("启动 FastAPI 后端服务")

    try:
        import uvicorn
    except ImportError:
        _fail("缺少 uvicorn，请先安装依赖：pip install -r requirements.txt")
        return

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "5174"))

    print(f"  地址：http://localhost:{port}")
    print(f"  文档：http://localhost:{port}/docs")
    print(f"  健康：http://localhost:{port}/health")
    print()
    print("  按 Ctrl+C 停止服务。")
    print()

    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=True,
        reload_dirs=[str(ROOT / "api"), str(ROOT / "app")],
        log_level="info",
    )


def cmd_web() -> None:
    """启动 React 前端开发服务器。"""
    _heading("启动 React 前端开发服务器")

    web_dir = ROOT / "web"
    if not (web_dir / "package.json").exists():
        _fail(f"找不到 {web_dir / 'package.json'}，请确认前端项目存在")
        return

    npm = _which("npm")
    if npm is None:
        _fail("未检测到 Node.js / npm，请先安装 Node.js：https://nodejs.org")
        return

    print("  安装依赖...")
    result = subprocess.run(
        [npm, "install"],
        cwd=str(web_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _fail(f"npm install 失败：\n{result.stderr}")
        return
    _ok("依赖安装完成")

    print()
    print("  启动 Vite 开发服务器...")
    print("  前端地址：http://localhost:5173")
    print("  按 Ctrl+C 停止。")
    print()

    # 前台运行，子进程继承当前终端的标准输入输出
    subprocess.run(
        [npm, "run", "dev"],
        cwd=str(web_dir),
    )


def cmd_dev() -> None:
    """一键启动前后端（后端 API + 前端开发服务器）。"""
    import time

    _heading("一键启动前后端")

    # -- 验证环境 --
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        _fail("缺少 uvicorn，请先安装依赖：pip install -r requirements.txt")
        return

    web_dir = ROOT / "web"
    if not (web_dir / "package.json").exists():
        _fail(f"找不到 {web_dir / 'package.json'}，请确认前端项目存在")
        return

    npm = _which("npm")
    if npm is None:
        _fail("未检测到 Node.js / npm，请先安装 Node.js：https://nodejs.org")
        return

    # -- 前端依赖 --
    print("  安装前端依赖...")
    result = subprocess.run(
        [npm, "install"],
        cwd=str(web_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _fail(f"npm install 失败：\n{result.stderr}")
        return
    _ok("前端依赖就绪")

    # -- 启动后端 --
    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = os.getenv("API_PORT", "5174")

    backend_proc = subprocess.Popen(
        [
            _python_exe(), "-m", "uvicorn", "api.main:app",
            "--host", api_host,
            "--port", api_port,
            "--reload",
            "--reload-dir", str(ROOT / "api"),
            "--reload-dir", str(ROOT / "app"),
        ],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    _ok(f"后端已启动  http://localhost:{api_port}")
    _ok(f"接口文档    http://localhost:{api_port}/docs")

    # 等后端启动完毕（轮询 /health）
    import urllib.request
    api_url = f"http://localhost:{api_port}/health"
    print(f"  等待后端就绪...")
    for _ in range(30):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(api_url, timeout=1)
            _ok("后端就绪")
            break
        except Exception:
            pass
    else:
        _warn("后端可能尚未就绪，继续启动前端...")

    # -- 启动前端 --
    frontend_proc = subprocess.Popen(
        [npm, "run", "dev"],
        cwd=str(web_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    _ok("前端已启动  http://localhost:5173")

    print()
    print("  ────────────────────────────────────────")
    print(f"  后端  http://localhost:{api_port}")
    print(f"  前端  http://localhost:5173")
    print(f"  文档  http://localhost:{api_port}/docs")
    print("  ────────────────────────────────────────")
    print()
    print("  按 Ctrl+C 停止所有服务。")
    print()

    # -- 等待退出 --
    procs = [backend_proc, frontend_proc]
    try:
        for proc in procs:
            proc.wait()
    except KeyboardInterrupt:
        print("\n  正在停止...")
        for proc in procs:
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        _ok("前后端已停止")


def cmd_init() -> None:
    """初始化 MySQL 数据库。"""
    _heading("初始化 MySQL 数据库")

    try:
        import pymysql
    except ImportError:
        _fail("缺少 pymysql，请先安装依赖：pip install -r requirements.txt")
        return

    from pymysql.constants import CLIENT

    migrations_dir = ROOT / "migrations"
    if not migrations_dir.exists():
        _fail(f"找不到迁移目录 {migrations_dir}")
        return

    # 建立连接
    try:
        conn = pymysql.connect(
            host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            port=int(os.getenv("MYSQL_PORT", "9999")),
            user=os.getenv("MYSQL_USER", "study_user"),
            password=os.getenv("MYSQL_PASSWORD", "study_pass"),
            database=os.getenv("MYSQL_DATABASE", "study_db"),
            charset="utf8mb4",
            autocommit=True,
            client_flag=CLIENT.MULTI_STATEMENTS,
        )
        _ok("MySQL 连接成功")
    except Exception as exc:
        _fail(f"MySQL 连接失败：{exc}")
        print()
        print("  请检查：")
        print("    1. MySQL 是否已启动")
        print("    2. .env 中的 MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD 是否正确")
        return

    # 按序执行 SQL 文件
    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        _fail(f"{migrations_dir} 下没有 SQL 文件")
        conn.close()
        return

    with conn.cursor() as cur:
        for sql_file in sql_files:
            print(f"  执行：{sql_file.name}")
            content = sql_file.read_text(encoding="utf-8")
            try:
                cur.execute(content)
                _ok(f"{sql_file.name} 完成")
            except Exception as exc:
                _fail(f"{sql_file.name} 执行失败：{exc}")
                conn.close()
                return

    conn.close()
    print()
    _ok("数据库初始化完成")


def cmd_model() -> None:
    """下载向量模型到本地。"""
    _heading("下载向量模型")

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        _fail("缺少 huggingface_hub，请先安装依赖：pip install -r requirements.txt")
        return

    from app.config import EMBEDDING_MODEL_ID, LOCAL_MODEL_DIR, has_local_model

    if has_local_model():
        _ok(f"模型已存在：{LOCAL_MODEL_DIR}")
        print(f"  如需重新下载，请删除该目录后重试。")
        return

    print(f"  模型：{EMBEDDING_MODEL_ID}")
    print(f"  目标：{LOCAL_MODEL_DIR}")
    print()

    sources: list[tuple[str, str]] = [
        ("https://hf-mirror.com", "国内镜像 hf-mirror.com"),
        ("https://huggingface.co", "官方源 huggingface.co"),
    ]

    for endpoint, label in sources:
        print(f"  尝试：{label}（{endpoint}）")
        try:
            code = (
                "from huggingface_hub import snapshot_download\n"
                f"snapshot_download(repo_id={EMBEDDING_MODEL_ID!r}, "
                f"local_dir={str(LOCAL_MODEL_DIR)!r})\n"
            )
            env = {**os.environ, "HF_ENDPOINT": endpoint}
            result = subprocess.run(
                [_python_exe(), "-c", code],
                env=env,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                _ok("下载成功")
                return
            print(f"    失败：{result.stderr.strip().split(chr(10))[-1]}")
        except Exception as exc:
            print(f"    异常：{exc}")

    print()
    _fail("所有来源均下载失败")
    print()
    print("  备用方案：用浏览器打开镜像站，手动下载所有文件")
    print(f"  https://hf-mirror.com/{EMBEDDING_MODEL_ID}/tree/main")
    print(f"  下载到：{LOCAL_MODEL_DIR}")


def cmd_check() -> None:
    """系统环境检查。"""
    _heading("系统环境检查")

    results: list[tuple[str, bool, str]] = []

    # Python
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    results.append(("Python", True, version))

    # pip packages
    try:
        import fastapi
        results.append(("FastAPI", True, fastapi.__version__))
    except ImportError:
        results.append(("FastAPI", False, "未安装"))

    try:
        import pymysql
        results.append(("PyMySQL", True, pymysql.__version__))
    except ImportError:
        results.append(("PyMySQL", False, "未安装"))

    try:
        import redis
        results.append(("redis-py", True, redis.__version__))
    except ImportError:
        results.append(("redis-py", False, "未安装"))

    # Node.js
    node = _which("node")
    if node:
        try:
            r = subprocess.run([node, "--version"], capture_output=True, text=True)
            results.append(("Node.js", True, r.stdout.strip()))
        except Exception:
            results.append(("Node.js", False, "无法获取版本"))
    else:
        results.append(("Node.js", False, "未安装"))

    # npm
    npm = _which("npm")
    if npm:
        try:
            r = subprocess.run([npm, "--version"], capture_output=True, text=True)
            results.append(("npm", True, r.stdout.strip()))
        except Exception:
            results.append(("npm", False, "无法获取版本"))
    else:
        results.append(("npm", False, "未安装"))

    # MySQL 连接
    try:
        import pymysql
        conn = pymysql.connect(
            host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            port=int(os.getenv("MYSQL_PORT", "9999")),
            user=os.getenv("MYSQL_USER", "study_user"),
            password=os.getenv("MYSQL_PASSWORD", "study_pass"),
            database=os.getenv("MYSQL_DATABASE", "study_db"),
            connect_timeout=3,
        )
        conn.close()
        results.append(("MySQL", True, f"{os.getenv('MYSQL_HOST', '127.0.0.1')}:{os.getenv('MYSQL_PORT', '9999')}"))
    except ImportError:
        results.append(("MySQL", False, "PyMySQL 未安装"))
    except Exception as exc:
        results.append(("MySQL", False, str(exc)))

    # Redis 连接
    try:
        import redis
        r = redis.Redis(
            host=os.getenv("REDIS_HOST", "127.0.0.1"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD", "") or None,
            socket_connect_timeout=3,
        )
        r.ping()
        r.close()
        results.append(("Redis", True, f"{os.getenv('REDIS_HOST', '127.0.0.1')}:{os.getenv('REDIS_PORT', '6379')}"))
    except ImportError:
        results.append(("Redis", False, "redis-py 未安装"))
    except Exception as exc:
        results.append(("Redis", False, str(exc)))

    # 模型文件
    from app.config import LOCAL_MODEL_DIR, has_local_model
    if has_local_model():
        results.append(("向量模型", True, str(LOCAL_MODEL_DIR)))
    else:
        results.append(("向量模型", False, f"未下载（目标：{LOCAL_MODEL_DIR}）"))

    # 打印结果
    print()
    all_ok = True
    for name, ok, detail in results:
        mark = "[OK]" if ok else "[FAIL]"
        if not ok:
            all_ok = False
        print(f"  {mark:8s} {name:16s} {detail}")
    print()

    if all_ok:
        _ok("所有检查通过")
    else:
        _warn("部分检查未通过，请根据上面的 [FAIL] 项排查")


# ==============================================================
# 交互式菜单
# ==============================================================

_MENU = r"""                                                
       ██████╗  █████╗ ██╗   ██╗████████╗██╗   ██╗██████╗ ██╗   ██╗
       ██╔══██╗██╔══██╗██║   ██║╚══██╔══╝██║   ██║██╔══██╗╚██╗ ██╔╝
       ██████╔╝███████║████████║   ██║   ██║   ██║██║  ██║ ╚████╔╝ 
       ██╔══██╗██╔══██║██╔═══██║   ██║   ██║   ██║██║  ██║  ╚██╔╝  
       ██║  ██║██║  ██║██║   ██║   ██║   ╚██████╔╝██████╔╝   ██║   
       ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝   ╚═╝   ╚═╝    ╚═════╝ ╚═════╝    ╚═╝   
                                                                     
                思政+法学 双课程 AI 辅助学习系统
"""

_MENU_OPTIONS: list[tuple[str, str, Callable[[], None]]] = [
    ("dev",   "一键启动前后端（API + Web）                         ★ 推荐", cmd_dev),
    ("api",   "单独启动 FastAPI 后端服务    http://localhost:5174", cmd_api),
    ("web",   "单独启动 React 前端开发服务器 http://localhost:5173", cmd_web),
    ("init",  "初始化 MySQL 数据库（建表 + 种子数据）",             cmd_init),
    ("model", "下载向量模型到本地（BGE-Small-Zh）",                cmd_model),
    ("check", "系统环境检查（Python / Node / MySQL / Redis）",     cmd_check),
]

_MENU_MAP: dict[str, Callable[[], None]] = {
    key: func for key, _, func in _MENU_OPTIONS
}

_MENU_TEXT = "\n".join(
    f"    [{key:5s}]  {desc}" for key, desc, _ in _MENU_OPTIONS
)


def _print_banner() -> None:
    """打印欢迎横幅与菜单。"""
    print(_MENU)
    print(_MENU_TEXT)
    print()
    print("    输入命令（api / web / init / model / check）或 q 退出。")
    print()


def main() -> None:
    """项目启动器主函数。"""
    args = sys.argv[1:]

    # 有命令行参数 → 直接执行子命令
    if args:
        cmd = args[0].lower()
        func = _MENU_MAP.get(cmd)
        if func is None:
            print(f"未知命令：{cmd}")
            print(f"可用命令：{', '.join(_MENU_MAP)}")
            sys.exit(1)
        func()
        return

    # 无参数 → 交互式菜单
    _print_banner()
    while True:
        try:
            choice = input("  >>> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice in ("q", "quit", "exit", ""):
            break

        func = _MENU_MAP.get(choice)
        if func is None:
            print(f"  未知命令：{choice}，输入 api / web / init / model / check 或 q 退出。")
            continue

        try:
            func()
        except KeyboardInterrupt:
            print("\n  已中断。")
        except Exception as exc:
            _fail(f"执行出错：{exc}")
        finally:
            print()
            print("─" * 60)
            print("  输入下一个命令（或 q 退出）：")


if __name__ == "__main__":
    main()