from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pycore.core import ConfigManager
from pycore.core.exceptions import ConfigurationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.config.settings import AppSettings, settings
from src.db.session import attach_sqlite_pragma, init_db
from src.models.common import MISSING_MODEL_KEY, PACE_ERROR
from src.services.manager import empty_intake, extract_from_text, merge_intake


def assert_ok(resp: httpx.Response, status: int = 200) -> dict:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["error_code"] is None
    return body["data"]


def _llm_payload(obj: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(obj, ensure_ascii=False)}}]}


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


@pytest.fixture
async def client(tmp_path, monkeypatch) -> AsyncGenerator[AsyncClient, None]:
    test_db = tmp_path / "Travel_Helper.test.db"
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

    await init_db()
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", trust_env=False) as ac:
        yield ac
    await test_engine.dispose()


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


@pytest.mark.asyncio
async def test_create_empty_body_idle(client: AsyncClient) -> None:
    data = assert_ok(await client.post("/api/conversations"), 201)
    assert data["planning"]["status"] == "idle"
    assert data["messages"] == []
    roles = {item["role"]: item["status"] for item in data["planning"]["specialists"]}
    assert roles == {
        "destination_research": "not_started",
        "budget_expert": "not_started",
        "itinerary_design": "not_started",
    }


@pytest.mark.asyncio
async def test_create_prefill_hangzhou_missing_only_unfilled(client: AsyncClient) -> None:
    data = assert_ok(
        await client.post(
            "/api/conversations",
            json={
                "destination_city": "杭州",
                "duration_days": 5,
                "companion_type": "couple",
                "adults": 2,
                "budget_amount_cny": 20000,
                "pace": "relaxed",
                "wish_text": "目前已知的计划：轻松吃吃走走",
            },
        ),
        201,
    )
    missing = data["intake"]["missing_fields"]
    assert "destination_city" not in missing
    assert "duration_days" not in missing
    assert "companion" not in missing
    assert "budget" not in missing
    assert "pace" not in missing
    assert "origin_city" in missing
    assert data["planning"]["status"] == "idle"


