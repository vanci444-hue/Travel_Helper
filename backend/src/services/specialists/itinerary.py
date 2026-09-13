"""行程设计专员：DeepSeek Flash、开思考 reasoning_effort=high、工具最多 12 轮。"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from src.config.settings import settings
from src.models.common import new_id

ROLE = "itinerary_design"
ALLOWED_TOOLS = ("search_poi", "get_poi_detail", "route_walking", "route_transit")
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "itinerary_design.md"
PACE_MAJOR_BOUNDS: dict[str, tuple[int, int]] = {
    "relaxed": (1, 2),
    "moderate": (2, 3),
    "packed": (3, 4),
}
NON_MAJOR_TYPES = {"lodging", "meal"}
CHILD_NOTE = "避坑：带儿童注意人流与休息，预留看护时间。"
COUPLE_NOTE = "情侣节奏：适合散步或夜景，不赶场。"

LoopFn = Callable[..., Awaitable[dict[str, Any]]]


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_card(raw: dict[str, Any]) -> dict[str, Any] | None:
    lng = _as_float(raw.get("lng"))
    lat = _as_float(raw.get("lat"))
    if lng is None or lat is None:
        return None
    title = str(raw.get("title") or "").strip()
    if not title:
        return None
    return {
        "id": str(raw.get("id") or new_id("card")),
        "type": str(raw.get("type") or "attraction"),
        "title": title,
        "poi_id": str(raw.get("poi_id") or "") or None,
        "lng": lng,
        "lat": lat,
        "address": str(raw.get("address") or ""),
        "intro": str(raw.get("intro") or ""),
        "photo_url": raw.get("photo_url"),
        "start_time": raw.get("start_time"),
        "suitable_for_children": bool(raw.get("suitable_for_children", True)),
    }


def _normalize_leg(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": str(raw.get("mode") or "transit"),
        "duration_min": raw.get("duration_min"),
        "distance_m": raw.get("distance_m"),
        "summary": str(raw.get("summary") or "公交+步行（假设）"),
        "source": str(raw.get("source") or "estimate"),
    }


def is_major_card(card: dict[str, Any]) -> bool:
    return str(card.get("type") or "attraction") not in NON_MAJOR_TYPES


def _estimate_leg() -> dict[str, Any]:
    return {
        "mode": "transit",
        "duration_min": None,
        "distance_m": None,
        "summary": "公交+步行约（假设）",
        "source": "estimate",
    }


def _ensure_legs(cards: list[dict[str, Any]], legs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    needed = max(0, len(cards) - 1)
    filled = [leg for leg in legs if isinstance(leg, dict)]
    while len(filled) < needed:
        filled.append(_estimate_leg())
    return filled[:needed]


def _poi_coords(poi: dict[str, Any]) -> tuple[float, float] | None:
    lng = _as_float(poi.get("lng"))
    lat = _as_float(poi.get("lat"))
    if lng is not None and lat is not None:
        return lng, lat
    location = str(poi.get("location") or "")
    if "," not in location:
        return None
    left, right = location.split(",", 1)
    lng = _as_float(left.strip())
    lat = _as_float(right.strip())
    if lng is None or lat is None:
        return None
    return lng, lat


def _annotate_intro(card: dict[str, Any], companion: str) -> dict[str, Any]:
    intro = str(card.get("intro") or "").strip()
    if companion == "parent_child":
        if "避坑" not in intro:
            intro = f"{intro}。{CHILD_NOTE}".lstrip("。")
        card["suitable_for_children"] = bool(card.get("suitable_for_children", True))
    elif companion == "couple":
        if "情侣" not in intro and "夜景" not in intro:
            intro = f"{intro}。{COUPLE_NOTE}".lstrip("。")
    card["intro"] = intro
    return card


def card_from_research_poi(poi: dict[str, Any], companion: str) -> dict[str, Any] | None:
    coords = _poi_coords(poi)
    title = str(poi.get("name") or poi.get("title") or "").strip()
    if coords is None or not title:
        return None
    lng, lat = coords
    suitable = poi.get("suitable_for_children")
    card = {
        "id": new_id("card"),
        "type": "attraction",
        "title": title,
        "poi_id": str(poi.get("poi_id") or poi.get("id") or "") or None,
        "lng": lng,
        "lat": lat,
        "address": str(poi.get("address") or ""),
        "intro": str(poi.get("reason") or poi.get("intro") or ""),
        "photo_url": poi.get("photo_url"),
        "start_time": None,
        "suitable_for_children": True if suitable is None else bool(suitable),
    }
    return _annotate_intro(card, companion)


def density_instruction(intake: dict[str, Any]) -> str:
    pace = str(intake.get("pace") or "moderate")
    companion = str(intake.get("companion_type") or "unknown")
    low, high = PACE_MAJOR_BOUNDS.get(pace, (2, 3))
    pace_zh = {"relaxed": "轻松", "moderate": "适中", "packed": "紧凑"}.get(pace, pace)
    companion_zh = {
        "parent_child": "亲子：公园/动物园/博物馆，intro 写避坑，不要酒吧夜店",
        "couple": "情侣：夜景、散步、咖啡馆、观景，不要写成带娃清单",
        "family": "家庭出行，留休息",
        "friends": "朋友同行",
        "solo": "独行",
    }.get(companion, "按同行选点")
    return (
        f"【硬约束】节奏={pace_zh}，每天主要景点必须 {low}–{high} 个（不含住宿/正餐）；"
        f"人群={companion_zh}。不能只换标题或 companion_type。"
    )


def apply_pace_and_companion(
    days: list[dict[str, Any]],
    intake: dict[str, Any],
    research: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    pace = str(intake.get("pace") or "moderate")
    companion = str(intake.get("companion_type") or "unknown")
    low, high = PACE_MAJOR_BOUNDS.get(pace, (2, 3))
    used_titles: set[str] = set()
    pool: list[dict[str, Any]] = []
    for poi in (research or {}).get("pois") or []:
        if not isinstance(poi, dict):
            continue
        card = card_from_research_poi(poi, companion)
        if card is not None:
            pool.append(card)
    if companion == "parent_child":
        pool.sort(key=lambda item: (not item.get("suitable_for_children"), item.get("title") or ""))

    for day in days:
        cards = [card for card in day.get("cards") or [] if isinstance(card, dict)]
        lodging = [card for card in cards if card.get("type") == "lodging"]
        meals = [card for card in cards if card.get("type") == "meal"]
        majors = [_annotate_intro(card, companion) for card in cards if is_major_card(card)]
        if len(majors) > high:
            majors = majors[:high]
        if len(majors) < low:
            existing = {str(card.get("title") or "") for card in majors}
            for candidate in pool:
                title = str(candidate.get("title") or "")
                if not title or title in existing or title in used_titles:
                    continue
                if companion == "parent_child" and candidate.get("suitable_for_children") is False:
                    continue
                majors.append(candidate)
                existing.add(title)
                if len(majors) >= low:
                    break
        for card in majors:
            title = str(card.get("title") or "")
            if title:
                used_titles.add(title)
        next_cards = majors + meals + lodging
        day["cards"] = next_cards
        day["legs"] = _ensure_legs(next_cards, day.get("legs") or [])
    return days


def parse_result(raw: dict[str, Any] | None) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    if data.get("ok") is False:
        reason = str(data.get("reason") or "").strip()
        return {
            "ok": False,
            "reason_code": str(data.get("reason_code") or "model_error"),
            "reason": reason,
            "summary": reason or "行程未完成",
        }
    days_out: list[dict[str, Any]] = []
    for index, item in enumerate(data.get("days") or [], start=1):
        if not isinstance(item, dict):
            continue
        cards = []
        for card in item.get("cards") or []:
            if isinstance(card, dict):
                normalized = _normalize_card(card)
                if normalized is not None:
                    cards.append(normalized)
        legs_in = item.get("legs") if isinstance(item.get("legs"), list) else []
        legs = [_normalize_leg(leg) for leg in legs_in if isinstance(leg, dict)]
        days_out.append(
            {
                "day_index": int(item.get("day_index") or index),
                "label": str(item.get("label") or f"第 {index} 天"),
                "date": item.get("date"),
                "cards": cards,
                "legs": _ensure_legs(cards, legs),
            }
        )
    summary = str(data.get("summary") or f"{len(days_out)} 天行程")
    return {
        "ok": True,
        "days": days_out,
        "summary": summary,
        "reason_code": None,
        "reason": None,
    }


async def run_itinerary(
    intake: dict[str, Any],
    research: dict[str, Any],
    *,
    run_loop: LoopFn,
) -> dict[str, Any]:
    payload = {
        "intake": intake,
        "research": {
            "destination_city": research.get("destination_city"),
            "pois": research.get("pois") or [],
            "weather_summary": research.get("weather_summary"),
            "warnings": research.get("warnings") or [],
        },
    }
    user = (
        density_instruction(intake)
        + "\n请根据以下 json 设计行程，先工具后结论，只输出 json：\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    raw = await run_loop(
        role=ROLE,
        provider="deepseek",
        system_prompt=load_prompt(),
        user_content=user,
        tools=ALLOWED_TOOLS,
        max_iter=settings.max_tool_iterations_itinerary,
        thinking_enabled=settings.itinerary_thinking_enabled,
        json_object=True,
        reasoning_effort="high" if settings.itinerary_thinking_enabled else None,
    )
    parsed = parse_result(raw)
    if parsed.get("ok"):
        parsed["days"] = apply_pace_and_companion(parsed.get("days") or [], intake, research)
    return parsed
