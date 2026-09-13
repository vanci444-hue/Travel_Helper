"""DeepSeek OpenAI 兼容 Chat Completions。禁止 dashscope SDK，禁止 os.getenv。"""

from __future__ import annotations

import asyncio
import json

import httpx
from pycore.core import get_logger
from src.config.settings import settings
from src.models.common import ManagerUnavailableError, MissingModelKeyError

logger = get_logger()


def strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def parse_json_object(raw: str) -> dict:
    text = strip_json_fence(raw)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data


def _chat_url() -> str:
    return f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"


async def chat_completion(
    messages: list[dict[str, str]],
    *,
    json_object: bool = False,
    thinking_enabled: bool | None = None,
) -> str:
    api_key = (settings.deepseek_api_key or "").strip()
    if not api_key:
        raise MissingModelKeyError()

    enabled = (
        settings.manager_thinking_enabled if thinking_enabled is None else thinking_enabled
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": settings.deepseek_model,
        "messages": messages,
        "thinking": {"type": "enabled" if enabled else "disabled"},
    }
    if json_object:
        payload["response_format"] = {"type": "json_object"}
    timeout = httpx.Timeout(settings.llm_timeout_seconds)
    async with httpx.AsyncClient(trust_env=False, timeout=timeout) as client:
        data = await _post_chat(client, _chat_url(), headers, payload)
    choices = data.get("choices") or []
    if not choices:
        raise ManagerUnavailableError()
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ManagerUnavailableError()
    logger.info("调用规划经理接口成功，返回含 choices 字段")
    return content


async def chat_json(
    messages: list[dict[str, str]],
    *,
    thinking_enabled: bool | None = None,
) -> dict:
    content = await chat_completion(
        messages,
        json_object=True,
        thinking_enabled=thinking_enabled,
    )
    try:
        return parse_json_object(content)
    except (ValueError, json.JSONDecodeError):
        logger.warning("规划经理 JSON 首次解析失败，尝试修复调用")
        repair_messages = [
            *messages,
            {"role": "assistant", "content": content},
            {"role": "user", "content": "只输出 json"},
        ]
        content = await chat_completion(
            repair_messages,
            json_object=True,
            thinking_enabled=thinking_enabled,
        )
        try:
            return parse_json_object(content)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ManagerUnavailableError() from exc


async def _post_chat(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    payload: dict,
) -> dict:
    attempts = 1 + max(0, settings.llm_max_retries)
    for attempt in range(attempts):
        try:
            response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException:
            logger.warning("规划经理接口超时", attempt=attempt + 1)
            if attempt < attempts - 1:
                await asyncio.sleep(1)
                continue
            raise ManagerUnavailableError() from None
        except httpx.HTTPError as exc:
            logger.warning("规划经理接口网络错误", attempt=attempt + 1, error_msg=str(exc))
            if attempt < attempts - 1:
                await asyncio.sleep(1)
                continue
            raise ManagerUnavailableError() from exc

        if response.status_code == 429 or response.status_code >= 500:
            logger.warning(
                "规划经理接口可重试错误",
                status_code=response.status_code,
                attempt=attempt + 1,
            )
            if attempt < attempts - 1:
                await asyncio.sleep(1)
                continue
            raise ManagerUnavailableError()
        if response.status_code >= 400:
            logger.warning("规划经理接口客户端错误", status_code=response.status_code)
            raise ManagerUnavailableError()
        data = response.json()
        if not isinstance(data, dict):
            raise ManagerUnavailableError()
        return data
    raise ManagerUnavailableError()
