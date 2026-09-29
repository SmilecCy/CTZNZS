# -*- coding: utf-8 -*-
"""全局配置：路径常量、课程种子数据、切分与检索参数、数据库与缓存配置。

本模块是整个项目的"单一事实来源"（single source of truth）。
任何模块都不应硬编码课程名、知识点或路径，一律从此处导入。

【v4.0 重要变更】
    课程真相源从"代码里的 COURSES 字典"迁移到了"MySQL 的 courses 表"。
    COURSES 字典降级为**种子数据**，只在两处允许使用：
      1. 首次建库时插入种子课程（migrations 脚本会引用它）
      2. 提示词路由（m2_tort_short_answer / m2_xigai_short_answer 的模板选择）
    新代码里**不得**再出现 COURSES["tort"] 这种访问。
    课程一律通过 course_id 从数据库查。

【.env 加载时机】
    load_dotenv 必须放在文件最顶部、其他 import 之前执行。
    原因：本模块在导入时就会读环境变量，晚了就读不到 .env 里的值。
"""

from __future__ import annotations

# ==============================================================
# 最优先：加载 .env
# ==============================================================
# 这一行必须在任何 os.getenv 之前执行。
# 路径用绝对路径显式指定，因为不同启动方式（脚本 / uvicorn / pytest）
# 的工作目录可能不同，相对路径会读错文件。
from pathlib import Path as _Path

from dotenv import load_dotenv

# BASE_DIR 先算出来，后面所有路径都基于它
BASE_DIR = _Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ==============================================================
# 常规 import
# ==============================================================
import os
from typing import Final, TypedDict


# ---------------------------------------------------------------
# 一、路径常量
# ---------------------------------------------------------------
APP_DIR: Final[_Path] = _Path(__file__).resolve().parent           # app 包
DATA_DIR: Final[_Path] = BASE_DIR / "data"
PROMPTS_DIR: Final[_Path] = APP_DIR / "prompts"                    # 提示词库

UPLOAD_DIR: Final[_Path] = DATA_DIR / "uploads"      # 原始资料落盘区
VECTOR_DIR: Final[_Path] = DATA_DIR / "vector"       # FAISS 向量库持久化目录
MARKDOWN_DIR: Final[_Path] = DATA_DIR / "markdown"   # PDF 转 Markdown 落盘区

