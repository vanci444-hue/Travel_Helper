"""预算专家：千问 Plus、JSON、无工具。"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

ROLE = "budget_expert"
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "budget_expert.md"
CATEGORY_LABELS = {
    "transport": "交通",
    "lodging": "住宿",
    "food": "餐饮",
    "tickets": "门票活动",
    "other": "其他",
}

LoopFn = Callable[..., Awaitable[dict[str, Any]]]


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def parse_result(raw: dict[str, Any] | None, *, cap_amount: float | None) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    if data.get("ok") is False:
        reason = str(data.get("reason") or "").strip()
        return {
            "ok": False,
            "reason_code": str(data.get("reason_code") or "model_error"),
            "reason": reason,
            "summary": reason or "预算未完成",
        }
    categories_in = data.get("categories") if isinstance(data.get("categories"), list) else []
    categories: list[dict[str, Any]] = []
    total = 0.0
    for item in categories_in:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "other")
        try:
            amount = float(item.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        total += amount
        categories.append(
            {
                "key": key,
                "label": CATEGORY_LABELS.get(key, key),
                "amount": amount,
            }
        )
    if data.get("total_amount") is not None:
        try:
            total = float(data.get("total_amount"))
        except (TypeError, ValueError):
            pass
    over_cap = bool(data.get("over_cap"))
    if cap_amount is not None and total > cap_amount:
        over_cap = True
    note = str(data.get("includes_note") or "含往返与当地食住行门票的估算，非实时报价")
    summary = f"合计约 {int(total)}，{'已超上限' if over_cap else '未超上限'}"
    if cap_amount is not None and not over_cap:
        summary = f"合计约 {int(total)}，未超 {int(cap_amount)}"
    return {
        "ok": True,
        "currency": str(data.get("currency") or "CNY"),
        "total_amount": total,
        "categories": categories,
        "includes_note": note,
        "over_cap": over_cap,
        "cap_amount": cap_amount,
        "summary": summary,
        "reason_code": None,
        "reason": None,
    }


async def run_budget(
    intake: dict[str, Any],
    research: dict[str, Any],
    itinerary_draft: dict[str, Any] | None,
    *,
    run_loop: LoopFn,
) -> dict[str, Any]:
    payload = {
        "intake": intake,
        "research": {
            "destination_city": research.get("destination_city"),
            "pois": research.get("pois") or [],
            "weather_summary": research.get("weather_summary"),
        },
        "itinerary_draft": itinerary_draft,
    }
    user = "请根据以下 json 估算预算，只输出 json：\n" + json.dumps(payload, ensure_ascii=False)
    raw = await run_loop(
        role=ROLE,
        provider="qwen",
        system_prompt=load_prompt(),
        user_content=user,
        tools=(),
        max_iter=1,
        thinking_enabled=False,
        json_object=True,
    )
    cap = intake.get("budget_amount_cny")
    try:
        cap_amount = float(cap) if cap is not None else None
    except (TypeError, ValueError):
        cap_amount = None
    return parse_result(raw, cap_amount=cap_amount)
