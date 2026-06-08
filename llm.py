"""
LLM 接口封装 - 兼容 Chat2API (OpenAI 格式)
支持多模型：每个 NPC 绑定独立的 LLM 模型
规则：所有模型共用同一 Chat2API 地址，只是传不同的 model 参数。
chat_with_tools() 使用 DeepSeek 官方 API（支持 function calling）。
"""
import os
import sys
import time
import threading
import json
import urllib.error
import urllib.request
from openai import OpenAI
from config_loader import load_config


_config = load_config()
_llm_config = _config["llm"]
_ds_config = _config.get("deepseek_api", {})

_client = OpenAI(
    api_key=_llm_config["api_key"],
    base_url=_llm_config["api_base"],
)
_CHAT2API_CLIENT = _client

_DEEPSEEK_CLIENT = None
if _ds_config.get("api_key"):
    _DEEPSEEK_CLIENT = OpenAI(
        api_key=_ds_config["api_key"],
        base_url=_ds_config.get("api_base", "https://api.deepseek.com/v1"),
    )

_BASE_DEFAULT_MODEL = _llm_config.get("default_model", "")
_DEFAULT_MODEL = _BASE_DEFAULT_MODEL
_RUNTIME_PROTOCOL = "openai"
_RUNTIME_API_KEY = ""
_RUNTIME_API_BASE = ""
_RUNTIME_WIRE_API = "chat_completions"
_RUNTIME_REASONING_EFFORT = ""
_REQUEST_TIMEOUT = _llm_config.get("request_timeout_seconds", 60)
_RETRY_DELAY = _llm_config.get("retry_delay_seconds", 5)
_MAX_RETRIES = _llm_config.get("max_retries", 3)
_LAST_ERRORS = {}

_AGENT_MODEL_MAP = _llm_config.get("agent_models", {})
_RUNTIME_MODEL_MAP = {}

_MAX_CONCURRENT = _llm_config.get("max_concurrent_requests", 3)
if _MAX_CONCURRENT < 1:
    _MAX_CONCURRENT = 1
_MODEL_SEMAPHORE = threading.Semaphore(_MAX_CONCURRENT)
_MAX_PRIORITY_CONCURRENT = _llm_config.get("max_priority_requests", 1)
if _MAX_PRIORITY_CONCURRENT < 1:
    _MAX_PRIORITY_CONCURRENT = 1
_PRIORITY_SEMAPHORE = threading.Semaphore(_MAX_PRIORITY_CONCURRENT)


def normalize_llm_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    lower = text.lower()
    if "402" in lower or "insufficient_balance" in lower or "insufficient account balance" in lower:
        return "账户余额不足：当前 API Key 或供应商账号没有可用额度，请充值或更换供应商/API Key。"
    if "429" in lower or "rate limit" in lower or "rate-limited" in lower or "ratelimit" in lower:
        return "模型限流：当前模型或上游供应商暂时限流，请稍后重试或更换模型/API Key。"
    return text


