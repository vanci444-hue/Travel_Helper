from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.config.settings import settings
from src.db.models import Conversation, Itinerary
from src.db.session import attach_sqlite_pragma, init_db
from src.models.common import utcnow
from src.services.revision import CARD_NOT_FOUND, ITINERARY_NOT_FOUND, set_leg_resolver


def assert_ok(resp: httpx.Response, status: int = 200) -> dict:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["error_code"] is None
    return body["data"]


def _card(card_id: str, title: str, lng: float, lat: float, start_time: str | None = "10:00") -> dict:
    return {
        "id": card_id,
        "type": "attraction",
        "title": title,
        "poi_id": f"poi_{card_id}",
        "lng": lng,
        "lat": lat,
        "address": "杭州市西湖区",
        "intro": f"{title}简介",
        "photo_url": None,
        "start_time": start_time,
        "suitable_for_children": True,
    }


def hangzhou_payload(
    conversation_id: str,
    *,
    itinerary_id: str = "itn_01",
    over_cap: bool = False,
) -> dict:
    cap = 5000 if over_cap else 20000
    total = 16200
    now = "2026-09-13T05:24:00Z"
    return {
        "id": itinerary_id,
        "conversation_id": conversation_id,
        "title": "杭州 5 日轻松游",
        "destination_city": "杭州",
        "origin_city": "上海",
        "duration_days": 5,
        "pace": "relaxed",
        "companion_type": "couple",
        "assumptions": ["市内交通按公交+适量步行", "住宿为推荐档，不代订"],
        "days": [
            {
                "day_index": 1,
                "label": "第 1 天",
                "date": None,
                "cards": [
                    _card("card_d1_01", "灵隐寺", 120.101, 30.241, "10:00"),
                    _card("card_d1_02", "西湖", 120.148, 30.242, "14:00"),
                    _card("card_d1_03", "断桥", 120.151, 30.258, "16:00"),
                ],
                "legs": [
                    {
                        "mode": "transit",
                        "duration_min": 25,
                        "distance_m": 4000,
                        "summary": "公交约 25 分钟",
                        "source": "amap",
                    },
                    {
                        "mode": "walking",
                        "duration_min": 12,
                        "distance_m": 900,
                        "summary": "步行约 12 分钟",
                        "source": "estimate",
                    },
                ],
            },
            {
                "day_index": 2,
                "label": "第 2 天",
                "date": None,
                "cards": [
                    _card("card_d2_01", "龙井村", 120.116, 30.22),
                    {
                        "id": "card_d2_02",
                        "type": "lodging",
                        "title": "推荐住宿 · 湖边民宿",
                        "poi_id": None,
                        "lng": 120.155,
                        "lat": 30.228,
                        "address": "南山路附近",
                        "intro": "仅推荐，不代订",
                        "photo_url": None,
                        "start_time": None,
                        "suitable_for_children": True,
                    },
                ],
                "legs": [
                    {
                        "mode": "walking",
                        "duration_min": 12,
                        "distance_m": 800,
                        "summary": "步行约 12 分钟",
                        "source": "estimate",
                    }
                ],
            },
            {
                "day_index": 3,
                "label": "第 3 天",
                "date": None,
                "cards": [
                    _card("card_d3_01", "西溪湿地", 120.063, 30.274, "10:30"),
                    _card("card_d3_02", "河坊街", 120.169, 30.245, "17:30"),
                ],
                "legs": [
                    {
                        "mode": "transit",
                        "duration_min": 40,
                        "distance_m": 9000,
                        "summary": "公交约 40 分钟",
                        "source": "amap",
                    }
                ],
            },
            {
                "day_index": 4,
                "label": "第 4 天",
                "date": None,
                "cards": [_card("card_d4_01", "九溪十八涧", 120.113, 30.205)],
                "legs": [],
            },
            {
                "day_index": 5,
                "label": "第 5 天",
                "date": None,
                "cards": [_card("card_d5_01", "湖滨漫步", 120.165, 30.253, "09:30")],
                "legs": [],
            },
        ],
        "budget": {
            "currency": "CNY",
            "cap_amount": cap,
            "total_amount": total,
            "over_cap": total > cap,
            "includes_note": "含上海—杭州往返与当地食住行门票的估算，非实时报价",
            "categories": [
                {"key": "transport", "label": "交通", "amount": 4000},
                {"key": "lodging", "label": "住宿", "amount": 6000},
                {"key": "food", "label": "餐饮", "amount": 3500},
                {"key": "tickets", "label": "门票活动", "amount": 2200},
                {"key": "other", "label": "其他", "amount": 500},
            ],
        },
        "checklist": [
            {"id": "chk_01", "text": "携带身份证", "relevant": True},
            {"id": "chk_02", "text": "查看是否需要提前预约西湖周边热门园", "relevant": True},
        ],
        "map_center": {"lng": 120.15, "lat": 30.25},
        "quick_suggestions": [
            {"id": "qs_01", "text": "第三天不要排那么满"},
            {"id": "qs_02", "text": "白天少走路，多坐公交"},
            {"id": "qs_03", "text": "换一家更安静的推荐住宿"},
        ],
        "status": "ready",
        "created_at": now,
        "updated_at": now,
    }


