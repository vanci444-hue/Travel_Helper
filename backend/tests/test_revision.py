from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.config.settings import settings
from src.db.session import attach_sqlite_pragma, init_db
from src.services.revision import (
    apply_operations,
    apply_prefer_transit,
    apply_replace_lodging,
    apply_set_day_pace,
    is_major_replan,
    known_revision_operations,
    set_leg_resolver,
)
from test_itineraries import hangzhou_payload, seed_itinerary


def assert_ok(resp: httpx.Response, status: int = 200) -> dict:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert body["success"] is True
    return body["data"]


def _llm_payload(obj: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(obj, ensure_ascii=False)}}]}


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def _patch_llm(monkeypatch, payload: dict) -> None:
    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            assert kwargs.get("trust_env") is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return None

        async def post(self, url, headers=None, json=None):
            assert url.endswith("/chat/completions")
            return _FakeResponse(_llm_payload(payload))

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)


@pytest.fixture
async def client(tmp_path, monkeypatch) -> AsyncGenerator[AsyncClient, None]:
    test_db = tmp_path / "Travel_Helper.revision.test.db"
    url = f"sqlite+aiosqlite:///{test_db}"
    test_engine = create_async_engine(url, future=True)
    test_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    attach_sqlite_pragma(test_engine)
    import src.db.session as session_mod

    monkeypatch.setattr(session_mod, "engine", test_engine)
    monkeypatch.setattr(session_mod, "async_session_maker", test_maker)
    monkeypatch.setattr(settings, "deepseek_api_key", "test-not-a-real-key")
    monkeypatch.setattr(settings, "amap_web_key", "")
    await init_db()
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", trust_env=False) as ac:
        yield ac
    set_leg_resolver(None)
    await test_engine.dispose()


def _revise_payload(*, action: str, reply: str, operations: list | None = None) -> dict:
    return {
        "action": action,
        "reply": reply,
        "intake_patch": {},
        "recommended_destination": None,
        "operations": operations or [],
    }


@pytest.mark.asyncio
async def test_revise_remove_card_same_itinerary(client: AsyncClient, monkeypatch) -> None:
    conv_id, itinerary_id = await seed_itinerary()
    _patch_llm(
        monkeypatch,
        _revise_payload(
            action="revise",
            reply="好，第 2 天那张龙井村我帮你拿掉了。",
            operations=[{"op": "remove_card", "card_id": "card_d2_01"}],
        ),
    )
    turn = assert_ok(
        await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "第二天不要去龙井村了"},
        )
    )
    assert turn["planning"]["itinerary_id"] == itinerary_id
    assert turn["planning"]["status"] == "succeeded"
    roles = {item["role"]: item["status"] for item in turn["planning"]["specialists"]}
    assert set(roles.values()) == {"succeeded"}
    detail = assert_ok(await client.get(f"/api/itineraries/{itinerary_id}"))
    day2 = next(day for day in detail["days"] if day["day_index"] == 2)
    assert "card_d2_01" not in [card["id"] for card in day2["cards"]]


@pytest.mark.asyncio
async def test_revise_set_day_pace_same_itinerary(client: AsyncClient, monkeypatch) -> None:
    conv_id, itinerary_id = await seed_itinerary()
    _patch_llm(
        monkeypatch,
        _revise_payload(
            action="revise",
            reply="第三天我帮你排松一点。",
            operations=[{"op": "set_day_pace", "day_index": 3, "max_major_points": 1}],
        ),
    )
    turn = assert_ok(
        await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "第三天不要排那么满"},
        )
    )
    assert turn["planning"]["itinerary_id"] == itinerary_id
    assert turn["planning"]["status"] == "succeeded"
    detail = assert_ok(await client.get(f"/api/itineraries/{itinerary_id}"))
    day3 = next(day for day in detail["days"] if day["day_index"] == 3)
    assert len(day3["cards"]) == 1
    assert day3["cards"][0]["id"] == "card_d3_01"


@pytest.mark.asyncio
async def test_unmapped_keeps_itinerary(client: AsyncClient, monkeypatch) -> None:
    conv_id, itinerary_id = await seed_itinerary()
    before = assert_ok(await client.get(f"/api/itineraries/{itinerary_id}"))
    before_ids = [card["id"] for day in before["days"] for card in day["cards"]]
    _patch_llm(
        monkeypatch,
        _revise_payload(
            action="ask",
            reply="我可以帮你删某张卡片，或把某一天排松一点。",
            operations=[],
        ),
    )
    turn = assert_ok(
        await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "帮我弄得更有趣一点"},
        )
    )
    assert "卡片" in turn["assistant_message"]["content"] or "排松" in turn["assistant_message"]["content"]
    after = assert_ok(await client.get(f"/api/itineraries/{itinerary_id}"))
    after_ids = [card["id"] for day in after["days"] for card in day["cards"]]
    assert after_ids == before_ids
    assert turn["planning"]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_suggest_new_plan_does_not_change_cards(client: AsyncClient, monkeypatch) -> None:
    conv_id, itinerary_id = await seed_itinerary()
    before = assert_ok(await client.get(f"/api/itineraries/{itinerary_id}"))
    before_ids = [card["id"] for day in before["days"] for card in day["cards"]]
    _patch_llm(
        monkeypatch,
        _revise_payload(
            action="revise",
            reply="我先帮你删一张。",
            operations=[{"op": "remove_card", "card_id": "card_d2_01"}],
        ),
    )
    turn = assert_ok(
        await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "换个目的地改去成都"},
        )
    )
    assert "新建计划" in turn["assistant_message"]["content"] or "换目的地" in turn["assistant_message"]["content"]
    after = assert_ok(await client.get(f"/api/itineraries/{itinerary_id}"))
    after_ids = [card["id"] for day in after["days"] for card in day["cards"]]
    assert after_ids == before_ids
    assert turn["planning"]["status"] == "succeeded"
    assert turn["planning"]["itinerary_id"] == itinerary_id


