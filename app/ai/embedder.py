# -*- coding: utf-8 -*-
"""M0-v0.1 向量化：中文 embedding（bge-small-zh-v1.5）。

模型体积不小，因此采用**惰性单例**加载：只有第一次真正需要向量时才下载/载入，
保证纯结构调试和单元测试不必等模型。
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from app.config import EMBEDDING_MODEL

if TYPE_CHECKING:  # pragma: no cover
    from sentence_transformers import SentenceTransformer

_MODEL: "SentenceTransformer | None" = None

DEFAULT_HF_ENDPOINT = "https://huggingface.co"


class EmbeddingUnavailableError(RuntimeError):
    """未安装 sentence-transformers，或向量模型加载失败时抛出。"""


# 下载失败的排查提示。提前探测与真失败两条路径共用同一段文字，
# 免得改了其中一处、另一处还在教用户做已经不做用的事。
_DOWNLOAD_HINT = (
    f"加载中文向量模型失败：{EMBEDDING_MODEL}\n\n"
    "最常见的原因是下载模型时连不上 HuggingFace（国内网络几乎必然如此）。"
    "两个办法，任选其一：\n\n"
    "  1. 设置镜像（推荐）。设好后**完整重启应用**才会生效：\n"
    "       PowerShell:  $env:HF_ENDPOINT=\"https://hf-mirror.com\"\n"
    "       CMD:         set HF_ENDPOINT=https://hf-mirror.com\n"
    "       或直接加到系统环境变量里，一劳永逸\n\n"
    "  2. 手动下载模型到本地目录，再把 app/config.py 里的\n"
    "     EMBEDDING_MODEL 改成本地路径\n\n"
    "模型只需成功下载一次，之后会缓存在本地，不再联网。"
)


def _endpoint_reachable(timeout: float = 3.0) -> bool:
    """探测 HuggingFace 端点是否可达。

    只做一次 TCP 握手，不下载任何东西——耗时上限就是 ``timeout`` 秒。

    之所以要这一步：默认情况下 huggingface_hub 会重试 5 次、每次间隔递增，
    用户要干等一分钟才看到报错，很容易以为程序卡死了。
    提前三秒问一句，就能把这一分钟变成一条立刻可行动的提示。
    """
    endpoint = os.getenv("HF_ENDPOINT") or DEFAULT_HF_ENDPOINT
    host = urlparse(endpoint).hostname
    if not host:
        return True   # 解析不出主机名就别拦，交给后面的真实调用去报错

    try:
        with socket.create_connection((host, 443), timeout=timeout):
            return True
    except OSError:
        return False


def _model_cached() -> bool | None:
    """模型是否已在本地缓存。

    Returns:
        True/False；**None 表示判断不出来**——此时调用方应当跳过网络探测。
        宁可慢一点，也不要误拦一次本来能成功的加载。
    """
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        folder = Path(HF_HUB_CACHE) / ("models--" + EMBEDDING_MODEL.replace("/", "--"))
        return folder.exists()
    except Exception:  # noqa: BLE001 - 拿不到缓存路径就不做判断
        return None


def model_status() -> dict:
    """向量模型的可就绪状态，供自检脚本与界面提前展示。

    "能不能用"取决于两件事：模型在不在本地缓存、HuggingFace 端点通不通。
    提前问一句，就能把"上传资料时才发现失败"变成"启动前就知道"。

    ``ready`` 的判断故意偏向宽松（缓存状态判断不出来就算就绪）：
    自检误报"不可用"会让人白折腾一通，比漏报还烦。

    Returns:
        ``{"cached": True/False/None, "endpoint": 地址, "reachable": 布尔, "ready": 布尔}``
    """
    cached = _model_cached()
    reachable = _endpoint_reachable()
    return {
        "cached": cached,
        "endpoint": os.getenv("HF_ENDPOINT") or DEFAULT_HF_ENDPOINT,
        "reachable": reachable,
        "ready": (cached is not False) or reachable,
    }


# 缺少某个依赖模块时的提示。**必须与"下载失败"分开**：
# 模型已经下好了、只是缺个包，却提示去配网络镜像，等于把人引到错误的方向上——
# 比不提示还糟。
_MISSING_DEP_HINT = (
    "加载向量模型时缺少依赖模块：{module}\n\n"
    "sentence-transformers 依赖的一些包不会自动装上，缺哪个补哪个：\n"
    "    pip install {module}\n\n"
    "最常见的是 torchvision：transformers 会用到它，但它不在 "
    "sentence-transformers 的依赖声明里，所以 pip 装前者时不会带上它。"
)


def get_model() -> "SentenceTransformer":
    """返回（并缓存）embedding 模型实例。"""
    global _MODEL
    if _MODEL is not None:
        return _MODEL

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover
        raise EmbeddingUnavailableError(
            "需要向量化能力但未安装 sentence-transformers。请执行：\n"
            "    pip install sentence-transformers"
        ) from exc

    # 模型是本地目录时，一切网络探测都是多余的，直接跳过。
    #
    # 这一步很关键：缓存探测是按 HuggingFace 的目录命名规则算路径的
    # （models--BAAI--bge-small-zh-v1.5），而本地路径算出来是个不存在的名字，
    # 于是会被误判成"没缓存"；要是此时端点又恰好不通，就会报"下载失败"——
    # 可模型明明就在磁盘上躺着。
    is_local = Path(EMBEDDING_MODEL).is_dir()

    # 只在"确定没缓存"且"端点不可达"时才提前失败：
    # 两个条件缺一不可，避免误拦已经下载好模型、只是暂时断网的场景。
    if not is_local and _model_cached() is False and not _endpoint_reachable():
        raise EmbeddingUnavailableError(
            _DOWNLOAD_HINT
            + "\n\n提示：也可以运行 python scripts/download_model.py "
            "把模型下到本地，之后就能完全离线使用。"
        )

    try:
        _MODEL = SentenceTransformer(EMBEDDING_MODEL)
    except ModuleNotFoundError as exc:
        # 缺包要单独处理。这里最忌讳的是把"少装一个包"说成"网络不通"——
        # 用户会去折腾镜像和代理，而真正该做的是一条 pip install。
        raise EmbeddingUnavailableError(
            _MISSING_DEP_HINT.format(module=exc.name or "未知模块")
        ) from exc
    except Exception as exc:
        raise EmbeddingUnavailableError(_DOWNLOAD_HINT) from exc

    return _MODEL


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """批量把文本转成向量。

    bge 系列检索时建议给"查询"加指令前缀、给"文档"不加；
    本函数只负责**文档侧**向量化，查询侧请用 :func:`embed_query`。

    Args:
        texts: 待向量化文本列表。
        batch_size: 批大小。

    Returns:
        与输入等长的向量列表。
    """
    if not texts:
        return []
    vectors = get_model().encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,   # 归一化后余弦相似度=点积，便于阈值比较
        show_progress_bar=False,
    )
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> list[float]:
    """把检索查询转成向量（带 bge 推荐的中文检索指令前缀）。"""
    instruction = "为这个句子生成表示以用于检索相关文章："
    return embed_texts([instruction + text])[0]