from typing import Any

from pycore.plugins import BasePlugin, PluginResult

from .amap import (
    REASON_UNAVAILABLE,
    AmapClient,
    amap_number,
    amap_text,
    format_lnglat,
    observation_fail,
    observation_ok,
)


class RouteTransitPlugin(BasePlugin):
    name: str = "route_transit"
    description: str = "查询公交路径距离、耗时与票价。失败时由行程侧估算。"
    parameters: dict = {
        "type": "object",
        "properties": {
            "origin": {"type": "string", "description": "起点 经度,纬度"},
            "destination": {"type": "string", "description": "终点 经度,纬度"},
            "city1": {"type": "string", "description": "起点 citycode"},
            "city2": {"type": "string", "description": "终点 citycode"},
        },
        "required": ["origin", "destination", "city1", "city2"],
    }
    client: Any = None

    async def execute(
        self,
        origin: str = "",
        destination: str = "",
        city1: str = "",
        city2: str = "",
        **kwargs,
    ) -> PluginResult:
        client: AmapClient = self.client or AmapClient()
        if not amap_text(city1) or not amap_text(city2):
            return observation_fail("city1 与 city2（citycode）同时必填", client)
        try:
            origin_pt = format_lnglat(amap_text(origin))
            dest_pt = format_lnglat(amap_text(destination))
        except (TypeError, ValueError):
            return observation_fail("origin/destination 须为 经度,纬度", client)
        result = await client.get(
            "/v5/direction/transit/integrated",
            {
                "origin": origin_pt,
                "destination": dest_pt,
                "city1": city1,
                "city2": city2,
                "show_fields": "cost",
            },
        )
        if not result:
            return result
        route = result.data.get("route") if isinstance(result.data, dict) else None
        transits = route.get("transits") if isinstance(route, dict) else None
        if not isinstance(transits, list) or not transits or not isinstance(transits[0], dict):
            return observation_fail(
                "公交路线不可用，允许估算",
                client,
                reason=REASON_UNAVAILABLE,
            )
        first = transits[0]
        cost = first.get("cost") if isinstance(first.get("cost"), dict) else {}
        distance = amap_number(first.get("distance"))
        duration = amap_number(cost.get("duration"))
        if distance is None or duration is None:
            return observation_fail(
                "公交路线不可用，允许估算",
                client,
                reason=REASON_UNAVAILABLE,
            )
        return observation_ok(
            {
                "distance": distance,
                "duration": duration,
                "transit_fee": amap_number(cost.get("transit_fee")),
            },
            client,
        )
