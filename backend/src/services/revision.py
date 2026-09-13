"""行程读写、逐项改与对话修订。不重跑三专员；无金额不重算预算。"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Literal

from pycore.core import get_logger
from pydantic import Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.config.settings import settings
from src.db.models import Itinerary
from src.models.common import (
    CamelModel,
    CompanionType,
    NotFoundError,
    Pace,
    ValidationAppError,
    new_id,
    utc_iso,
    utcnow,
)
from src.plugins.amap import AmapClient
from src.plugins.geocode_city import GeocodeCityPlugin
from src.plugins.route_transit import RouteTransitPlugin
from src.plugins.route_walking import RouteWalkingPlugin
from src.services.specialists.budget import CATEGORY_LABELS

logger = get_logger()

ITINERARY_NOT_FOUND = "找不到这份行程"
CARD_NOT_FOUND = "找不到这张卡片"
UNMAPPED_REPLY = (
    "💬 我可以帮你删掉某张卡片、改开始时间，或者把某一天排松一点。"
    "换目的地或大幅改天数请去新建计划。"
)
NEW_PLAN_REPLY = "🗺️ 换目的地或大幅改天数需要去新建计划。当前这份行程我先不动。"
REVISED_REPLY = "👍 好，我按你的意思改好了，还是这一份行程。"
TRANSIT_REPLY = "👍 白天这段我改成多坐公交、少走路，还是这一份行程。"
LODGING_REPLY = "👍 住宿我换成更安静的推荐，还是这一份行程。"
LOOSEN_DAY3_REPLY = "👍 第三天我帮你排松一点，还是这一份行程。"
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAJOR_DEST_RE = re.compile(r"换目的地|改去|换个城市|换个地方|换成|改到")
DAYS_RE = re.compile(r"(?:改成|变成|改到|换成)\s*(\d{1,2})\s*天")
LOOSEN_DAY3_RE = re.compile(r"第三天不要排那么满")
PREFER_TRANSIT_RE = re.compile(r"少走路.*公交|公交.*少走路")
QUIET_LODGING_RE = re.compile(r"更安静的推荐住宿|换一家更安静")
PASSPORT_MARKERS = ("护照", "签证")
WALK_SPEED_M_PER_MIN = 80
TRANSIT_SPEED_M_PER_MIN = 250

CardType = Literal["attraction", "lodging", "meal", "other"]
TransitMode = Literal["transit", "walking", "mixed"]
LegSource = Literal["amap", "estimate"]
ItineraryStatus = Literal["ready"]

_leg_resolver = None


def set_leg_resolver(fn) -> None:
    global _leg_resolver
    _leg_resolver = fn


class CardPatch(CamelModel):
    title: str | None = None
    start_time: str | None = None
    day_index: int | None = Field(default=None, ge=1)
    sort_order: int | None = Field(default=None, ge=0)

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not TIME_RE.match(text):
            raise ValueError("开始时间须为 HH:MM")
        return text

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("标题不能为空")
        return text

    @model_validator(mode="after")
    def at_least_one(self) -> CardPatch:
        if not self.model_fields_set:
            raise ValueError("至少改一项")
        return self


class ItineraryCardPublic(CamelModel):
    id: str
    type: CardType
    title: str
    poi_id: str | None = None
    lng: float | None = None
    lat: float | None = None
    address: str | None = None
    intro: str | None = None
    photo_url: str | None = None
    start_time: str | None = None
    suitable_for_children: bool = True


class TransitLegPublic(CamelModel):
    mode: TransitMode
    duration_min: int | None = None
    distance_m: int | None = None
    summary: str
    source: LegSource


class ItineraryDayPublic(CamelModel):
    day_index: int
    label: str
    date: str | None = None
    cards: list[ItineraryCardPublic] = Field(default_factory=list)
    legs: list[TransitLegPublic] = Field(default_factory=list)


class BudgetCategoryPublic(CamelModel):
    key: str
    label: str
    amount: float


class BudgetPublic(CamelModel):
    currency: str = "CNY"
    cap_amount: float
    total_amount: float
    over_cap: bool
    includes_note: str
    categories: list[BudgetCategoryPublic] = Field(default_factory=list)


class ChecklistItemPublic(CamelModel):
    id: str
    text: str
    relevant: bool = True


class QuickSuggestionPublic(CamelModel):
    id: str
    text: str


class MapPointPublic(CamelModel):
    lng: float
    lat: float


class ItineraryPublic(CamelModel):
    id: str
    conversation_id: str
    title: str
    destination_city: str
    origin_city: str
    duration_days: int
    pace: Pace
    companion_type: CompanionType | str
    assumptions: list[str] = Field(default_factory=list)
    days: list[ItineraryDayPublic] = Field(default_factory=list)
    budget: BudgetPublic
    checklist: list[ChecklistItemPublic] = Field(default_factory=list)
    map_center: MapPointPublic
    quick_suggestions: list[QuickSuggestionPublic] = Field(default_factory=list)
    status: ItineraryStatus
    created_at: str
    updated_at: str


class ItineraryListItem(CamelModel):
    id: str
    title: str
    destination_city: str
    duration_days: int
    pace: Pace
    updated_at: str
    conversation_id: str


def loads_payload(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("行程数据无效")
    return data


def dumps_payload(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def itinerary_summary(payload: dict[str, Any]) -> dict[str, Any]:
    days = []
    for day in payload.get("days") or []:
        cards = []
        for card in day.get("cards") or []:
            cards.append(
                {
                    "id": card.get("id"),
                    "title": card.get("title"),
                    "type": card.get("type"),
                    "start_time": card.get("start_time"),
                }
            )
        days.append(
            {
                "day_index": day.get("day_index"),
                "label": day.get("label"),
                "card_count": len(cards),
                "cards": cards,
            }
        )
    return {
        "id": payload.get("id"),
        "destination_city": payload.get("destination_city"),
        "duration_days": payload.get("duration_days"),
        "days": days,
    }


def is_major_replan(text: str, payload: dict[str, Any]) -> bool:
    if MAJOR_DEST_RE.search(text):
        return True
    match = DAYS_RE.search(text)
    if match:
        new_days = int(match.group(1))
        current = int(payload.get("duration_days") or 0)
        if current and abs(new_days - current) >= 3:
            return True
    return False


def known_revision_operations(content: str) -> list[dict[str, Any]]:
    text = content.strip()
    operations: list[dict[str, Any]] = []
    if LOOSEN_DAY3_RE.search(text):
        operations.append({"op": "set_day_pace", "day_index": 3, "max_major_points": 1})
    if PREFER_TRANSIT_RE.search(text):
        operations.append({"op": "prefer_transit"})
    if QUIET_LODGING_RE.search(text):
        operations.append({"op": "replace_lodging"})
    return operations


def reply_for_known_operations(operations: list[dict[str, Any]]) -> str:
    ops = {item.get("op") for item in operations if isinstance(item, dict)}
    if "prefer_transit" in ops:
        return TRANSIT_REPLY
    if "replace_lodging" in ops:
        return LODGING_REPLY
    if "set_day_pace" in ops:
        return LOOSEN_DAY3_REPLY
    return REVISED_REPLY


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _haversine_m(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    angle = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(angle)))


def _estimate_leg(distance_m: float | None, *, walking: bool) -> dict[str, Any]:
    if distance_m is None:
        minutes = 15
        distance = None
    else:
        speed = WALK_SPEED_M_PER_MIN if walking else TRANSIT_SPEED_M_PER_MIN
        minutes = max(1, int(round(distance_m / speed)))
        distance = int(round(distance_m))
    mode: TransitMode = "walking" if walking else "transit"
    return {
        "mode": mode,
        "duration_min": minutes,
        "distance_m": distance,
        "summary": f"约 {minutes} 分钟（估算）",
        "source": "estimate",
    }


def _card_amount(card: dict[str, Any]) -> float | None:
    return _as_float(card.get("amount"))


def maybe_recompute_budget(payload: dict[str, Any]) -> None:
    amounts: list[float] = []
    for day in payload.get("days") or []:
        for card in day.get("cards") or []:
            amount = _card_amount(card)
            if amount is not None:
                amounts.append(amount)
    if not amounts:
        return
    budget = payload.setdefault("budget", {})
    total = sum(amounts)
    budget["total_amount"] = total
    cap = _as_float(budget.get("cap_amount"))
    if cap is not None:
        budget["over_cap"] = total > cap


def refresh_map_center(payload: dict[str, Any]) -> None:
    for day in payload.get("days") or []:
        for card in day.get("cards") or []:
            lng = _as_float(card.get("lng"))
            lat = _as_float(card.get("lat"))
            if lng is not None and lat is not None:
                payload["map_center"] = {"lng": lng, "lat": lat}
                return


def _normalize_card(raw: dict[str, Any]) -> dict[str, Any]:
    allowed = {"attraction", "lodging", "meal", "other"}
    card_type = raw.get("type") if raw.get("type") in allowed else "attraction"
    return {
        "id": str(raw.get("id") or ""),
        "type": card_type,
        "title": str(raw.get("title") or ""),
        "poi_id": raw.get("poi_id"),
        "lng": _as_float(raw.get("lng")),
        "lat": _as_float(raw.get("lat")),
        "address": raw.get("address"),
        "intro": raw.get("intro"),
        "photo_url": raw.get("photo_url"),
        "start_time": raw.get("start_time"),
        "suitable_for_children": bool(raw.get("suitable_for_children", True)),
    }


def _normalize_leg(raw: dict[str, Any]) -> dict[str, Any]:
    mode = raw.get("mode") if raw.get("mode") in {"transit", "walking", "mixed"} else "transit"
    source = raw.get("source") if raw.get("source") in {"amap", "estimate"} else "estimate"
    duration = raw.get("duration_min")
    distance = raw.get("distance_m")
    try:
        duration_min = int(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_min = None
    try:
        distance_m = int(distance) if distance is not None else None
    except (TypeError, ValueError):
        distance_m = None
    return {
        "mode": mode,
        "duration_min": duration_min,
        "distance_m": distance_m,
        "summary": str(raw.get("summary") or "约 15 分钟（估算）"),
        "source": source,
    }


def _domestic_checklist(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for item in items:
        text = str(item.get("text") or "")
        if any(marker in text for marker in PASSPORT_MARKERS):
            continue
        cleaned.append(
            {
                "id": str(item.get("id") or ""),
                "text": text,
                "relevant": bool(item.get("relevant", True)),
            }
        )
    return cleaned


def to_public(row: Itinerary, payload: dict[str, Any] | None = None) -> ItineraryPublic:
    data = payload or loads_payload(row.payload_json)
    budget_in = data.get("budget") if isinstance(data.get("budget"), dict) else {}
    categories = []
    for item in budget_in.get("categories") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "other")
        categories.append(
            {
                "key": key,
                "label": str(item.get("label") or CATEGORY_LABELS.get(key, key)),
                "amount": float(item.get("amount") or 0),
            }
        )
    cap = _as_float(budget_in.get("cap_amount"))
    total = _as_float(budget_in.get("total_amount")) or 0.0
    if cap is None:
        cap = 0.0
    map_center = data.get("map_center") if isinstance(data.get("map_center"), dict) else None
    if not map_center:
        refresh_map_center(data)
        map_center = data.get("map_center")
    if not map_center:
        map_center = {"lng": 104.2, "lat": 35.2}
    days = []
    for index, day in enumerate(data.get("days") or [], start=1):
        if not isinstance(day, dict):
            continue
        cards = [_normalize_card(card) for card in day.get("cards") or [] if isinstance(card, dict)]
        legs = [_normalize_leg(leg) for leg in day.get("legs") or [] if isinstance(leg, dict)]
        days.append(
            {
                "day_index": int(day.get("day_index") or index),
                "label": str(day.get("label") or f"第 {index} 天"),
                "date": day.get("date"),
                "cards": cards,
                "legs": legs[: max(0, len(cards) - 1)],
            }
        )
    suggestions = []
    for item in (data.get("quick_suggestions") or [])[:4]:
        if isinstance(item, dict) and item.get("text"):
            suggestions.append({"id": str(item.get("id") or ""), "text": str(item["text"])})
    pace = data.get("pace") or row.pace or "relaxed"
    if pace not in {"relaxed", "moderate", "packed"}:
        pace = "relaxed"
    return ItineraryPublic(
        id=row.id,
        conversation_id=row.conversation_id,
        title=str(data.get("title") or row.title),
        destination_city=str(data.get("destination_city") or row.destination_city or ""),
        origin_city=str(data.get("origin_city") or ""),
        duration_days=int(data.get("duration_days") or row.duration_days or len(days) or 0),
        pace=pace,
        companion_type=str(data.get("companion_type") or "unknown"),
        assumptions=list(data.get("assumptions") or []),
        days=days,
        budget=BudgetPublic(
            currency=str(budget_in.get("currency") or "CNY"),
            cap_amount=cap,
            total_amount=total,
            over_cap=bool(budget_in.get("over_cap")),
            includes_note=str(budget_in.get("includes_note") or ""),
            categories=categories,
        ),
        checklist=_domestic_checklist(list(data.get("checklist") or [])),
        map_center=MapPointPublic.model_validate(map_center),
        quick_suggestions=suggestions,
        status="ready",
        created_at=utc_iso(row.created_at),
        updated_at=utc_iso(row.updated_at),
    )


def to_list_item(row: Itinerary) -> ItineraryListItem:
    payload = loads_payload(row.payload_json)
    pace = row.pace or payload.get("pace") or "relaxed"
    if pace not in {"relaxed", "moderate", "packed"}:
        pace = "relaxed"
    return ItineraryListItem(
        id=row.id,
        title=row.title or str(payload.get("title") or "行程"),
        destination_city=str(row.destination_city or payload.get("destination_city") or ""),
        duration_days=int(row.duration_days or payload.get("duration_days") or 0),
        pace=pace,
        updated_at=utc_iso(row.updated_at),
        conversation_id=row.conversation_id,
    )


def _find_card(days: list[dict[str, Any]], card_id: str) -> tuple[int, int, dict[str, Any]] | None:
    for day_idx, day in enumerate(days):
        cards = day.get("cards") or []
        for card_idx, card in enumerate(cards):
            if isinstance(card, dict) and card.get("id") == card_id:
                return day_idx, card_idx, card
    return None


def _day_by_index(days: list[dict[str, Any]], day_index: int) -> dict[str, Any] | None:
    for day in days:
        if int(day.get("day_index") or 0) == day_index:
            return day
    return None


def apply_remove_card(payload: dict[str, Any], card_id: str) -> set[int]:
    days = payload.get("days") or []
    found = _find_card(days, card_id)
    if found is None:
        return set()
    day_idx, card_idx, _card = found
    day = days[day_idx]
    day["cards"].pop(card_idx)
    return {int(day.get("day_index") or day_idx + 1)}


def apply_set_day_pace(payload: dict[str, Any], day_index: int, max_major_points: int) -> set[int]:
    day = _day_by_index(payload.get("days") or [], day_index)
    if day is None:
        return set()
    cards = [card for card in day.get("cards") or [] if isinstance(card, dict)]
    majors = [card for card in cards if card.get("type") != "lodging"]
    lodging = [card for card in cards if card.get("type") == "lodging"]
    keep_major = majors[: max(0, max_major_points)]
    keep_ids = {card.get("id") for card in keep_major + lodging}
    next_cards = [card for card in cards if card.get("id") in keep_ids]
    if [card.get("id") for card in next_cards] == [card.get("id") for card in cards]:
        return set()
    day["cards"] = next_cards
    return {day_index}


def apply_prefer_transit(payload: dict[str, Any]) -> set[int]:
    payload["prefer_transit"] = True
    affected: set[int] = set()
    for day in payload.get("days") or []:
        if not isinstance(day, dict):
            continue
        try:
            day_index = int(day.get("day_index") or 0)
        except (TypeError, ValueError):
            continue
        cards = [card for card in day.get("cards") or [] if isinstance(card, dict)]
        legs = [leg for leg in day.get("legs") or [] if isinstance(leg, dict)]
        if day_index and (len(cards) >= 2 or any(leg.get("mode") == "walking" for leg in legs)):
            affected.add(day_index)
    if affected:
        return affected
    assumptions = [str(item) for item in (payload.get("assumptions") or [])]
    note = "白天少走路，多坐公交"
    if note not in assumptions:
        assumptions.append(note)
        payload["assumptions"] = assumptions
        first = next((day for day in payload.get("days") or [] if isinstance(day, dict)), None)
        if first is not None:
            try:
                return {int(first.get("day_index") or 1)}
            except (TypeError, ValueError):
                return {1}
    return set()


def apply_replace_lodging(payload: dict[str, Any]) -> set[int]:
    days = payload.get("days") or []
    for day in days:
        if not isinstance(day, dict):
            continue
        try:
            day_index = int(day.get("day_index") or 0)
        except (TypeError, ValueError):
            continue
        for card in day.get("cards") or []:
            if not isinstance(card, dict) or card.get("type") != "lodging":
                continue
            old_title = str(card.get("title") or "推荐住宿").strip() or "推荐住宿"
            if old_title == "更安静的推荐住宿":
                card["intro"] = "已按更安静的要求再调整一版，仅推荐不代订。"
            else:
                card["title"] = "更安静的推荐住宿"
                card["intro"] = f"由「{old_title}」换成更安静的推荐，仅推荐不代订。"
            return {day_index} if day_index else set()
    if not days or not isinstance(days[-1], dict):
        return set()
    last = days[-1]
    center = payload.get("map_center") if isinstance(payload.get("map_center"), dict) else {}
    last.setdefault("cards", []).append(
        {
            "id": new_id("card"),
            "type": "lodging",
            "title": "更安静的推荐住宿",
            "poi_id": None,
            "lng": _as_float(center.get("lng")),
            "lat": _as_float(center.get("lat")),
            "address": None,
            "intro": "按更安静的要求新增的推荐住宿，仅推荐不代订。",
            "photo_url": None,
            "start_time": None,
            "suitable_for_children": True,
        }
    )
    try:
        return {int(last.get("day_index") or len(days))}
    except (TypeError, ValueError):
        return {len(days)}


def apply_card_patch(payload: dict[str, Any], card_id: str, patch: CardPatch) -> set[int]:
    days = payload.get("days") or []
    found = _find_card(days, card_id)
    if found is None:
        raise NotFoundError(CARD_NOT_FOUND)
    day_idx, card_idx, card = found
    fields = patch.model_fields_set
    if "title" in fields and patch.title is not None:
        card["title"] = patch.title
    if "start_time" in fields:
        card["start_time"] = patch.start_time
    target_idx = day_idx
    if "day_index" in fields and patch.day_index is not None:
        target = _day_by_index(days, patch.day_index)
        if target is None:
            raise ValidationAppError("没有这一天")
        target_idx = days.index(target)
    membership_changed = target_idx != day_idx or "sort_order" in fields
    affected = {int(days[day_idx].get("day_index") or day_idx + 1)}
    if membership_changed:
        days[day_idx]["cards"].pop(card_idx)
        dest = days[target_idx].setdefault("cards", [])
        insert_at = len(dest)
        if "sort_order" in fields and patch.sort_order is not None:
            insert_at = max(0, min(patch.sort_order, len(dest)))
        dest.insert(insert_at, card)
        affected.add(int(days[target_idx].get("day_index") or target_idx + 1))
    return affected if membership_changed else set()


def apply_operations(payload: dict[str, Any], operations: list[dict[str, Any]]) -> set[int]:
    affected: set[int] = set()
    for item in operations:
        if not isinstance(item, dict):
            continue
        op = item.get("op")
        if op == "remove_card":
            card_id = str(item.get("card_id") or "")
            if card_id:
                affected |= apply_remove_card(payload, card_id)
            continue
        if op == "set_day_pace":
            try:
                day_index = int(item.get("day_index"))
                max_points = int(item.get("max_major_points"))
            except (TypeError, ValueError):
                continue
            affected |= apply_set_day_pace(payload, day_index, max_points)
            continue
        if op == "prefer_transit":
            affected |= apply_prefer_transit(payload)
            continue
        if op == "replace_lodging":
            affected |= apply_replace_lodging(payload)
    return affected


async def _lookup_citycode(city: str, client: AmapClient) -> str | None:
    if not city:
        return None
    plugin = GeocodeCityPlugin(client=client)
    result = await plugin.execute(address=city)
    if not result or not isinstance(result.data, dict):
        return None
    code = str(result.data.get("citycode") or "").strip()
    return code or None


def _duration_min_from_amap(duration: Any) -> int | None:
    number = _as_float(duration)
    if number is None:
        return None
    if number >= 120:
        return max(1, int(round(number / 60)))
    return max(1, int(round(number)))


async def default_resolve_leg(
    origin: dict[str, Any],
    dest: dict[str, Any],
    *,
    city: str,
    citycode: str | None,
    prefer_transit: bool = False,
) -> dict[str, Any]:
    lng1, lat1 = _as_float(origin.get("lng")), _as_float(origin.get("lat"))
    lng2, lat2 = _as_float(dest.get("lng")), _as_float(dest.get("lat"))
    distance = None
    if None not in {lng1, lat1, lng2, lat2}:
        distance = _haversine_m(lng1, lat1, lng2, lat2)
    walking = (
        distance is not None
        and distance < settings.walk_threshold_m
        and not prefer_transit
    )
    if not settings.amap_web_key:
        return _estimate_leg(distance, walking=walking)
    client = AmapClient(
        api_key=settings.amap_web_key,
        timeout=settings.amap_timeout_seconds,
    )
    origin_pt = f"{lng1},{lat1}" if None not in {lng1, lat1} else ""
    dest_pt = f"{lng2},{lat2}" if None not in {lng2, lat2} else ""
    if not origin_pt or not dest_pt:
        return _estimate_leg(distance, walking=walking)
    try:
        if walking:
            plugin = RouteWalkingPlugin(client=client)
            result = await plugin.execute(origin=origin_pt, destination=dest_pt)
        else:
            code = citycode or await _lookup_citycode(city, client)
            if not code:
                logger.info("公交缺 citycode，该腿改用估算")
                return _estimate_leg(distance, walking=False)
            plugin = RouteTransitPlugin(client=client)
            result = await plugin.execute(
                origin=origin_pt,
                destination=dest_pt,
                city1=code,
                city2=code,
            )
    except Exception:
        logger.exception("高德补腿失败，改用估算")
        return _estimate_leg(distance, walking=walking)
    if not result or not isinstance(result.data, dict):
        logger.info("高德补腿未成功，改用估算")
        return _estimate_leg(distance, walking=walking)
    amap_distance = _as_float(result.data.get("distance"))
    minutes = _duration_min_from_amap(result.data.get("duration"))
    if amap_distance is None or minutes is None:
        return _estimate_leg(distance, walking=walking)
    mode: TransitMode = "walking" if walking else "transit"
    label = "步行" if walking else "公交"
    return {
        "mode": mode,
        "duration_min": minutes,
        "distance_m": int(round(amap_distance)),
        "summary": f"{label}约 {minutes} 分钟",
        "source": "amap",
    }


async def resolve_leg(
    origin: dict[str, Any],
    dest: dict[str, Any],
    *,
    city: str,
    citycode: str | None,
    prefer_transit: bool = False,
) -> dict[str, Any]:
    if _leg_resolver is not None:
        return await _leg_resolver(origin, dest, city=city, citycode=citycode)
    return await default_resolve_leg(
        origin,
        dest,
        city=city,
        citycode=citycode,
        prefer_transit=prefer_transit,
    )


async def recalc_days(payload: dict[str, Any], day_indexes: set[int]) -> None:
    if not day_indexes:
        return
    city = str(payload.get("destination_city") or "")
    citycode = None
    prefer_transit = bool(payload.get("prefer_transit"))
    for day in payload.get("days") or []:
        if int(day.get("day_index") or 0) not in day_indexes:
            continue
        cards = [card for card in day.get("cards") or [] if isinstance(card, dict)]
        legs: list[dict[str, Any]] = []
        for index in range(len(cards) - 1):
            legs.append(
                await resolve_leg(
                    cards[index],
                    cards[index + 1],
                    city=city,
                    citycode=citycode,
                    prefer_transit=prefer_transit,
                )
            )
        day["legs"] = legs


class ItineraryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_ready(self, page: int, page_size: int) -> tuple[list[ItineraryListItem], int]:
        total = await self.db.scalar(
            select(func.count()).select_from(Itinerary).where(Itinerary.status == "ready")
        )
        result = await self.db.execute(
            select(Itinerary)
            .where(Itinerary.status == "ready")
            .order_by(Itinerary.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list(result.scalars().all())
        return [to_list_item(row) for row in rows], int(total or 0)

    async def get_ready(self, itinerary_id: str) -> Itinerary:
        row = await self.db.get(Itinerary, itinerary_id)
        if row is None or row.status != "ready":
            raise NotFoundError(ITINERARY_NOT_FOUND)
        return row

    async def get_public(self, itinerary_id: str) -> ItineraryPublic:
        row = await self.get_ready(itinerary_id)
        return to_public(row)

    async def _save(self, row: Itinerary, payload: dict[str, Any]) -> ItineraryPublic:
        now = utcnow()
        payload["updated_at"] = now.isoformat(timespec="seconds").replace("+00:00", "Z")
        payload["status"] = "ready"
        maybe_recompute_budget(payload)
        refresh_map_center(payload)
        row.payload_json = dumps_payload(payload)
        row.updated_at = now
        row.title = str(payload.get("title") or row.title)
        row.destination_city = payload.get("destination_city") or row.destination_city
        row.duration_days = payload.get("duration_days") or row.duration_days
        row.pace = payload.get("pace") or row.pace
        row.status = "ready"
        await self.db.flush()
        await self.db.refresh(row)
        return to_public(row, payload)

    async def patch_card(
        self, itinerary_id: str, card_id: str, patch: CardPatch
    ) -> ItineraryPublic:
        row = await self.get_ready(itinerary_id)
        payload = loads_payload(row.payload_json)
        affected = apply_card_patch(payload, card_id, patch)
        await recalc_days(payload, affected)
        return await self._save(row, payload)

    async def delete_card(self, itinerary_id: str, card_id: str) -> ItineraryPublic:
        row = await self.get_ready(itinerary_id)
        payload = loads_payload(row.payload_json)
        affected = apply_remove_card(payload, card_id)
        if not affected:
            raise NotFoundError(CARD_NOT_FOUND)
        await recalc_days(payload, affected)
        return await self._save(row, payload)

    async def apply_revision(
        self, itinerary_id: str, operations: list[dict[str, Any]]
    ) -> tuple[ItineraryPublic, bool]:
        row = await self.get_ready(itinerary_id)
        payload = loads_payload(row.payload_json)
        affected = apply_operations(payload, operations)
        if not affected:
            return to_public(row, payload), False
        await recalc_days(payload, affected)
        public = await self._save(row, payload)
        return public, True