def configure_runtime_llm(override: dict = None) -> dict:
    """Switch the chat client for this process without persisting API keys."""
    global _client, _DEFAULT_MODEL, _RUNTIME_PROTOCOL, _RUNTIME_API_KEY, _RUNTIME_API_BASE
    global _RUNTIME_WIRE_API, _RUNTIME_REASONING_EFFORT

    provider = (override or {}).get("provider", "").strip().lower()
    api_key = (override or {}).get("api_key", "").strip()
    model = (override or {}).get("model", "").strip()
    api_base = (override or {}).get("api_base", "").strip()
    wire_api = (override or {}).get("wire_api", "chat_completions").strip().lower()
    reasoning_effort = (override or {}).get("reasoning_effort", "").strip().lower()

    if provider and api_key and model and api_base:
        _RUNTIME_PROTOCOL = "anthropic" if provider in ("anthropic", "custom_anthropic") else "openai"
        _RUNTIME_API_KEY = api_key
        _RUNTIME_API_BASE = api_base
        _RUNTIME_WIRE_API = wire_api if wire_api in {"chat_completions", "responses"} else "chat_completions"
        _RUNTIME_REASONING_EFFORT = reasoning_effort
        if _RUNTIME_PROTOCOL == "openai":
            _client = OpenAI(
                api_key=api_key,
                base_url=api_base,
                default_headers={
                    "HTTP-Referer": "http://127.0.0.1:5000",
                    "X-Title": "Werewolf Ville",
                },
            )
        _DEFAULT_MODEL = model
        return {
            "provider": provider,
            "model": model,
            "api_base": api_base,
            "wire_api": _RUNTIME_WIRE_API,
            "reasoning_effort": _RUNTIME_REASONING_EFFORT,
        }

    _client = _CHAT2API_CLIENT
    _DEFAULT_MODEL = _BASE_DEFAULT_MODEL
    _RUNTIME_PROTOCOL = "openai"
    _RUNTIME_API_KEY = ""
    _RUNTIME_API_BASE = ""
    _RUNTIME_WIRE_API = "chat_completions"
    _RUNTIME_REASONING_EFFORT = ""
    return {"provider": "chat2api", "model": _DEFAULT_MODEL, "wire_api": "chat_completions"}


def _call_anthropic_messages(model: str, messages: list, temperature: float,
                             max_tokens: int, timeout: int) -> str:
    system_texts = []
    anthropic_messages = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            system_texts.append(content)
        elif role in ("user", "assistant"):
            anthropic_messages.append({"role": role, "content": content})
    if not anthropic_messages:
        anthropic_messages = [{"role": "user", "content": ""}]

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": anthropic_messages,
    }
    if system_texts:
        payload["system"] = "\n\n".join(system_texts)

    url = _RUNTIME_API_BASE.rstrip("/") + "/messages"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": _RUNTIME_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Anthropic HTTP {e.code}: {body}") from e

    parts = []
    for block in data.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts).strip()


def set_runtime_model_assignments(assignments: dict) -> None:
    global _RUNTIME_MODEL_MAP
    _RUNTIME_MODEL_MAP.clear()
    if not isinstance(assignments, dict):
        return
    for k, v in assignments.items():
        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
            _RUNTIME_MODEL_MAP[k.strip()] = v.strip()


def get_model_for_agent(agent_name: str) -> str:
    if agent_name in _RUNTIME_MODEL_MAP:
        return _RUNTIME_MODEL_MAP[agent_name]
    return _AGENT_MODEL_MAP.get(agent_name, _DEFAULT_MODEL)


def get_last_error_for_agent(agent_name: str) -> str:
    return _LAST_ERRORS.get(agent_name, "")


