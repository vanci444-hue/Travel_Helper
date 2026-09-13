from typing import Any

from pycore.plugins import BasePlugin, PluginResult

from .amap import (
    REASON_NOT_FOUND,
    AmapClient,
    amap_text,
    observation_fail,
    observation_ok,
)


class GeocodeCityPlugin(BasePlugin):
    name: str = "geocode_city"
    description: str = "将国内城市或地址解析为 location、adcode、citycode。"
    parameters: dict = {
        "type": "object",
        "properties": {
            "address": {"type": "string", "description": "城市名或详细地址"},
            "city": {"type": "string", "description": "可选，限定城市"},
        },
        "required": ["address"],
    }
    client: Any = None

    async def execute(self, address: str = "", city: str = "", **kwargs) -> PluginResult:
        client: AmapClient = self.client or AmapClient()
        if not amap_text(address):
            return observation_fail("缺少 address", client)
        result = await client.get(
            "/v3/geocode/geo",
            {"address": address, "city": city},
        )
        if not result:
            return result
        geocodes = result.data.get("geocodes") if isinstance(result.data, dict) else None
        if not isinstance(geocodes, list) or not geocodes:
            return observation_fail(
                "找不到该目的地",
                client,
                reason=REASON_NOT_FOUND,
            )
        first = geocodes[0] if isinstance(geocodes[0], dict) else {}
        location = amap_text(first.get("location"))
        adcode = amap_text(first.get("adcode"))
        if not location or not adcode:
            return observation_fail(
                "找不到该目的地",
                client,
                reason=REASON_NOT_FOUND,
            )
        return observation_ok(
            {
                "location": location,
                "adcode": adcode,
                "citycode": amap_text(first.get("citycode")),
            },
            client,
        )
