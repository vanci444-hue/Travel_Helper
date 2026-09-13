from typing import Any

from pycore.plugins import BasePlugin, PluginResult

from .amap import AmapClient, amap_text, observation_fail, observation_ok


class GetWeatherPlugin(BasePlugin):
    name: str = "get_weather"
    description: str = "按 adcode 查询国内天气预报（昼夜天气与气温）。"
    parameters: dict = {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "城市 adcode"},
        },
        "required": ["city"],
    }
    client: Any = None

    async def execute(self, city: str = "", **kwargs) -> PluginResult:
        client: AmapClient = self.client or AmapClient()
        adcode = amap_text(city)
        if not adcode:
            return observation_fail("缺少 city（adcode）", client)
        result = await client.get(
            "/v3/weather/weatherInfo",
            {"city": adcode, "extensions": "all"},
        )
        if not result:
            return result
        payload = result.data if isinstance(result.data, dict) else {}
        forecasts = payload.get("forecasts")
        if not isinstance(forecasts, list) or not forecasts:
            forecast = payload.get("forecast")
            forecasts = [forecast] if isinstance(forecast, dict) else []
        first = forecasts[0] if forecasts and isinstance(forecasts[0], dict) else {}
        raw_casts = first.get("casts")
        casts = []
        for item in raw_casts or []:
            if not isinstance(item, dict):
                continue
            casts.append(
                {
                    "date": amap_text(item.get("date")),
                    "dayweather": amap_text(item.get("dayweather")),
                    "nightweather": amap_text(item.get("nightweather")),
                    "daytemp": amap_text(item.get("daytemp")),
                    "nighttemp": amap_text(item.get("nighttemp")),
                }
            )
        return observation_ok({"casts": casts}, client)
