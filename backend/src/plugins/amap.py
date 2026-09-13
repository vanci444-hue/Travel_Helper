"""高德 Web 服务共用客户端：解析、脱敏日志、空数组字段。"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from pycore.core import get_logger
from pycore.plugins import BasePlugin, PluginRegistry, PluginResult

AMAP_BASE_URL = "https://restapi.amap.com"
SUCCESS_STATUS = "1"
SUCCESS_INFOCODE = "10000"
POLYLINE_KEYS = frozenset({"polyline", "polylines"})
REASON_UNAVAILABLE = "amap_unavailable"
REASON_NOT_FOUND = "destination_not_found"
REASON_POI_EMPTY = "poi_empty"


def amap_text(value: Any) -> str:
    """高德空字段常为 []，收成空字符串。"""
    if value is None or value == [] or value == {}:
        return ""
    if isinstance(value, list):
        return ""
    return str(value).strip()


def amap_number(value: Any) -> Optional[int | float]:
    text = amap_text(value)
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number.is_integer():
        return int(number)
    return number


def format_lnglat(value: str) -> str:
    lng_s, lat_s = value.split(",", 1)
    lng = round(float(lng_s.strip()), 6)
    lat = round(float(lat_s.strip()), 6)
    return f"{lng},{lat}"


def is_amap_ok(payload: dict[str, Any]) -> bool:
    return (
        str(payload.get("status", "")) == SUCCESS_STATUS
        and str(payload.get("infocode", "")) == SUCCESS_INFOCODE
    )


def sanitize_observation(value: Any, api_key: str = "") -> Any:
    """观察结果不得含 Key 或完整 polyline。"""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in POLYLINE_KEYS or lowered == "key":
                continue
            cleaned[key] = sanitize_observation(item, api_key)
        return cleaned
    if isinstance(value, list):
        return [sanitize_observation(item, api_key) for item in value]
    if isinstance(value, str) and api_key and api_key in value:
        return value.replace(api_key, "[redacted]")
    return value


def log_amap_call(path: str, infocode: str, poi_count: Optional[int] = None) -> None:
    fields: dict[str, Any] = {"path": path, "infocode": infocode}
    if poi_count is not None:
        fields["poi_count"] = poi_count
    get_logger().info("amap", **fields)


class AmapClient:
    def __init__(
        self,
        api_key: str = "",
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key or ""
        self.timeout = timeout
        self.transport = transport

    async def get(
        self,
        path: str,
        params: dict[str, Any],
        *,
        poi_count_from: str | None = None,
    ) -> PluginResult:
        if not self.api_key:
            log_amap_call(path, "missing_key")
            return PluginResult.fail(
                "地图服务不可用",
                reason=REASON_UNAVAILABLE,
                infocode="missing_key",
            )

        query = {
            "key": self.api_key,
            "output": "json",
            **{k: v for k, v in params.items() if v not in (None, "")},
        }
        url = f"{AMAP_BASE_URL}{path}"
        try:
            async with httpx.AsyncClient(
                trust_env=False,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = await client.get(url, params=query)
        except httpx.TimeoutException:
            log_amap_call(path, "timeout")
            return PluginResult.fail(
                "高德请求超时",
                reason=REASON_UNAVAILABLE,
                infocode="timeout",
            )
        except httpx.HTTPError:
            log_amap_call(path, "http_error")
            return PluginResult.fail(
                "高德服务不可用",
                reason=REASON_UNAVAILABLE,
                infocode="http_error",
            )

        logged_path = urlparse(str(response.url)).path or path
        try:
            payload = response.json()
        except ValueError:
            log_amap_call(logged_path, "invalid_json")
            return PluginResult.fail(
                "高德响应无法解析",
                reason=REASON_UNAVAILABLE,
                infocode="invalid_json",
            )
        if not isinstance(payload, dict):
            log_amap_call(logged_path, "invalid_json")
            return PluginResult.fail(
                "高德响应无法解析",
                reason=REASON_UNAVAILABLE,
                infocode="invalid_json",
            )

        infocode = amap_text(payload.get("infocode")) or str(response.status_code)
        poi_count = None
        if poi_count_from:
            items = payload.get(poi_count_from)
            poi_count = len(items) if isinstance(items, list) else 0
        log_amap_call(logged_path, infocode, poi_count)

        if not is_amap_ok(payload):
            info = amap_text(payload.get("info")) or "高德返回失败"
            return PluginResult.fail(
                f"{info} infocode={infocode}",
                reason=REASON_UNAVAILABLE,
                infocode=infocode,
            )
        return PluginResult.ok(payload, infocode=infocode)


def observation_ok(data: Any, client: AmapClient, **metadata: Any) -> PluginResult:
    return PluginResult.ok(sanitize_observation(data, client.api_key), **metadata)


def observation_fail(message: str, client: AmapClient, **metadata: Any) -> PluginResult:
    return PluginResult.fail(
        sanitize_observation(message, client.api_key),
        **{k: sanitize_observation(v, client.api_key) for k, v in metadata.items()},
    )


def create_amap_registry(
    api_key: str = "",
    timeout: float = 10.0,
    transport: httpx.BaseTransport | None = None,
    settings: Any = None,
) -> PluginRegistry:
    if settings is not None:
        api_key = api_key or getattr(settings, "amap_web_key", "") or ""
        timeout = getattr(settings, "amap_timeout_seconds", timeout)
    client = AmapClient(api_key=api_key, timeout=timeout, transport=transport)
    from .geocode_city import GeocodeCityPlugin
    from .get_poi_detail import GetPoiDetailPlugin
    from .get_weather import GetWeatherPlugin
    from .route_transit import RouteTransitPlugin
    from .route_walking import RouteWalkingPlugin
    from .search_poi import SearchPoiPlugin

    registry = PluginRegistry()
    registry.register_all(
        GeocodeCityPlugin(client=client),
        SearchPoiPlugin(client=client),
        GetPoiDetailPlugin(client=client),
        GetWeatherPlugin(client=client),
        RouteWalkingPlugin(client=client),
        RouteTransitPlugin(client=client),
    )
    return registry


def create_amap_plugins(
    api_key: str = "",
    timeout: float = 10.0,
    transport: httpx.BaseTransport | None = None,
    settings: Any = None,
) -> list[BasePlugin]:
    registry = create_amap_registry(
        api_key=api_key,
        timeout=timeout,
        transport=transport,
        settings=settings,
    )
    return list(registry)
