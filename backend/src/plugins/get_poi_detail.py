from typing import Any

from pycore.plugins import BasePlugin, PluginResult

from .amap import AmapClient, amap_text, observation_fail, observation_ok
from .search_poi import _pick_poi


class GetPoiDetailPlugin(BasePlugin):
    name: str = "get_poi_detail"
    description: str = "按 POI ID 取详情；介绍优先用 business/tag。"
    parameters: dict = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "高德 POI ID"},
        },
        "required": ["id"],
    }
    client: Any = None

    async def execute(self, id: str = "", **kwargs) -> PluginResult:
        client: AmapClient = self.client or AmapClient()
        poi_id = amap_text(id)
        if not poi_id:
            return observation_fail("缺少 id", client)
        result = await client.get(
            "/v5/place/detail",
            {"id": poi_id, "show_fields": "business,photos"},
            poi_count_from="pois",
        )
        if not result:
            return result
        raw_pois = result.data.get("pois") if isinstance(result.data, dict) else None
        if not isinstance(raw_pois, list) or not raw_pois or not isinstance(raw_pois[0], dict):
            return observation_ok({"poi": None}, client)
        poi = _pick_poi(raw_pois[0])
        intro = poi.get("tag") or ""
        poi["intro"] = intro
        return observation_ok({"poi": poi}, client)