# 首次导入即确保数据目录存在，避免下游模块重复 mkdir
for _d in (DATA_DIR, UPLOAD_DIR, VECTOR_DIR, MARKDOWN_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------
# 二、课程种子数据（已降级）
# ---------------------------------------------------------------
class Course(TypedDict):
    """一门课程的种子元数据。

    【注意】这只是"种子"，不是"真相源"。
        真相源是 MySQL 的 courses 表。
        这个 TypedDict 用于描述种子数据的结构，
        以及让提示词路由知道有哪些"模板课程"。
    """

    key: str            # 稳定标识符。写入数据库时转成 name 字段
    name: str           # 展示名
    knowledge_points: list[str]
    question_focus: str  # 出题侧重（供提示词模板选择）
    memory_strategy: str  # 记忆策略（保留字段，当前不用）


# 【重要】这个字典的用途已降级：
#   - 首次建库时，migrations 脚本会读它来插入种子课程
#   - 提示词路由读它来选模板（tort → m2_tort_short_answer）
# 除此之外，新代码不得引用它。
COURSES: Final[dict[str, Course]] = {
    "tort": {
        "key": "tort",
        "name": "商法",
        "knowledge_points": [
            "归责原则",
            "构成要件",
            "过错推定",
            "无过错责任",
            "公平责任",
            "抗辩事由",
            "责任主体",
            "损害赔偿",
            "数人侵权",
            "诉讼时效",
        ],
        "question_focus": "构成要件辨析、归责原则判断、案例适用",
        "memory_strategy": "知识层级（归责原则→构成要件→抗辩事由）",
    },
    "xigai": {
        "key": "xigai",
        "name": "习概",
        "knowledge_points": [
            "中国式现代化",
            "新发展理念",
            "高质量发展",
            "全过程人民民主",
            "文化自信",
            "总体国家安全观",
            "人类命运共同体",
            "全面深化改革",
            "共同富裕",
            "党的自我革命",
        ],
        "question_focus": "概念阐释、关系辨析、时政结合",
        "memory_strategy": "层级缩略（核心论点→支撑逻辑→关键词）",
    },
}

COURSE_KEYS: Final[list[str]] = list(COURSES.keys())


def get_seed_course(key: str) -> Course:
    """按 key 取种子课程定义。

    【何时用】
        只用于首次建库与提示词路由。
        业务代码请改用 course 服务从数据库取。

    Raises:
        KeyError: 课程不存在。
    """
    if key not in COURSES:
        raise KeyError(f"未知种子课程 key={key!r}，可选：{COURSE_KEYS}")
    return COURSES[key]


# ---------------------------------------------------------------
# 三、切分参数（M0 结构化切分）
# ---------------------------------------------------------------
CHUNK_SIZE: Final[int] = 500        # 每块目标字数
CHUNK_OVERLAP: Final[int] = 50      # 相邻块重叠字数
CHINESE_SEPARATORS: Final[list[str]] = [
    "\n第", "\n一、", "\n二、", "\n三、", "\n四、", "\n五、",
    "\n（一）", "\n（二）", "\n1.", "\n2.", "\n3.",
    "\n\n", "\n", "。", "；", "，", " ", "",
]


# ---------------------------------------------------------------
# 四、向量化与检索参数
# ---------------------------------------------------------------
EMBEDDING_MODEL_ID: Final[str] = "BAAI/bge-small-zh-v1.5"

# 本地模型目录。把模型文件放进来就能完全离线运行。
MODEL_DIR: Final[_Path] = BASE_DIR / "models"
LOCAL_MODEL_DIR: Final[_Path] = MODEL_DIR / "bge-small-zh-v1.5"

# 模型权重的可能文件名（不同来源/版本不一致，任一个存在即可）
_MODEL_WEIGHT_FILES: Final[tuple[str, ...]] = (
    "model.safetensors",
    "pytorch_model.bin",
)


def has_local_model() -> bool:
    """本地是否已有一份**完整**的向量模型。

    【为什么判断要严】
        必须 config.json 与权重文件都在。
        只看"目录存在"是不够的——一次中断的下载会留下空壳目录，
        之后被当成"已就绪"，加载时以一个莫名其妙的报错结束，
        而真正的原因是那份文件根本没下完。
    """
    if not LOCAL_MODEL_DIR.is_dir():
        return False
    if not (LOCAL_MODEL_DIR / "config.json").is_file():
        return False
    return any((LOCAL_MODEL_DIR / name).is_file() for name in _MODEL_WEIGHT_FILES)


def _resolve_embedding_model() -> str:
    """决定用哪个向量模型，顺序：本地 → 环境变量 → HuggingFace 模型名。

    本地优先是刻意的：既然磁盘上已经有一份完整的，就绝不该再联网去取。
    """
    if has_local_model():
        return str(LOCAL_MODEL_DIR)
    override = os.getenv("EMBEDDING_MODEL", "").strip()
    if override:
        return override
    return EMBEDDING_MODEL_ID


# 程序启动时定一次。下载了新模型或改了环境变量，需要重启应用才生效。
EMBEDDING_MODEL: Final[str] = _resolve_embedding_model()

TOP_K: Final[int] = 5              # 出题时检索上下文条数（M2）
SIMILARITY_THRESHOLD: Final[float] = 0.6   # 低于阈值触发网络搜索（M2）
DEDUP_THRESHOLD: Final[float] = 0.9        # 题干相似度高于此值视为重复


# ---------------------------------------------------------------
# 五、题型与难度枚举（避免下游拼写漂移）
# ---------------------------------------------------------------
QUESTION_TYPES: Final[list[str]] = ["简答", "选择"]
DIFFICULTIES: Final[list[str]] = ["易", "中", "难"]


# ---------------------------------------------------------------
# 六、MySQL（持久存储）
# ---------------------------------------------------------------
# 【为什么用 os.getenv 而不是硬编码】
#   密码绝不进代码库。所有敏感信息都从环境变量读，
#   .env 文件负责提供这些值（不提交 git）。
MYSQL_HOST: Final[str] = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT: Final[int] = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER: Final[str] = os.getenv("MYSQL_USER", "study_user")
MYSQL_PASSWORD: Final[str] = os.getenv("MYSQL_PASSWORD", "study_pass")
MYSQL_DATABASE: Final[str] = os.getenv("MYSQL_DATABASE", "study_db")
MYSQL_POOL_SIZE: Final[int] = int(os.getenv("MYSQL_POOL_SIZE", "5"))


# ---------------------------------------------------------------
# 七、Redis（缓存与临时数据）
# ---------------------------------------------------------------
REDIS_HOST: Final[str] = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT: Final[int] = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD: Final[str] = os.getenv("REDIS_PASSWORD", "")
REDIS_DB: Final[int] = int(os.getenv("REDIS_DB", "0"))

# 缓存 TTL 统一在这里定义，避免各 service 各写一个数字。
CACHE_TTL_COURSE_LIST: Final[int] = 300        # 课程列表 5 分钟
CACHE_TTL_KNOWLEDGE_POINTS: Final[int] = 600   # 知识点 10 分钟
CACHE_TTL_QUESTION_BANK: Final[int] = 600      # 题库 10 分钟
CACHE_TTL_DRAFT: Final[int] = 86400            # 作答草稿 24 小时


# ---------------------------------------------------------------
# 八、JWT
# ---------------------------------------------------------------
JWT_SECRET: Final[str] = os.getenv("JWT_SECRET", "change_me_in_production")
JWT_ALGORITHM: Final[str] = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES: Final[int] = int(os.getenv("JWT_EXPIRE_MINUTES", "120"))


# ---------------------------------------------------------------
# 九、LLM 接入（OpenAI 兼容协议）
# ---------------------------------------------------------------
# 所有值都可被环境变量覆盖，代码里不出现任何密钥。
LLM_BASE_URL: Final[str] = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_API_KEY: Final[str] = os.getenv("LLM_API_KEY", "")
LLM_MODEL: Final[str] = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT: Final[float] = float(os.getenv("LLM_TIMEOUT", "90"))
LLM_TEMPERATURE: Final[float] = float(os.getenv("LLM_TEMPERATURE", "0.7"))
LLM_MAX_RETRIES: Final[int] = int(os.getenv("LLM_MAX_RETRIES", "2"))
LLM_JSON_MODE: Final[bool] = os.getenv("LLM_JSON_MODE", "1") not in ("0", "false", "False")


# ---------------------------------------------------------------
# 十、搜索引擎（博查 API）
# ---------------------------------------------------------------
BOCHA_API_KEY: Final[str] = os.getenv("BOCHA_API_KEY", "")
BOCHA_BASE_URL: Final[str] = "https://api.bochaai.com/v1/web-search"


# ---------------------------------------------------------------
# 十一、网络搜索兜底开关
# ---------------------------------------------------------------
# 是否启用搜索兜底。默认关，通过环境变量 WEB_SEARCH_ENABLED=1 开启。
WEB_SEARCH_ENABLED: Final[bool] = os.getenv("WEB_SEARCH_ENABLED", "0") in ("1", "true", "True")


# ---------------------------------------------------------------
# 十二、出题相关参数
# ---------------------------------------------------------------
DEDUP_MAX_RETRY: Final[int] = 2
DEFAULT_WARMUP_COUNT: Final[dict[str, int]] = {"简答": 3, "选择": 5}

# 简答题判为"掌握"的评分要点命中率阈值。
# 单点定义：练习页的自动收录、错题集的复习判定都用它。
SHORT_ANSWER_PASS_RATIO: Final[float] = 0.6