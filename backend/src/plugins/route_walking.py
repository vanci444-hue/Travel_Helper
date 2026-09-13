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


class RouteWalkingPlugin(BasePlugin):
    name: str = "route_walking"
    description: str = "查询步行路径距离（米）与耗时（秒）。失败时由行程侧估算。"
    parameters: dict = {
        "type": "object",
        "properties": {
            "origin": {"type": "string", "description": "起点 经度,纬度"},
            "destination": {"type": "string", "description": "终点 经度,纬度"},
        },
        "required": ["origin", "destination"],
    }
    client: Any = None

    async def execute(
        self,
        origin: str = "",
        destination: str = "",
        **kwargs,
    ) -> PluginResult:
        client: AmapClient = self.client or AmapClient()
        try:
            origin_pt = format_lnglat(amap_text(origin))
            dest_pt = format_lnglat(amap_text(destination))
        except (TypeError, ValueError):
            return observation_fail("origin/destination 须为 经度,纬度", client)
        result = await client.get(
            "/v5/direction/walking",
            {"origin": origin_pt, "destination": dest_pt, "show_fields": "cost"},
        )
        if not result:
            return result
        route = result.data.get("route") if isinstance(result.data, dict) else None
        paths = route.get("paths") if isinstance(route, dict) else None
        if not isinstance(paths, list) or not paths or not isinstance(paths[0], dict):
            return observation_fail(
                "步行路线不可用，允许估算",
                client,
                reason=REASON_UNAVAILABLE,
            )
        first = paths[0]
        cost = first.get("cost") if isinstance(first.get("cost"), dict) else {}
        distance = amap_number(first.get("distance"))
        duration = amap_number(cost.get("duration"))
        if distance is None or duration is None:
            return observation_fail(
                "步行路线不可用，允许估算",
                client,
                reason=REASON_UNAVAILABLE,
            )
        return observation_ok({"distance": distance, "duration": duration}, client)
