"""T-006：mock httpx 验解析与脱敏。不把 mock 当成真实地理编码通过。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pycore.core.logger import Logger, LoggerConfig, LogLevel  # noqa: E402
from pycore.plugins import BasePlugin, PluginRegistry  # noqa: E402
from plugins.amap import create_amap_registry  # noqa: E402

Logger.reset()
Logger.configure(
    LoggerConfig(console_enabled=False, file_enabled=False, level=LogLevel.INFO)
)
from plugins.geocode_city import GeocodeCityPlugin  # noqa: E402
from plugins.get_poi_detail import GetPoiDetailPlugin  # noqa: E402
from plugins.get_weather import GetWeatherPlugin  # noqa: E402
from plugins.route_transit import RouteTransitPlugin  # noqa: E402
from plugins.route_walking import RouteWalkingPlugin  # noqa: E402
from plugins.search_poi import SearchPoiPlugin  # noqa: E402

FAKE_KEY = "unit-test-amap-key-do-not-log"
LONG_POLYLINE = "120.153576,30.287459;" * 80 + "120.16,30.29"
PLUGIN_DIR = SRC_DIR / "plugins"
PLUGIN_NAMES = (
    "geocode_city",
    "search_poi",
    "get_poi_detail",
    "get_weather",
    "route_walking",
    "route_transit",
)


def _contains_secret(value) -> bool:
    return FAKE_KEY in json.dumps(value, ensure_ascii=False, default=str)


def _json_response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def _success_payloads(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/v3/geocode/geo":
        return _json_response(
            {
                "status": "1",
                "infocode": "10000",
                "geocodes": [
                    {
                        "location": "120.153576,30.287459",
                        "adcode": "330100",
                        "citycode": "0571",
                        "city": [],
                        "formatted_address": [],
                    }
                ],
            }
        )
    if path == "/v5/place/text":
        return _json_response(
            {
                "status": "1",
                "infocode": "10000",
                "pois": [
                    {
                        "id": "B000A7BD6C",
                        "name": "西湖",
                        "location": "120.143,30.242",
                        "address": [],
                        "type": "风景名胜",
                        "business": {
                            "opentime_week": "全天",
                            "rating": "4.8",
                            "cost": "0",
                            "tag": "湖泊",
                        },
                        "photos": [{"url": "https://example.com/xihu.jpg"}],
                    }
                ],
            }
        )
    if path == "/v5/place/detail":
        return _json_response(
            {
                "status": "1",
                "infocode": "10000",
                "pois": [
                    {
                        "id": "B000A7BD6C",
                        "name": "西湖",
                        "location": "120.143,30.242",
                        "address": "杭州市西湖区",
                        "type": "风景名胜",
                        "business": {"tag": "湖泊"},
                        "photos": [],
                    }
                ],
            }
        )
    if path == "/v3/weather/weatherInfo":
        return _json_response(
            {
                "status": "1",
                "infocode": "10000",
                "forecasts": [
                    {
                        "casts": [
                            {
                                "date": "2026-09-13",
                                "dayweather": "晴",
                                "nightweather": "多云",
                                "daytemp": "30",
                                "nighttemp": "20",
                            }
                        ]
                    }
                ],
            }
        )
    if path == "/v5/direction/walking":
        return _json_response(
            {
                "status": "1",
                "infocode": "10000",
                "route": {
                    "paths": [
                        {
                            "distance": "1200",
                            "cost": {"duration": "900"},
                            "polyline": LONG_POLYLINE,
                            "steps": [{"polyline": LONG_POLYLINE}],
                        }
                    ]
                },
            }
        )
    if path == "/v5/direction/transit/integrated":
        return _json_response(
            {
                "status": "1",
                "infocode": "10000",
                "route": {
                    "transits": [
                        {
                            "distance": "5000",
                            "cost": {"duration": "1800", "transit_fee": "4"},
                            "polyline": LONG_POLYLINE,
                        }
                    ]
                },
            }
        )
    return _json_response({"status": "0", "infocode": "20000", "info": "INVALID_PARAMS"})


def _registry(handler) -> PluginRegistry:
    return create_amap_registry(
        api_key=FAKE_KEY,
        timeout=2.0,
        transport=httpx.MockTransport(handler),
    )


def _dump(result) -> dict:
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return result.dict()


@pytest.fixture(autouse=True)
def _never_read_amap_env(monkeypatch):
    import os

    original = os.getenv

    def _guarded(name, default=None):
        key = str(name)
        if "AMAP" in key.upper() or key.lower() == "amap_web_key":
            raise AssertionError(f"插件测试不得读高德环境变量: {name}")
        return original(name, default)

    monkeypatch.setattr("os.getenv", _guarded)
    monkeypatch.delenv("AMAP_WEB_KEY", raising=False)
    monkeypatch.delenv("amap_web_key", raising=False)


@pytest.mark.asyncio
async def test_registry_executes_six_base_plugins():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return _success_payloads(request)

    registry = _registry(handler)
    assert all(isinstance(plugin, BasePlugin) for plugin in registry)
    assert set(registry.list_plugins()) == set(PLUGIN_NAMES)

    geo = await registry.execute("geocode_city", address="杭州")
    poi = await registry.execute("search_poi", keywords="西湖", region="330100")
    detail = await registry.execute("get_poi_detail", id="B000A7BD6C")
    weather = await registry.execute("get_weather", city="330100")
    walk = await registry.execute(
        "route_walking",
        origin="120.1535761,30.2874599",
        destination="120.16,30.29",
    )
    transit = await registry.execute(
        "route_transit",
        origin="120.15,30.28",
        destination="120.16,30.29",
        city1="0571",
        city2="0571",
    )

    assert geo and geo.data["location"] == "120.153576,30.287459"
    assert geo.data["adcode"] == "330100"
    assert geo.data["citycode"] == "0571"
    assert poi.data["pois"][0]["id"] == "B000A7BD6C"
    assert poi.data["pois"][0]["name"] == "西湖"
    assert poi.data["pois"][0]["location"] == "120.143,30.242"
    assert poi.data["pois"][0]["address"] == ""
    assert weather.data["casts"][0]["dayweather"] == "晴"
    assert walk.data == {"distance": 1200, "duration": 900}
    assert transit.data == {"distance": 5000, "duration": 1800, "transit_fee": 4}
    assert detail.data["poi"]["intro"] == "湖泊"
    assert seen == [
        "/v3/geocode/geo",
        "/v5/place/text",
        "/v5/place/detail",
        "/v3/weather/weatherInfo",
        "/v5/direction/walking",
        "/v5/direction/transit/integrated",
    ]
    for result in (geo, poi, detail, weather, walk, transit):
        dumped = json.dumps(_dump(result), ensure_ascii=False)
        assert FAKE_KEY not in dumped
        assert LONG_POLYLINE not in dumped
        assert "polyline" not in dumped


@pytest.mark.asyncio
async def test_status_or_infocode_failure_has_no_key_or_polyline():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            {
                "status": "0",
                "infocode": "10044",
                "info": "USER_DAILY_QUERY_OVER_LIMIT",
                "route": {"paths": [{"polyline": LONG_POLYLINE}]},
            }
        )

    result = await _registry(handler).execute("geocode_city", address="杭州")
    assert not result
    assert "10044" in (result.error or "")
    assert FAKE_KEY not in (result.error or "")
    assert LONG_POLYLINE not in (result.error or "")
    assert result.metadata.get("reason") == "amap_unavailable"


@pytest.mark.asyncio
async def test_timeout_is_failure_not_fabricated_poi():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    result = await _registry(handler).execute("search_poi", keywords="西湖")
    assert not result
    assert result.metadata.get("reason") == "amap_unavailable"
    assert "poi" not in json.dumps(result.data, default=str).lower() or result.data in (None, {})


@pytest.mark.asyncio
async def test_empty_search_does_not_invent_poi():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({"status": "1", "infocode": "10000", "pois": []})

    result = await _registry(handler).execute("search_poi", keywords="不存在的点")
    assert result
    assert result.data == {"pois": []}


@pytest.mark.asyncio
async def test_empty_geocode_is_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({"status": "1", "infocode": "10000", "geocodes": []})

    result = await _registry(handler).execute("geocode_city", address="乱码地名")
    assert not result
    assert result.metadata.get("reason") == "destination_not_found"


@pytest.mark.asyncio
async def test_logs_only_path_infocode_and_poi_count():
    mock_logger = MagicMock()

    def handler(request: httpx.Request) -> httpx.Response:
        return _success_payloads(request)

    with patch("plugins.amap.get_logger", return_value=mock_logger):
        await _registry(handler).execute("search_poi", keywords="西湖")

    mock_logger.info.assert_called()
    args, kwargs = mock_logger.info.call_args
    assert args == ("amap",)
    assert set(kwargs) <= {"path", "infocode", "poi_count"}
    assert kwargs["path"] == "/v5/place/text"
    assert kwargs["infocode"] == "10000"
    assert kwargs["poi_count"] == 1
    assert FAKE_KEY not in str(args) + str(kwargs)


@pytest.mark.asyncio
async def test_missing_key_fails_without_http():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _success_payloads(request)

    registry = create_amap_registry(
        api_key="",
        transport=httpx.MockTransport(handler),
    )
    result = await registry.execute("geocode_city", address="杭州")
    assert not result
    assert not called
    assert result.metadata.get("reason") == "amap_unavailable"


@pytest.mark.asyncio
async def test_route_failure_allows_estimate_not_fake_path():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            {"status": "1", "infocode": "10000", "route": {"transits": []}}
        )

    result = await _registry(handler).execute(
        "route_transit",
        origin="120.15,30.28",
        destination="120.16,30.29",
        city1="0571",
        city2="0571",
    )
    assert not result
    assert "估算" in (result.error or "")


def test_source_has_no_dashscope_or_env_reads():
    for path in PLUGIN_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "dashscope" not in text
        assert "os.getenv" not in text
        assert "os.environ" not in text


def test_plugin_classes_are_base_plugin():
    for cls in (
        GeocodeCityPlugin,
        SearchPoiPlugin,
        GetPoiDetailPlugin,
        GetWeatherPlugin,
        RouteWalkingPlugin,
        RouteTransitPlugin,
    ):
        assert issubclass(cls, BasePlugin)


def test_mock_http_is_not_live_geocode():
    """本文件只用 MockTransport，不能当作真实地理编码已通过。"""
    assert httpx.MockTransport is not None
    assert "restapi.amap.com" not in FAKE_KEY
