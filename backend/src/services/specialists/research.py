"""目的地研究专员：千问 Plus、关思考、工具最多 8 轮。"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from src.config.settings import settings

ROLE = "destination_research"
ALLOWED_TOOLS = ("geocode_city", "search_poi", "get_poi_detail", "get_weather")
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "destination_research.md"
REASON_CODES = {
    "destination_not_found",
    "poi_empty",
    "amap_unavailable",
    "iteration_limit",
    "model_error",
}

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


def attach_poi_coords(poi: dict[str, Any]) -> dict[str, Any]:
    lng = _as_float(poi.get("lng"))
    lat = _as_float(poi.get("lat"))
    if lng is None or lat is None:
        location = str(poi.get("location") or "")
        if "," in location:
            left, right = location.split(",", 1)
            lng = _as_float(left.strip())
            lat = _as_float(right.strip())
    if lng is not None:
        poi["lng"] = lng
    if lat is not None:
        poi["lat"] = lat
    return poi


def parse_result(raw: dict[str, Any] | None) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    if data.get("ok") is True:
        raw_pois = data.get("pois") if isinstance(data.get("pois"), list) else []
        pois = [attach_poi_coords(item) for item in raw_pois if isinstance(item, dict)]
        return {
            "ok": True,
            "destination_city": str(data.get("destination_city") or "").strip(),
            "weather_summary": str(data.get("weather_summary") or "").strip(),
            "pois": pois,
            "warnings": data.get("warnings") if isinstance(data.get("warnings"), list) else [],
            "summary": f"已收集{len(pois)} 处点位" if pois else "点位与天气可用",
            "reason_code": None,
            "reason": None,
        }
    code = str(data.get("reason_code") or "model_error")
    if code not in REASON_CODES:
        code = "model_error"
    reason = str(data.get("reason") or "").strip()
    return {
        "ok": False,
        "reason_code": code,
        "reason": reason,
        "summary": reason or "目的地研究未完成",
    }


def _research_constraint(intake: dict[str, Any]) -> str:
    pace = intake.get("pace") or "moderate"
    companion = intake.get("companion_type") or "unknown"
    pace_hint = {
        "relaxed": "轻松：约 6 个带坐标候选后立刻收束",
        "moderate": "适中：约 8 个带坐标候选后立刻收束",
        "packed": "紧凑：约 8–10 个带坐标候选后立刻收束，不要耗尽 8 轮",
    }.get(str(pace), "按节奏列候选")
    companion_hint = {
        "parent_child": "亲子：公园/动物园/博物馆等亲子向，标 suitable_for_children",
        "couple": "情侣：夜景、散步、咖啡馆、观景，不要只堆带娃项目",
        "family": "家庭：适合各年龄段的景区与休息点",
        "friends": "朋友：可打卡、可散步的城市点",
        "solo": "独行：节奏自在的城市点",
    }.get(str(companion), "按同行选点")
    return (
        f"【筛选】{companion_hint}。{pace_hint}。"
        "每个 poi 写入工具给的 location 或 lng/lat。"
        "最多 8 轮工具，已有 6 个以上带坐标的点必须立刻输出成功 json。"
    )


async def run_research(intake: dict[str, Any], *, run_loop: LoopFn) -> dict[str, Any]:
    user = (
        _research_constraint(intake)
        + "\n请根据以下问诊 json 研究目的地，先工具后结论：\n"
        + json.dumps(intake, ensure_ascii=False)
    )
    raw = await run_loop(
        role=ROLE,
        provider="qwen",
        system_prompt=load_prompt(),
        user_content=user,
        tools=ALLOWED_TOOLS,
        max_iter=settings.max_tool_iterations_research,
        thinking_enabled=False,
        json_object=True,
    )
    return parse_result(raw)
