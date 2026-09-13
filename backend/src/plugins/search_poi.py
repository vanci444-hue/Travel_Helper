from typing import Any

from pycore.plugins import BasePlugin, PluginResult

from .amap import AmapClient, amap_text, observation_fail, observation_ok


def _pick_poi(raw: dict[str, Any]) -> dict[str, Any]:
    business = raw.get("business") if isinstance(raw.get("business"), dict) else {}
    photos_in = raw.get("photos") if isinstance(raw.get("photos"), list) else []
    photos = []
    for item in photos_in:
        if isinstance(item, dict):
            url = amap_text(item.get("url"))
            if url:
                photos.append(url)
    return {
        "id": amap_text(raw.get("id")),
        "name": amap_text(raw.get("name")),
        "location": amap_text(raw.get("location")),
        "address": amap_text(raw.get("address")),
        "type": amap_text(raw.get("type")),
        "opentime": amap_text(business.get("opentime_week") or business.get("opentime_today")),
        "rating": amap_text(business.get("rating")),
        "cost": amap_text(business.get("cost")),
        "tag": amap_text(business.get("tag")),
        "photos": photos,
    }


class SearchPoiPlugin(BasePlugin):
    name: str = "search_poi"
    description: str = "按关键词或类型检索国内 POI，不编造结果。"
    parameters: dict = {
        "type": "object",
        "properties": {
            "keywords": {"type": "string", "description": "检索关键词"},
            "types": {"type": "string", "description": "POI 类型编码，可与 keywords 二选一"},
            "region": {"type": "string", "description": "可选，城市或 adcode"},
        },
        "required": [],
    }
    client: Any = None

    async def execute(
        self,
        keywords: str = "",
        types: str = "",
        region: str = "",
        **kwargs,
    ) -> PluginResult:
        client: AmapClient = self.client or AmapClient()
        if not amap_text(keywords) and not amap_text(types):
            return observation_fail("keywords 与 types 至少填一项", client)
        result = await client.get(
            "/v5/place/text",
            {
                "keywords": keywords,
                "types": types,
                "region": region,
                "show_fields": "business,photos",
            },
            poi_count_from="pois",
        )
        if not result:
            return result
        raw_pois = result.data.get("pois") if isinstance(result.data, dict) else None
        pois = [_pick_poi(item) for item in raw_pois or [] if isinstance(item, dict)]
        return observation_ok({"pois": pois}, client)