SUCCEEDED_PLANNING = {
    "status": "succeeded",
    "specialists": [
        {"role": "destination_research", "status": "succeeded", "summary": "点位可用"},
        {"role": "budget_expert", "status": "succeeded", "summary": "合计约 1.6 万"},
        {"role": "itinerary_design", "status": "succeeded", "summary": "5 天轻松行程"},
    ],
    "activity_log": [],
    "error_message": None,
    "itinerary_id": None,
}


@pytest.fixture
async def client(tmp_path, monkeypatch) -> AsyncGenerator[AsyncClient, None]:
    test_db = tmp_path / "Travel_Helper.itineraries.test.db"
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
    monkeypatch.setattr(settings, "amap_web_key", "")
    await init_db()
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", trust_env=False) as ac:
        yield ac
    set_leg_resolver(None)
    await test_engine.dispose()


async def seed_itinerary(
    *,
    conversation_id: str | None = None,
    itinerary_id: str = "itn_01",
    over_cap: bool = False,
    status: str = "ready",
    planning: dict | None = None,
) -> tuple[str, str]:
    from src.db.session import async_session_maker

    now = utcnow()
    async with async_session_maker() as db:
        if conversation_id is None:
            conversation_id = f"conv_{itinerary_id}"
            payload = hangzhou_payload(conversation_id, itinerary_id=itinerary_id, over_cap=over_cap)
            plan = dict(planning or SUCCEEDED_PLANNING)
            plan["itinerary_id"] = itinerary_id if status == "ready" else None
            conversation = Conversation(
                id=conversation_id,
                title="杭州 5 天",
                intake_json=json.dumps(
                    {
                        "origin_city": "上海",
                        "destination_city": "杭州",
                        "duration_days": 5,
                        "pace": "relaxed",
                        "companion_type": "couple",
                        "budget_amount_cny": 20000,
                        "missing_fields": [],
                        "ready": True,
                        "followup_rounds_used": 0,
                        "children": 0,
                        "children_age_bands": [],
                    },
                    ensure_ascii=False,
                ),
                planning_json=json.dumps(plan, ensure_ascii=False),
                created_at=now,
                updated_at=now,
            )
            db.add(conversation)
        else:
            payload = hangzhou_payload(conversation_id, itinerary_id=itinerary_id, over_cap=over_cap)
        row = Itinerary(
            id=itinerary_id,
            conversation_id=conversation_id,
            payload_json=json.dumps(payload, ensure_ascii=False),
            status=status,
            title=payload["title"],
            destination_city=payload["destination_city"],
            duration_days=payload["duration_days"],
            pace=payload["pace"],
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        await db.commit()
    return conversation_id, itinerary_id


def _assert_404_chinese(resp: httpx.Response) -> None:
    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert body["success"] is False
    assert body["error_code"] == "NOT_FOUND"
    assert body["error"]
    assert any("\u4e00" <= ch <= "\u9fff" for ch in body["error"])


@pytest.mark.asyncio
async def test_list_only_ready(client: AsyncClient) -> None:
    await seed_itinerary(itinerary_id="itn_ready")
    await seed_itinerary(itinerary_id="itn_draft", status="draft")
    resp = await client.get("/api/itineraries")
    data = assert_ok(resp)
    ids = [item["id"] for item in data]
    assert "itn_ready" in ids
    assert "itn_draft" not in ids
    assert all(item.keys() >= {"id", "title", "destination_city", "duration_days", "pace", "updated_at", "conversation_id"} for item in data)


@pytest.mark.asyncio
async def test_unknown_id_404_chinese(client: AsyncClient) -> None:
    _assert_404_chinese(await client.get("/api/itineraries/itn_missing"))
    _assert_404_chinese(
        await client.patch(
            "/api/itineraries/itn_missing/cards/card_01",
            json={"start_time": "11:00"},
        )
    )
    _assert_404_chinese(await client.delete("/api/itineraries/itn_missing/cards/card_01"))
    await seed_itinerary(itinerary_id="itn_01")
    _assert_404_chinese(await client.delete("/api/itineraries/itn_01/cards/card_missing"))
    missing = (await client.delete("/api/itineraries/itn_01/cards/card_missing")).json()
    assert missing["error"] == CARD_NOT_FOUND
    unknown = (await client.get("/api/itineraries/itn_missing")).json()
    assert unknown["error"] == ITINERARY_NOT_FOUND


@pytest.mark.asyncio
async def test_detail_fills_public_over_cap_no_passport(client: AsyncClient) -> None:
    await seed_itinerary(itinerary_id="itn_over", over_cap=True)
    data = assert_ok(await client.get("/api/itineraries/itn_over"))
    required = {
        "id",
        "conversation_id",
        "title",
        "destination_city",
        "origin_city",
        "duration_days",
        "pace",
        "companion_type",
        "assumptions",
        "days",
        "budget",
        "checklist",
        "map_center",
        "quick_suggestions",
        "status",
        "created_at",
        "updated_at",
    }
    assert required <= set(data)
    assert data["status"] == "ready"
    assert data["duration_days"] == 5
    assert data["days"][0]["cards"]
    assert data["days"][0]["legs"]
    assert data["budget"]["over_cap"] is True
    assert data["budget"]["total_amount"] > data["budget"]["cap_amount"]
    checklist = " ".join(item["text"] for item in data["checklist"])
    assert "护照" not in checklist
    assert "签证" not in checklist
    assert data["quick_suggestions"]


@pytest.mark.asyncio
async def test_patch_start_time_keeps_planning_succeeded(client: AsyncClient) -> None:
    conv_id, itinerary_id = await seed_itinerary()
    data = assert_ok(
        await client.patch(
            f"/api/itineraries/{itinerary_id}/cards/card_d1_01",
            json={"start_time": "11:30"},
        )
    )
    day1 = next(day for day in data["days"] if day["day_index"] == 1)
    card = next(item for item in day1["cards"] if item["id"] == "card_d1_01")
    assert card["start_time"] == "11:30"
    assert {item["id"] for item in day1["cards"]} >= {"card_d1_01", "card_d1_02"}
    conversation = assert_ok(await client.get(f"/api/conversations/{conv_id}"))
    assert conversation["planning"]["status"] == "succeeded"
    roles = {item["role"]: item["status"] for item in conversation["planning"]["specialists"]}
    assert roles == {
        "destination_research": "succeeded",
        "budget_expert": "succeeded",
        "itinerary_design": "succeeded",
    }


@pytest.mark.asyncio
async def test_delete_card_removes_point_keeps_planning(client: AsyncClient) -> None:
    conv_id, itinerary_id = await seed_itinerary()
    before = assert_ok(await client.get(f"/api/itineraries/{itinerary_id}"))
    day2_before = next(day for day in before["days"] if day["day_index"] == 2)
    assert any(card["id"] == "card_d2_01" for card in day2_before["cards"])
    data = assert_ok(await client.delete(f"/api/itineraries/{itinerary_id}/cards/card_d2_01"))
    day2 = next(day for day in data["days"] if day["day_index"] == 2)
    ids = [card["id"] for card in day2["cards"]]
    assert "card_d2_01" not in ids
    points = {(card["lng"], card["lat"]) for card in day2["cards"]}
    assert (120.116, 30.22) not in points
    conversation = assert_ok(await client.get(f"/api/conversations/{conv_id}"))
    assert conversation["planning"]["status"] == "succeeded"
    assert conversation["planning"]["itinerary_id"] == itinerary_id


@pytest.mark.asyncio
async def test_delete_recalculates_legs_as_estimate_without_key(client: AsyncClient) -> None:
    _conv_id, itinerary_id = await seed_itinerary()
    data = assert_ok(await client.delete(f"/api/itineraries/{itinerary_id}/cards/card_d1_02"))
    day1 = next(day for day in data["days"] if day["day_index"] == 1)
    assert [card["id"] for card in day1["cards"]] == ["card_d1_01", "card_d1_03"]
    assert len(day1["legs"]) == 1
    assert day1["legs"][0]["source"] == "estimate"
    assert "约" in day1["legs"][0]["summary"]
    assert data["budget"]["total_amount"] == 16200
    assert data["budget"]["over_cap"] is False
