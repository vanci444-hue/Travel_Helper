from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.api.routes.events import HEARTBEAT_SECONDS
from src.config.settings import settings
from src.db.session import attach_sqlite_pragma, init_db
from src.services.planning import set_planning_hooks, wait_background_tasks
from test_planning import (
    READY_HANGZHOU,
    ScriptedLLM,
    ScriptedRegistry,
    _budget_ok,
    _itinerary_ok,
    _manager_client,
    _research_ok,
    assert_ok,
)


@pytest.fixture
async def client(tmp_path, monkeypatch) -> AsyncGenerator[AsyncClient, None]:
    test_db = tmp_path / "Travel_Helper.sse.test.db"
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
    monkeypatch.setattr(settings, "qwen_api_key", "test-not-a-real-qwen-key")
    await init_db()
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", trust_env=False) as ac:
        yield ac
    await wait_background_tasks()
    set_planning_hooks(specialist_chat=None, registry_factory=None)
    await test_engine.dispose()


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = None
    data_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())
        elif line == "":
            if event_name and data_lines:
                events.append((event_name, json.loads("\n".join(data_lines))))
            event_name = None
            data_lines = []
    if event_name and data_lines:
        events.append((event_name, json.loads("\n".join(data_lines))))
    return events


async def _collect_sse(client: AsyncClient, conv_id: str, timeout: float = 8.0) -> list[tuple[str, dict]]:
    async with client.stream(
        "GET",
        f"/api/conversations/{conv_id}/events",
        headers={"Accept": "text/event-stream"},
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        raw = ""

        async def _read() -> str:
            collected = ""
            async for chunk in resp.aiter_text():
                collected += chunk
                names = [name for name, _ in _parse_sse(collected)]
                if "itinerary.ready" in names or "planning.failed" in names:
                    return collected
            return collected

        raw = await asyncio.wait_for(_read(), timeout=timeout)
    return _parse_sse(raw)


def test_heartbeat_default_is_15() -> None:
    assert HEARTBEAT_SECONDS == 15


@pytest.mark.asyncio
async def test_sse_unknown_conversation(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/conversations/conv_missing/events",
        headers={"Accept": "text/event-stream"},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["error_code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_sse_streams_logs_then_ready(client: AsyncClient, monkeypatch) -> None:
    llm = ScriptedLLM(
        research=[
            {"_tool": "search_poi", "_args": {"keywords": "西湖"}},
            _research_ok(),
        ]
    )
    set_planning_hooks(specialist_chat=llm, registry_factory=lambda: ScriptedRegistry())
    created = assert_ok(await client.post("/api/conversations"), 201)
    conv_id = created["id"]
    monkeypatch.setattr(httpx, "AsyncClient", _manager_client(READY_HANGZHOU))
    assert_ok(
        await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "从上海出发，带老婆去杭州玩 5 天，预算 2 万，不要太赶"},
        )
    )
    await wait_background_tasks()
    events = await _collect_sse(client, conv_id)
    names = [name for name, _ in events]
    assert "planning.updated" in names
    assert "planning.log" in names
    assert names[-1] == "itinerary.ready"
    ready = [data for name, data in events if name == "itinerary.ready"][-1]
    assert ready["status"] == "succeeded"
    assert ready["itinerary_id"]
    log_entries = [data["entry"] for name, data in events if name == "planning.log"]
    assert log_entries
    for entry in log_entries:
        if entry.get("clickable"):
            assert entry["detail"]["heading"]
            assert entry["detail"]["body"]


@pytest.mark.asyncio
async def test_sse_failed_then_closes(client: AsyncClient, monkeypatch) -> None:
    llm = ScriptedLLM(
        research=[
            {
                "ok": False,
                "reason_code": "destination_not_found",
                "reason": "在国内地图里找不到这个目的地，没有可用的景点信息",
            }
        ]
    )
    set_planning_hooks(specialist_chat=llm, registry_factory=lambda: ScriptedRegistry())
    created = assert_ok(await client.post("/api/conversations"), 201)
    conv_id = created["id"]
    monkeypatch.setattr(httpx, "AsyncClient", _manager_client(READY_HANGZHOU))
    assert_ok(
        await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "从上海出发，带老婆去杭州玩 5 天，预算 2 万，不要太赶"},
        )
    )
    await wait_background_tasks()
    events = await _collect_sse(client, conv_id)
    assert events[-1][0] == "planning.failed"
    failed = events[-1][1]
    assert failed["failure_reason"]
    assert failed["failure_reason"] != "失败"
    assert failed["coco_message_id"]
    assert failed["itinerary_id"] is None


@pytest.mark.asyncio
async def test_sse_heartbeat_and_disconnect_keeps_job(client: AsyncClient, monkeypatch) -> None:
    from src.api.routes import events as events_mod
    from src.api.routes.events import _event_stream

    monkeypatch.setattr(events_mod, "HEARTBEAT_SECONDS", 0.05)
    gate = asyncio.Event()

    async def slow_llm(**kwargs):
        if kwargs["role"] == "destination_research":
            await gate.wait()
            return {"content": json.dumps(_research_ok(), ensure_ascii=False), "tool_calls": None, "reasoning": None}
        if kwargs["role"] == "budget_expert":
            return {"content": json.dumps(_budget_ok(), ensure_ascii=False), "tool_calls": None, "reasoning": None}
        return {"content": json.dumps(_itinerary_ok(), ensure_ascii=False), "tool_calls": None, "reasoning": None}

    set_planning_hooks(specialist_chat=slow_llm, registry_factory=lambda: ScriptedRegistry())
    created = assert_ok(await client.post("/api/conversations"), 201)
    conv_id = created["id"]
    monkeypatch.setattr(httpx, "AsyncClient", _manager_client(READY_HANGZHOU))
    assert_ok(
        await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "从上海出发，带老婆去杭州玩 5 天，预算 2 万，不要太赶"},
        )
    )

    class _FakeRequest:
        async def is_disconnected(self) -> bool:
            return False

    snapshot = {
        "status": "running",
        "specialists": [{"role": "destination_research", "status": "running", "summary": None}],
        "activity_log": [],
        "itinerary_id": None,
        "error_message": None,
    }
    raw = ""
    async for chunk in _event_stream(_FakeRequest(), conv_id, snapshot):
        raw += chunk
        if any(name == "heartbeat" for name, _ in _parse_sse(raw)):
            break
    assert any(name == "heartbeat" for name, _ in _parse_sse(raw))

    mid = assert_ok(await client.get(f"/api/conversations/{conv_id}"))
    assert mid["planning"]["status"] == "running"
    gate.set()
    await wait_background_tasks()
    done = assert_ok(await client.get(f"/api/conversations/{conv_id}"))
    assert done["planning"]["status"] == "succeeded"
    assert done["planning"]["itinerary_id"]