def _perform_chat_request(model: str, messages: list, temperature: float,
                          max_tokens: int, timeout: int) -> str:
    if _RUNTIME_PROTOCOL == "anthropic":
        return _call_anthropic_messages(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
    if _RUNTIME_WIRE_API == "responses":
        return _call_openai_responses(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
    response = _client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""


def _call_openai_responses(model: str, messages: list, temperature: float,
                           max_tokens: int, timeout: int) -> str:
    payload = {
        "model": model,
        "input": [
            {
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            }
            for msg in messages
        ],
        "temperature": temperature,
        "max_output_tokens": max_tokens,
        "store": False,
    }
    if _RUNTIME_REASONING_EFFORT:
        payload["reasoning"] = {"effort": _RUNTIME_REASONING_EFFORT}
    req = urllib.request.Request(
        _RUNTIME_API_BASE.rstrip("/") + "/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_RUNTIME_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Responses HTTP {e.code}: {body}") from e

    if isinstance(data.get("output_text"), str):
        return data["output_text"].strip()
    parts = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            if isinstance(content, dict):
                text = content.get("text") or content.get("content")
                if isinstance(text, str):
                    parts.append(text)
    return "".join(parts).strip()


def _call_with_retry(model: str, messages: list, temperature: float,
                     max_tokens: int, timeout: int, max_retries: int = None,
                     priority: bool = False) -> str:
    """带指数退避重试的 LLM 调用"""
    retries = max_retries if max_retries is not None else _MAX_RETRIES
    last_error = None
    for attempt in range(retries + 1):
        try:
            semaphore = _PRIORITY_SEMAPHORE if priority else _MODEL_SEMAPHORE
            with semaphore:
                return _perform_chat_request(model, messages, temperature, max_tokens, timeout)
        except Exception as e:
            last_error = e
            if attempt < retries:
                wait = _RETRY_DELAY * (2 ** attempt)
                print(f"[LLM Retry] attempt={attempt+1}/{retries}, "
                      f"wait={wait}s, error={type(e).__name__}: {e}",
                      file=sys.stderr, flush=True)
                time.sleep(wait)
    raise last_error


def chat(system_prompt: str, user_prompt: str, temperature: float = None) -> str:
    temp = temperature if temperature is not None else _llm_config["temperature"]
    try:
        return _call_with_retry(
            model=_DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temp,
            max_tokens=_llm_config["max_tokens"],
            timeout=_REQUEST_TIMEOUT,
        )
    except Exception as e:
        print(f"[LLM Error] chat: {e}", file=sys.stderr, flush=True)
        return ""


def chat_for_agent(agent_name: str, system_prompt: str, user_prompt: str,
                   temperature: float = None, max_retries: int = None,
                   priority: bool = False) -> str:
    model = get_model_for_agent(agent_name)
    temp = temperature if temperature is not None else _llm_config["temperature"]
    try:
        print(f"[chat_for_agent] {agent_name} -> model={model}", file=sys.stderr, flush=True)
        content = _call_with_retry(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temp,
            max_tokens=_llm_config["max_tokens"],
            timeout=_REQUEST_TIMEOUT,
            max_retries=max_retries,
            priority=priority,
        )
        print(f"[chat_for_agent] {agent_name} resp len={len(content)}", file=sys.stderr, flush=True)
        _LAST_ERRORS.pop(agent_name, None)
        return content
    except Exception as e:
        _LAST_ERRORS[agent_name] = normalize_llm_error(e)
        print(f"[LLM Error] {agent_name} ({model}): {e}", file=sys.stderr, flush=True)
        return ""


def chat_with_tools(system_prompt: str, user_prompt: str,
                    tools: list, tool_choice: str = "auto",
                    temperature: float = None) -> dict:
    """使用 DeepSeek 官方 API 的 Function Calling 调用
    
    Args:
        system_prompt: 系统提示
        user_prompt: 用户提示
        tools: OpenAI 格式的工具定义列表
        tool_choice: "auto"/"none"/"required" 或特定工具
        temperature: 温度参数
    
    Returns:
        dict: 包含 content 和 tool_calls 的响应
    """
    if _DEEPSEEK_CLIENT is None:
        print("[LLM Error] chat_with_tools: DeepSeek API 未配置", file=sys.stderr, flush=True)
        return {"content": "", "tool_calls": None}

    ds_model = _ds_config.get("model", "deepseek-chat")
    temp = temperature if temperature is not None else _llm_config["temperature"]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = _DEEPSEEK_CLIENT.chat.completions.create(
            model=ds_model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temp,
            max_tokens=_llm_config["max_tokens"],
            timeout=_REQUEST_TIMEOUT,
        )
        msg = response.choices[0].message
        result = {"content": msg.content or ""}
        if msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        else:
            result["tool_calls"] = None
        return result
    except Exception as e:
        print(f"[LLM Error] chat_with_tools ({ds_model}): {e}", file=sys.stderr, flush=True)
        return {"content": "", "tool_calls": None}

# 导出公开模型列表供游戏引擎路由调用
available_models = _llm_config.get("available_models", [])