@pytest.mark.asyncio
async def test_suggest_new_plan_action_from_model(client: AsyncClient, monkeypatch) -> None:
    conv_id, itinerary_id = await seed_itinerary()
    before = assert_ok(await client.get(f"/api/itineraries/{itinerary_id}"))
    before_ids = [card["id"] for day in before["days"] for card in day["cards"]]
    _patch_llm(
        monkeypatch,
        _revise_payload(
            action="suggest_new_plan",
            reply="天数差太多，请去新建计划。",
            operations=[{"op": "remove_card", "card_id": "card_d1_01"}],
        ),
    )
    turn = assert_ok(
        await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "改成 10 天吧"},
        )
    )
    assert "新建计划" in turn["assistant_message"]["content"]
    after = assert_ok(await client.get(f"/api/itineraries/{itinerary_id}"))
    assert [card["id"] for day in after["days"] for card in day["cards"]] == before_ids


def test_is_major_replan_and_operations_unit() -> None:
    payload = hangzhou_payload("conv_x")
    assert is_major_replan("换个目的地改去成都", payload) is True
    assert is_major_replan("改成 10 天", payload) is True
    assert is_major_replan("第三天不要排那么满", payload) is False
    day3_before = next(day for day in payload["days"] if day["day_index"] == 3)
    assert len(day3_before["cards"]) == 2
    affected = apply_set_day_pace(payload, 3, 1)
    assert affected == {3}
    day3 = next(day for day in payload["days"] if day["day_index"] == 3)
    assert len(day3["cards"]) == 1
    other = hangzhou_payload("conv_y")
    changed = apply_operations(other, [{"op": "remove_card", "card_id": "card_d2_01"}])
    assert changed == {2}
    day2 = next(day for day in other["days"] if day["day_index"] == 2)
    assert "card_d2_01" not in [card["id"] for card in day2["cards"]]
    assert known_revision_operations("白天少走路，多坐公交") == [{"op": "prefer_transit"}]
    assert known_revision_operations("换一家更安静的推荐住宿") == [{"op": "replace_lodging"}]
    transit_payload = hangzhou_payload("conv_transit")
    assert apply_prefer_transit(transit_payload) >= {1, 2}
    assert transit_payload.get("prefer_transit") is True
    lodging_payload = hangzhou_payload("conv_stay")
    assert apply_replace_lodging(lodging_payload) == {2}
    day2_stay = next(day for day in lodging_payload["days"] if day["day_index"] == 2)
    lodging = next(card for card in day2_stay["cards"] if card["type"] == "lodging")
    assert lodging["title"] == "更安静的推荐住宿"


@pytest.mark.asyncio
async def test_quick_suggestion_transit_updates_without_llm(client: AsyncClient) -> None:
    conv_id, itinerary_id = await seed_itinerary()
    before = assert_ok(await client.get(f"/api/itineraries/{itinerary_id}"))
    walking_before = [
        leg
        for day in before["days"]
        for leg in day["legs"]
        if leg["mode"] == "walking"
    ]
    assert walking_before
    turn = assert_ok(
        await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "白天少走路，多坐公交"},
        )
    )
    assert "公交" in turn["assistant_message"]["content"]
    after = assert_ok(await client.get(f"/api/itineraries/{itinerary_id}"))
    walking_after = [
        leg
        for day in after["days"]
        for leg in day["legs"]
        if leg["mode"] == "walking"
    ]
    assert walking_after == []
    assert any(leg["mode"] == "transit" for day in after["days"] for leg in day["legs"])
    assert turn["planning"]["itinerary_id"] == itinerary_id


@pytest.mark.asyncio
async def test_quick_suggestion_lodging_updates_without_llm(client: AsyncClient) -> None:
    conv_id, itinerary_id = await seed_itinerary()
    turn = assert_ok(
        await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "换一家更安静的推荐住宿"},
        )
    )
    assert "住宿" in turn["assistant_message"]["content"]
    after = assert_ok(await client.get(f"/api/itineraries/{itinerary_id}"))
    lodging = next(
        card
        for day in after["days"]
        for card in day["cards"]
        if card["type"] == "lodging"
    )
    assert lodging["title"] == "更安静的推荐住宿"
    assert turn["planning"]["itinerary_id"] == itinerary_id