@pytest.mark.asyncio
async def test_create_invalid_pace(client: AsyncClient) -> None:
    resp = await client.post("/api/conversations", json={"pace": "crazy"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["success"] is False
    assert body["error_code"] == "VALIDATION_ERROR"
    assert body["error"] == PACE_ERROR


@pytest.mark.asyncio
async def test_mock_manager_ask_increments_followup(client: AsyncClient, monkeypatch) -> None:
    created = assert_ok(await client.post("/api/conversations"), 201)
    _patch_llm(
        monkeypatch,
        {
            "action": "ask",
            "reply": "还差出发地、时长和预算，这次是国内还是出境？",
            "intake_patch": {},
            "recommended_destination": None,
        },
    )
    data = assert_ok(
        await client.post(
            f"/api/conversations/{created['id']}/messages",
            json={"content": "想出去玩"},
        )
    )
    assert data["assistant_message"]["display_name"] == "Coco"
    assert data["intake"]["followup_rounds_used"] == 1
    roles = {item["role"]: item["status"] for item in data["planning"]["specialists"]}
    assert roles["destination_research"] == "not_started"
    assert roles["budget_expert"] == "not_started"
    assert roles["itinerary_design"] == "not_started"
    assert data["planning"]["status"] == "idle"


@pytest.mark.asyncio
async def test_mock_manager_ready_starts_research(client: AsyncClient, monkeypatch) -> None:
    created = assert_ok(await client.post("/api/conversations"), 201)
    _patch_llm(
        monkeypatch,
        {
            "action": "ready",
            "reply": "信息齐了：上海出发、杭州 5 天、情侣、2 万、轻松节奏。我这边让专员出一版。",
            "intake_patch": {},
            "recommended_destination": None,
        },
    )
    data = assert_ok(
        await client.post(
            f"/api/conversations/{created['id']}/messages",
            json={"content": "从上海出发，带老婆去杭州玩 5 天，预算 2 万，不要太赶"},
        )
    )
    assert "出境" not in data["assistant_message"]["content"]
    assert data["intake"]["ready"] is True
    assert data["intake"]["origin_city"] == "上海"
    assert data["intake"]["destination_city"] == "杭州"
    assert data["planning"]["status"] == "running"
    roles = {item["role"]: item["status"] for item in data["planning"]["specialists"]}
    assert roles["destination_research"] == "running"
    assert roles["budget_expert"] == "not_started"


@pytest.mark.asyncio
async def test_two_followups_force_stop(client: AsyncClient, monkeypatch) -> None:
    created = assert_ok(await client.post("/api/conversations"), 201)
    conv_id = created["id"]
    _patch_llm(
        monkeypatch,
        {
            "action": "ask",
            "reply": "还差出发地和天数。",
            "intake_patch": {},
            "recommended_destination": None,
        },
    )
    assert_ok(
        await client.post(f"/api/conversations/{conv_id}/messages", json={"content": "想出去玩"})
    )
    _patch_llm(
        monkeypatch,
        {
            "action": "ask",
            "reply": "还是缺出发地和天数。",
            "intake_patch": {},
            "recommended_destination": None,
        },
    )
    assert_ok(
        await client.post(f"/api/conversations/{conv_id}/messages", json={"content": "还没想好"})
    )
    _patch_llm(
        monkeypatch,
        {
            "action": "ready",
            "reply": "可以出方案了",
            "intake_patch": {},
            "recommended_destination": None,
        },
    )
    data = assert_ok(
        await client.post(f"/api/conversations/{conv_id}/messages", json={"content": "你看着办吧"})
    )
    assert data["intake"]["ready"] is False
    assert data["planning"]["status"] == "idle"
    assert data["planning"]["itinerary_id"] is None
    detail = assert_ok(await client.get(f"/api/conversations/{conv_id}"))
    assert detail["planning"]["status"] == "idle"
    assert detail["planning"]["itinerary_id"] is None


def test_ac009_hard_rules_ready_without_model() -> None:
    patch = extract_from_text("从北京出发带小孩想看海 4 天预算 8 千别太赶")
    intake = merge_intake(empty_intake(), patch)
    assert intake["ready"] is True
    assert intake["region"] == "domestic"
    assert intake["destination_city"] == "青岛"
    assert intake["origin_city"] == "北京"
    assert intake["duration_days"] == 4
    assert intake["budget_amount_cny"] == 8000
    assert intake["pace"] == "relaxed"
    assert intake["children_age_bands"] == ["学龄儿童"]
    assert intake["missing_fields"] == []


def test_unlimited_budget_is_premium_tier() -> None:
    patch = extract_from_text("从北京出发去三亚 8 天预算不限放松一点我和老婆")
    intake = merge_intake(empty_intake(), patch)
    assert intake["ready"] is True
    assert intake["budget_tier"] == "premium"
    assert intake["origin_city"] == "北京"
    assert intake["destination_city"] == "三亚"
    assert intake["duration_days"] == 8
    assert intake["pace"] == "relaxed"
    assert intake["companion_type"] == "couple"
    assert intake["missing_fields"] == []


def test_want_to_play_still_not_ready() -> None:
    patch = extract_from_text("想出去玩")
    intake = merge_intake(empty_intake(), patch)
    assert intake["ready"] is False
    assert "origin_city" in intake["missing_fields"]
    assert "duration_days" in intake["missing_fields"]
    assert intake["destination_city"] is None


GARBLED_CITY = "䶮䶮䶮阿巴市"
GARBLED_MIN_SET = f"上海出发带配偶去{GARBLED_CITY} 5 天、预算 2 万、不要太赶"
HANGZHOU_MIN_SET = "上海出发带配偶去杭州 5 天、预算 2 万、不要太赶"


def test_garbled_domestic_city_ready_without_model() -> None:
    patch = extract_from_text(GARBLED_MIN_SET)
    intake = merge_intake(empty_intake(), patch)
    assert intake["ready"] is True
    assert intake["region"] == "domestic"
    assert intake["destination_city"] == GARBLED_CITY
    assert intake["origin_city"] == "上海"
    assert intake["duration_days"] == 5
    assert intake["budget_amount_cny"] == 20000
    assert intake["pace"] == "relaxed"
    assert intake["companion_type"] == "couple"
    assert intake["destination_city"] != "杭州"
    assert intake["destination_city"] != "青岛"
    assert intake["missing_fields"] == []


def test_shanghai_hangzhou_min_set_still_ready() -> None:
    patch = extract_from_text(HANGZHOU_MIN_SET)
    intake = merge_intake(empty_intake(), patch)
    assert intake["ready"] is True
    assert intake["region"] == "domestic"
    assert intake["destination_city"] == "杭州"
    assert intake["origin_city"] == "上海"
    assert intake["missing_fields"] == []


@pytest.mark.asyncio
async def test_ac009_ready_even_if_model_asks(client: AsyncClient, monkeypatch) -> None:
    created = assert_ok(await client.post("/api/conversations"), 201)
    _patch_llm(
        monkeypatch,
        {
            "action": "ask",
            "reply": "请问孩子大概几岁？另外这趟想看海是想去国内的海边，还是想出境？",
            "intake_patch": {},
            "recommended_destination": None,
        },
    )
    data = assert_ok(
        await client.post(
            f"/api/conversations/{created['id']}/messages",
            json={"content": "从北京出发带小孩想看海 4 天预算 8 千别太赶"},
        )
    )
    assert data["intake"]["ready"] is True
    assert data["intake"]["destination_city"] == "青岛"
    assert data["intake"]["region"] == "domestic"
    assert data["intake"]["children_age_bands"] == ["学龄儿童"]
    assert data["planning"]["status"] == "running"
    roles = {item["role"]: item["status"] for item in data["planning"]["specialists"]}
    assert roles["destination_research"] == "running"
    assert "出境" not in data["assistant_message"]["content"]
    assert "几岁" not in data["assistant_message"]["content"]
    assert "青岛" in data["assistant_message"]["content"]


@pytest.mark.asyncio
async def test_garbled_city_starts_planning_even_if_model_asks(
    client: AsyncClient, monkeypatch
) -> None:
    created = assert_ok(await client.post("/api/conversations"), 201)
    _patch_llm(
        monkeypatch,
        {
            "action": "ask",
            "reply": "📝 这个地名我对应不到国内哪座城，你是指国外哪一区域吗？",
            "intake_patch": {"destination_city": "杭州", "destination_text": "杭州"},
            "recommended_destination": "杭州",
        },
    )
    data = assert_ok(
        await client.post(
            f"/api/conversations/{created['id']}/messages",
            json={"content": GARBLED_MIN_SET},
        )
    )
    assert data["intake"]["ready"] is True
    assert data["intake"]["region"] == "domestic"
    assert data["intake"]["destination_city"] == GARBLED_CITY
    assert data["intake"]["destination_city"] != "杭州"
    assert data["planning"]["status"] == "running"
    roles = {item["role"]: item["status"] for item in data["planning"]["specialists"]}
    assert roles["destination_research"] == "running"
    assert "哪座城" not in data["assistant_message"]["content"]
    assert "出境" not in data["assistant_message"]["content"]


@pytest.mark.asyncio
async def test_recommended_destination_can_ready(client: AsyncClient, monkeypatch) -> None:
    created = assert_ok(await client.post("/api/conversations"), 201)
    _patch_llm(
        monkeypatch,
        {
            "action": "ready",
            "reply": "按带小孩、看海来，我推荐青岛，直接出一版。",
            "intake_patch": {"children_age_bands": ["6-12岁"]},
            "recommended_destination": "青岛",
        },
    )
    data = assert_ok(
        await client.post(
            f"/api/conversations/{created['id']}/messages",
            json={"content": "从北京出发、带小孩、想看海、4 天、预算 8 千、别太赶"},
        )
    )
    assert data["intake"]["destination_city"] == "青岛"
    assert data["intake"]["ready"] is True
    assert data["planning"]["status"] == "running"


@pytest.mark.asyncio
async def test_missing_key_saves_user_message(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    created = assert_ok(await client.post("/api/conversations"), 201)
    resp = await client.post(
        f"/api/conversations/{created['id']}/messages",
        json={"content": "从上海出发去杭州"},
    )
    assert resp.status_code == 500
    body = resp.json()
    assert body["success"] is False
    assert body["error"] == MISSING_MODEL_KEY
    detail = assert_ok(await client.get(f"/api/conversations/{created['id']}"))
    user_msgs = [item for item in detail["messages"] if item["role"] == "user"]
    assert len(user_msgs) == 1
    assert user_msgs[0]["content"] == "从上海出发去杭州"


def test_config_manager_rejects_use_env(tmp_path: Path) -> None:
    from src.config.settings import ENV_PATH

    env_file = tmp_path / ".env"
    env_file.write_text("secret_key=test-secret\ndebug=true\n", encoding="utf-8")
    ConfigManager.reset()
    try:
        manager: ConfigManager[AppSettings] = ConfigManager()
        with pytest.raises(ConfigurationError):
            manager.load(AppSettings, env_file, use_env=True)
        manager.load(AppSettings, env_file, use_env=False)
        assert manager.settings.secret_key == "test-secret"
    finally:
        ConfigManager.reset()
        ConfigManager().load(AppSettings, ENV_PATH, use_env=False)


@pytest.mark.asyncio
async def test_conversation_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/conversations/conv_missing")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "找不到这场对话"
