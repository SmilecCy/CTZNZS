# -*- coding: utf-8 -*-
"""LLM 调用层：OpenAI 兼容协议的统一客户端。

【本版本新增】

    支持 **function calling（工具调用）**。
    让 LLM 能自己判断"我需要调搜索引擎"，
    而不是每次都把所有工具塞给它。

【function calling 是什么】

    普通调用：你给 LLM 一段提示词，它返回文本。

    function calling：你除了提示词，还给 LLM 一份"可用工具列表"。
    LLM 可以选择：
      A. 直接返回答案（像普通调用）
      B. 返回"我要调用某个工具，参数是 xxx"

    如果是 B，你执行工具，把结果再喂给 LLM，让它继续。
    这就能实现"搜索 → 看到结果 → 整合成题"这条链路。

【为什么需要】

    资料不足时，光让 LLM 编题会不准确（它没依据）。
    有了搜索工具，它能查真实资料再出题。

    对比"每次都强制搜索"：
      - 强制搜索：浪费（有资料也搜）、成本高
      - LLM 自判断：只在需要时搜，省成本
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_JSON_MODE,
    LLM_MAX_RETRIES,
    LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_TIMEOUT,
)


# ==============================================================
# 异常
# ==============================================================
class LLMError(RuntimeError):
    """LLM 调用的统一异常基类。"""


class LLMNotConfiguredError(LLMError):
    """未配置 API Key 时抛出。"""


class LLMResponseError(LLMError):
    """模型返回内容无法解析为期望结构时抛出。"""


# ==============================================================
# 数据结构
# ==============================================================
@dataclass
class LLMUsage:
    """一次调用的开销记录。"""

    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMResponse:
    """一次调用的完整结果。"""

    content: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    # 如果有工具调用请求，存这里。
    # 结构：[{"name": "search_web", "arguments": {"query": "..."}}, ...]
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


# ==============================================================
# JSON 提取
# ==============================================================
_RE_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> object:
    """从模型返回中稳健地抠出 JSON。"""
    if not text or not text.strip():
        raise LLMResponseError("模型返回为空")

    candidates: list[str] = []

    fence = _RE_FENCE.search(text)
    if fence:
        candidates.append(fence.group(1))

    candidates.append(text.strip())

    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = text.find(open_ch), text.rfind(close_ch)
        if start != -1 and end > start:
            candidates.append(text[start:end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue

    preview = text.strip()[:200]
    raise LLMResponseError(f"无法从模型返回中解析 JSON。返回前 200 字：{preview}")


# ==============================================================
# 客户端
# ==============================================================
class LLMClient:
    """OpenAI 兼容协议的聊天客户端。

    【本版本新增的能力】

        chat_with_tools(messages, tools, tool_executor)
        —— 带工具调用的对话。LLM 可以决定调工具，
           系统执行工具，再把结果喂回 LLM，循环直到 LLM 给出最终答案。
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        temperature: float | None = None,
    ) -> None:
        self.base_url = base_url or LLM_BASE_URL
        self.api_key = api_key if api_key is not None else LLM_API_KEY
        self.model = model or LLM_MODEL
        self.timeout = timeout if timeout is not None else LLM_TIMEOUT
        self.temperature = temperature if temperature is not None else LLM_TEMPERATURE
        self._client: object | None = None

    # ----------------------------------------------------------
    def is_configured(self) -> bool:
        """是否已具备调用条件。"""
        return bool(self.api_key)

    def _ensure_client(self) -> object:
        """惰性构造 OpenAI SDK 客户端。"""
        if self._client is not None:
            return self._client

        if not self.is_configured():
            raise LLMNotConfiguredError(
                "未配置 LLM API Key。请检查 .env 里的 LLM_API_KEY。"
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMError("未安装 openai SDK。请执行：pip install openai") from exc

        self._client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=LLM_MAX_RETRIES,
        )
        return self._client

    # ----------------------------------------------------------
    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        json_mode: bool | None = None,
    ) -> LLMResponse:
        """发起一次对话补全（无工具）。"""
        client = self._ensure_client()
        use_json = LLM_JSON_MODE if json_mode is None else json_mode

        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
        }
        if use_json:
            kwargs["response_format"] = {"type": "json_object"}

        started = time.monotonic()

        try:
            completion = client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            if use_json:
                kwargs.pop("response_format", None)
                try:
                    completion = client.chat.completions.create(**kwargs)
                except Exception as retry_exc:  # noqa: BLE001
                    raise LLMError(f"LLM 调用失败：{retry_exc}") from retry_exc
            else:
                raise LLMError(f"LLM 调用失败：{exc}") from exc

        latency_ms = int((time.monotonic() - started) * 1000)

        content = ""
        if completion.choices:
            content = completion.choices[0].message.content or ""

        raw_usage = getattr(completion, "usage", None)
        usage = LLMUsage(
            model=getattr(completion, "model", self.model) or self.model,
            prompt_tokens=int(getattr(raw_usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(raw_usage, "completion_tokens", 0) or 0),
            latency_ms=latency_ms,
        )

        if not content.strip():
            raise LLMResponseError("模型返回了空内容")

        return LLMResponse(content=content, usage=usage)

    # ----------------------------------------------------------
    def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
    ) -> tuple[object, LLMResponse]:
        """发起对话并直接解析 JSON。"""
        response = self.chat(messages, temperature=temperature, json_mode=True)
        payload = extract_json(response.content)
        return payload, response

    # ----------------------------------------------------------
    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_executor: Callable[[str, dict[str, Any]], str],
        max_iterations: int = 3,
        temperature: float | None = None,
    ) -> LLMResponse:
        """带工具调用的对话。

        【执行流程】

            第 1 轮：把 messages + tools 发给 LLM
              ↓
              如果 LLM 返回 tool_calls（想调工具）
                → 执行工具（用 tool_executor）
                → 把工具结果追加到 messages
                → 第 2 轮
              如果 LLM 返回 content（最终答案）
                → 结束

            最多循环 max_iterations 轮。超过就返回当前内容。

        【为什么限制 max_iterations】

            防止 LLM 反复调工具不给出最终答案（死循环）。
            3 次通常够了：第 1 次搜，第 2 次可能补充搜，第 3 次给答案。

        【为什么 tool_executor 是回调函数】

            本模块不直接依赖 search_tool（避免循环依赖）。
            调用方把"怎么执行工具"传进来。

            好处：将来加新工具（比如"查数据库"），
            本模块不用改，只需要传不同的 executor。

        Args:
            messages: 消息列表。
            tools: 可用工具列表（OpenAI function calling 格式）。
            tool_executor: 工具执行函数。
                签名：tool_executor(name: str, arguments: dict) -> str
                返回值会作为工具结果喂回 LLM。
            max_iterations: 最大循环轮数。
            temperature: 覆盖默认温度。

        Returns:
            LLMResponse。content 是最终的答案文本，
            usage 是所有轮次累计的开销。
        """
        client = self._ensure_client()
        use_temp = self.temperature if temperature is None else temperature

        # 累计所有轮次的 token
        total_prompt = 0
        total_completion = 0
        total_latency = 0
        used_model = self.model

        # 复制一份 messages（不要修改调用方传进来的）
        working_messages = list(messages)

        for iteration in range(max_iterations):
            # 构造请求
            kwargs: dict = {
                "model": self.model,
                "messages": working_messages,
                "temperature": use_temp,
                "tools": tools,
                # tool_choice="auto" 表示让 LLM 自己决定要不要调工具。
                # 如果强制调（"required"）会让它每次都必须调，
                # 那"资料足够时不搜"的设计就废了。
                "tool_choice": "auto",
            }

            started = time.monotonic()
            try:
                completion = client.chat.completions.create(**kwargs)
            except Exception as exc:  # noqa: BLE001
                raise LLMError(f"LLM 调用失败（第 {iteration + 1} 轮）：{exc}") from exc

            latency = int((time.monotonic() - started) * 1000)
            total_latency += latency

            # 累计 token
            raw_usage = getattr(completion, "usage", None)
            if raw_usage:
                total_prompt += int(getattr(raw_usage, "prompt_tokens", 0) or 0)
                total_completion += int(getattr(raw_usage, "completion_tokens", 0) or 0)
            used_model = getattr(completion, "model", self.model) or self.model

            # 取回复
            if not completion.choices:
                raise LLMResponseError("模型返回了空 choices")

            message = completion.choices[0].message
            content = message.content or ""
            tool_calls = getattr(message, "tool_calls", None) or []

            # 如果 LLM 没调工具 → 拿到最终答案，退出循环
            if not tool_calls:
                if not content.strip():
                    raise LLMResponseError("模型既没调工具，也没返回内容")
                return LLMResponse(
                    content=content,
                    usage=LLMUsage(
                        model=used_model,
                        prompt_tokens=total_prompt,
                        completion_tokens=total_completion,
                        latency_ms=total_latency,
                    ),
                )

            # 有工具调用：执行工具，把结果喂回 LLM
            # 先把 LLM 的这一轮回复追加到消息历史
            # （OpenAI 协议要求：调工具后，assistant 的这轮消息必须进历史）
            working_messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            })

            # 逐个执行工具
            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    tool_args = {}

                # 调 executor。executor 抛异常时给一个错误字符串，
                # 而不是让整个循环崩掉——因为"工具失败"该让 LLM 知道，
                # 由它决定是重试还是放弃。
                try:
                    result_str = tool_executor(tool_name, tool_args)
                except Exception as exc:  # noqa: BLE001
                    result_str = f"工具调用失败：{type(exc).__name__}: {exc}"

                # 把工具结果追加到消息历史
                working_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

        # 超过最大轮次：返回当前内容（可能为空）
        # 【为什么不抛异常】此时 LLM 已经调过工具了，可能积累了有用的信息，
        # 直接抛异常会让这些信息浪费。返回内容 + 让调用方处理更好。
        return LLMResponse(
            content=content if "content" in dir() else "",
            usage=LLMUsage(
                model=used_model,
                prompt_tokens=total_prompt,
                completion_tokens=total_completion,
                latency_ms=total_latency,
            ),
        )


# ==============================================================
# 工具定义辅助
# ==============================================================
def build_tool_definition(
    name: str,
    description: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """构造一个 OpenAI function calling 格式的工具定义。

    【为什么要辅助函数】
        工具定义的 JSON 结构比较绕（嵌套三层），
        手写容易写错。用辅助函数拼，出错概率低。

    Args:
        name: 工具名（英文，不能有空格）。
        description: 工具描述（告诉 LLM 这个工具干什么）。
            描述写得好不好，直接影响 LLM 会不会在正确的时机调用。
        parameters: 参数定义（JSON Schema 格式）。

    Returns:
        OpenAI function calling 格式的工具定义。
    """
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }