"""规划运行日志：脱敏、截断、80 条上限与 SSE 订阅。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from src.models.common import new_id, utc_iso, utcnow

MAX_ENTRIES = 80
BODY_LIMIT = 4000
POLYLINE_KEYS = frozenset({"polyline", "polylines"})
SECRET_HINTS = ("sk-", "bearer ", "api_key", "apikey", "authorization")


def _looks_secret(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered for hint in SECRET_HINTS)


def sanitize_text(value: Any, secrets: list[str] | None = None) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    for secret in secrets or []:
        if secret:
            text = text.replace(secret, "[redacted]")
    if _looks_secret(text):
        text = "已脱敏，不展示密钥或凭证"
    return text


def sanitize_value(value: Any, secrets: list[str] | None = None) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in POLYLINE_KEYS or lowered in {"key", "api_key", "authorization"}:
                continue
            if lowered in {"url", "href", "request", "response", "http"}:
                continue
            cleaned[str(key)] = sanitize_value(item, secrets)
        return cleaned
    if isinstance(value, list):
        return [sanitize_value(item, secrets) for item in value]
    if isinstance(value, str):
        return sanitize_text(value, secrets)
    return value


def truncate_body(text: str) -> str:
    if len(text) <= BODY_LIMIT:
        return text
    return text[: BODY_LIMIT - 4] + "已截断"


def evict_overflow(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trimmed = list(entries)
    while len(trimmed) > MAX_ENTRIES:
        thought_index = next(
            (index for index, item in enumerate(trimmed) if item.get("kind") == "thought"),
            0,
        )
        trimmed.pop(thought_index)
    return trimmed


def build_entry(
    *,
    kind: str,
    specialist: str,
    title: str,
    body: str | None = None,
    clickable: bool | None = None,
    secrets: list[str] | None = None,
) -> dict[str, Any]:
    clean_title = sanitize_text(title, secrets).strip() or "完成一步"
    if any(token in clean_title.lower() for token in ("deepseek", "qwen", "dashscope", "http")):
        clean_title = "完成一步规划"
    detail = None
    has_body = body is not None and str(body).strip() != ""
    is_clickable = has_body if clickable is None else clickable
    if is_clickable:
        clean_body = truncate_body(sanitize_text(body or "暂无更多说明", secrets))
        detail = {"heading": clean_title, "body": clean_body}
        is_clickable = True
    return {
        "id": new_id("log"),
        "kind": kind,
        "specialist": specialist,
        "title": clean_title,
        "clickable": bool(is_clickable),
        "detail": detail,
        "created_at": utc_iso(utcnow()),
    }


def append_entry(
    entries: list[dict[str, Any]],
    entry: dict[str, Any],
) -> list[dict[str, Any]]:
    return evict_overflow([*entries, entry])


class PlanningEventHub:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, conversation_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subs.setdefault(conversation_id, []).append(queue)
        return queue

    def unsubscribe(self, conversation_id: str, queue: asyncio.Queue) -> None:
        items = self._subs.get(conversation_id) or []
        if queue in items:
            items.remove(queue)
        if not items:
            self._subs.pop(conversation_id, None)

    def publish(self, conversation_id: str, event: str, data: dict[str, Any]) -> None:
        payload = (event, data)
        for queue in list(self._subs.get(conversation_id) or []):
            queue.put_nowait(payload)


event_hub = PlanningEventHub()
