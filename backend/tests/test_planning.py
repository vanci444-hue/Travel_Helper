from __future__ import annotations

import ast
import asyncio
import json as json_mod
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pycore.plugins import PluginResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.config.settings import AppSettings, settings
from src.db.models import Itinerary, PlanningJob
from src.db.session import attach_sqlite_pragma, init_db
from src.services.activity_log import MAX_ENTRIES, append_entry, build_entry, evict_overflow
from src.services.planning import set_planning_hooks, wait_background_tasks
from src.services.specialists.budget import load_prompt as load_budget_prompt
from src.services.specialists.itinerary import load_prompt as load_itinerary_prompt
from src.services.specialists.research import load_prompt as load_research_prompt


def assert_ok(resp: httpx.Response, status: int = 200) -> dict:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert body["success"] is True
    return body["data"]


READY_HANGZHOU = {
    "action": "ready",
    "reply": "信息齐了：上海出发、杭州 5 天、情侣、2 万、轻松节奏。我这边让专员出一版。",
    "intake_patch": {},
    "recommended_destination": None,
}

GARBLED_CITY = "䶮䶮䶮阿巴市"
GARBLED_MIN_SET = f"上海出发带配偶去{GARBLED_CITY} 5 天、预算 2 万、不要太赶"
ASK_WHICH_CITY = {
    "action": "ask",
    "reply": "📝 这个地名我对应不到国内哪座城，你是指国外哪一区域吗？",
    "intake_patch": {},
    "recommended_destination": None,
}


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def _manager_client(payload: dict):
    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            assert kwargs.get("trust_env") is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return None

        async def post(self, url, headers=None, json=None):
            assert url.endswith("/chat/completions")
            return _FakeResponse(
                {"choices": [{"message": {"content": json_mod.dumps(payload, ensure_ascii=False)}}]}
            )

    return _FakeClient


@pytest.fixture
async def client(tmp_path, monkeypatch) -> AsyncGenerator[AsyncClient, None]:
    test_db = tmp_path / "Travel_Helper.planning.test.db"
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


def _research_ok() -> dict:
    return {
        "ok": True,
        "destination_city": "杭州",
        "weather_summary": "多云，适宜出行",
        "pois": [
            {
                "poi_id": "B0FFFAB6J2",
                "name": "西湖",
                "type": "attraction",
                "reason": "适合情侣轻松散步",
                "suitable_for_children": True,
                "open_time": "全天",
                "photo_url": None,
            }
        ],
        "warnings": [],
    }


def _budget_ok(*, over_cap: bool = False) -> dict:
    total = 26000 if over_cap else 16200
    return {
        "ok": True,
        "currency": "CNY",
        "total_amount": total,
        "categories": [
            {"key": "transport", "amount": 4000},
            {"key": "lodging", "amount": 8000 if over_cap else 6000},
            {"key": "food", "amount": 6000 if over_cap else 3500},
            {"key": "tickets", "amount": 6000 if over_cap else 2200},
            {"key": "other", "amount": 2000 if over_cap else 500},
        ],
        "includes_note": "含上海—杭州往返与当地食住行门票的估算，非实时报价",
        "over_cap": over_cap,
    }


def _itinerary_ok() -> dict:
    return {
        "ok": True,
        "summary": "5 天轻松行程",
        "days": [
            {
                "day_index": 1,
                "label": "第 1 天",
                "date": None,
                "cards": [
                    {
                        "type": "attraction",
                        "title": "西湖",
                        "poi_id": "B0FFFAB6J2",
                        "lng": 120.148,
                        "lat": 30.242,
                        "address": "杭州市西湖区",
                        "intro": "适合轻松散步",
                        "photo_url": None,
                        "start_time": "10:00",
                        "suitable_for_children": True,
                    }
                ],
                "legs": [],
            }
        ],
    }


class ScriptedLLM:
    def __init__(self, research=None, budget=None, itinerary=None) -> None:
        self.research = research if research is not None else [_research_ok()]
        self.budget = budget if budget is not None else [_budget_ok()]
        self.itinerary = itinerary if itinerary is not None else [_itinerary_ok()]
        self.calls: list[dict] = []
        self.started: dict[str, asyncio.Event] = {
            "budget_expert": asyncio.Event(),
            "itinerary_design": asyncio.Event(),
        }
        self.seen_parallel = False

    async def __call__(self, **kwargs):
        role = kwargs["role"]
        self.calls.append(kwargs)
        if role == "budget_expert":
            self.started["budget_expert"].set()
            if not self.started["itinerary_design"].is_set():
                try:
                    await asyncio.wait_for(self.started["itinerary_design"].wait(), timeout=2)
                    self.seen_parallel = True
                except TimeoutError:
                    self.seen_parallel = False
            payload = self.budget.pop(0) if self.budget else _budget_ok()
        elif role == "itinerary_design":
            self.started["itinerary_design"].set()
            if not self.started["budget_expert"].is_set():
                try:
                    await asyncio.wait_for(self.started["budget_expert"].wait(), timeout=2)
                    self.seen_parallel = True
                except TimeoutError:
                    self.seen_parallel = False
            payload = self.itinerary.pop(0) if self.itinerary else _itinerary_ok()
        else:
            payload = self.research.pop(0) if self.research else _research_ok()
        if payload.get("_tool"):
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": payload["_tool"],
                            "arguments": json_mod.dumps(payload.get("_args") or {}, ensure_ascii=False),
                        },
                    }
                ],
                "reasoning": payload.get("_reasoning"),
            }
        return {"content": json_mod.dumps(payload, ensure_ascii=False), "tool_calls": None, "reasoning": None}


class ScriptedRegistry:
    def __init__(self, result: PluginResult | None = None) -> None:
        self.result = result or PluginResult.ok({"pois": [{"name": "西湖"}]})
        self.executed: list[str] = []

    def to_specs(self):
        names = (
            "geocode_city",
            "search_poi",
            "get_poi_detail",
            "get_weather",
            "route_walking",
            "route_transit",
        )
        return [
            {
                "type": "function",
                "function": {"name": name, "description": name, "parameters": {"type": "object", "properties": {}}},
            }
            for name in names
        ]

    async def execute(self, name: str, **kwargs) -> PluginResult:
        self.executed.append(name)
        return self.result


async def _wait_status(client: AsyncClient, conversation_id: str, expected: set[str]) -> dict:
    await wait_background_tasks()
    data = assert_ok(await client.get(f"/api/conversations/{conversation_id}"))
    assert data["planning"]["status"] in expected, data["planning"]
    return data


def test_settings_defaults_and_no_dashscope() -> None:
    fields = AppSettings.model_fields
    assert fields["manager_thinking_enabled"].default is False
    assert fields["itinerary_thinking_enabled"].default is True
    assert fields["deepseek_model"].default == "deepseek-flash"
    assert fields["qwen_model"].default == "qwen-plus"
    src = Path(__file__).resolve().parents[1] / "src"
    for path in src.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name.split(".")[0] != "dashscope" for alias in node.names), path
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] != "dashscope", path


def test_itinerary_prompt_density() -> None:
    text = load_itinerary_prompt()
    assert "轻松" in text and "1–2" in text
    assert "适中" in text and "2–3" in text
    assert "紧凑" in text and "3–4" in text
    assert "亲子" in text and "避坑" in text
    assert "情侣" in text
    assert "护照" in text and "签证" in text
    assert "公交" in text and "步行" in text
    assert "json" in text.lower()
    research = load_research_prompt()
    assert "json" in research.lower()
    assert "亲子" in research and "情侣" in research
    assert "location" in research
    assert "json" in load_budget_prompt().lower()


def _sample_card(title: str, lng: float = 104.06, lat: float = 30.67) -> dict:
    return {
        "id": f"card_{title}",
        "type": "attraction",
        "title": title,
        "poi_id": title,
        "lng": lng,
        "lat": lat,
        "address": "成都市",
        "intro": title,
        "photo_url": None,
        "start_time": "10:00",
        "suitable_for_children": True,
    }


def test_apply_pace_trims_relaxed_and_annotates_family() -> None:
    from src.services.specialists.itinerary import apply_pace_and_companion, is_major_card

    days = [
        {
            "day_index": 1,
            "label": "第 1 天",
            "cards": [
                _sample_card("熊猫基地"),
                _sample_card("宽窄巷子"),
                _sample_card("锦里"),
                _sample_card("武侯祠"),
            ],
            "legs": [],
        }
    ]
    out = apply_pace_and_companion(
        days,
        {"pace": "relaxed", "companion_type": "parent_child"},
        {"pois": []},
    )
    majors = [card for card in out[0]["cards"] if is_major_card(card)]
    assert 1 <= len(majors) <= 2
    assert all("避坑" in str(card.get("intro") or "") for card in majors)


def test_apply_pace_pads_packed_from_research() -> None:
    from src.services.specialists.itinerary import apply_pace_and_companion, is_major_card

    days = [
        {
            "day_index": 1,
            "label": "第 1 天",
            "cards": [_sample_card("春熙路")],
            "legs": [],
        }
    ]
    research = {
        "pois": [
            {
                "name": "太古里",
                "location": "104.081,30.655",
                "reason": "夜景散步",
                "suitable_for_children": False,
            },
            {
                "name": "九眼桥",
                "lng": 104.09,
                "lat": 30.64,
                "reason": "河边夜景",
                "suitable_for_children": False,
            },
            {
                "name": "望江楼",
                "location": "104.09,30.63",
                "reason": "观景",
                "suitable_for_children": True,
            },
        ]
    }
    out = apply_pace_and_companion(
        days,
        {"pace": "packed", "companion_type": "couple"},
        research,
    )
    majors = [card for card in out[0]["cards"] if is_major_card(card)]
    titles = {card["title"] for card in majors}
    assert 3 <= len(majors) <= 4
    assert "春熙路" in titles
    assert titles != {"春熙路"}
    assert any("情侣" in str(card.get("intro") or "") or "夜景" in str(card.get("intro") or "") for card in majors)


def test_activity_log_keeps_eighty_and_clickable_detail() -> None:
    entries: list[dict] = []
    for index in range(70):
        entries = append_entry(
            entries,
            build_entry(kind="thought", specialist="destination_research", title=f"思考 {index}", body="短说明"),
        )
    for index in range(15):
        entries = append_entry(
            entries,
            build_entry(kind="tool", specialist="destination_research", title=f"搜索景点 {index}", body="找到：西湖"),
        )
    entries = evict_overflow(entries)
    assert len(entries) == MAX_ENTRIES
    assert all(item["kind"] != "thought" or item["title"] != "思考 0" for item in entries)
    assert any(item["kind"] == "tool" for item in entries)
    clickable = [item for item in entries if item["clickable"]]
    assert clickable
    for item in clickable:
        assert item["detail"]["heading"]
        assert item["detail"]["body"]
        assert len(item["detail"]["body"]) <= 4000


@pytest.mark.asyncio
async def test_mock_success_simple(client: AsyncClient, monkeypatch) -> None:
    llm = ScriptedLLM()
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
    detail = await _wait_status(client, conv_id, {"succeeded"})
    assert detail["planning"]["itinerary_id"]
    assert llm.seen_parallel is True
    roles = {item["role"]: item["status"] for item in detail["planning"]["specialists"]}
    assert roles == {
        "destination_research": "succeeded",
        "budget_expert": "succeeded",
        "itinerary_design": "succeeded",
    }
    coco = [item for item in detail["messages"] if item["role"] == "assistant"][-1]
    assert "行程详情" in coco["content"]
    assert "第 1 天" not in coco["content"]
    logs = detail["planning"]["activity_log"]
    assert logs
    assert [item["id"] for item in logs] == list({item["id"]: None for item in logs})
    clickable = [item for item in logs if item["clickable"]]
    assert clickable
    for item in clickable:
        assert item["detail"]["heading"]
        assert item["detail"]["body"]
    from src.db.session import async_session_maker

    async with async_session_maker() as db:
        row = await db.get(Itinerary, detail["planning"]["itinerary_id"])
        assert row is not None
        assert row.status == "ready"
        payload = json_mod.loads(row.payload_json)
        assert payload["budget"]["over_cap"] is False
        checklist = " ".join(item["text"] for item in payload["checklist"])
        assert "护照" not in checklist
        assert "签证" not in checklist


@pytest.mark.parametrize(
    "code,reason",
    [
        ("destination_not_found", "在国内地图里找不到这个目的地，没有可用的景点信息"),
        ("poi_empty", "检索不到可用景点信息"),
        ("amap_unavailable", "地图服务不可用，没法完成这次检索"),
    ],
)
@pytest.mark.asyncio
async def test_research_failure_templates(client: AsyncClient, monkeypatch, code: str, reason: str) -> None:
    llm = ScriptedLLM(research=[{"ok": False, "reason_code": code, "reason": reason}])
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
    detail = await _wait_status(client, conv_id, {"failed"})
    assert detail["planning"]["itinerary_id"] is None
    coco = [item for item in detail["messages"] if item["role"] == "assistant"][-1]
    assert reason in coco["content"]
    assert coco["content"].strip() not in {"失败", "失败了"}
    assert "没法帮你出方案" in coco["content"]
    assert detail["planning"]["error_message"] == reason
    assert detail["planning"]["error_message"] not in {"失败", "失败了", ""}
    from src.db.session import async_session_maker

    async with async_session_maker() as db:
        rows = list((await db.execute(select(Itinerary).where(Itinerary.conversation_id == conv_id))).scalars())
        assert rows == []


@pytest.mark.asyncio
async def test_garbled_city_ready_then_planning_failed(client: AsyncClient, monkeypatch) -> None:
    reason = "在国内地图里找不到这个目的地，没有可用的景点信息"
    llm = ScriptedLLM(research=[{"ok": False, "reason_code": "destination_not_found", "reason": reason}])
    set_planning_hooks(specialist_chat=llm, registry_factory=lambda: ScriptedRegistry())
    created = assert_ok(await client.post("/api/conversations"), 201)
    conv_id = created["id"]
    monkeypatch.setattr(httpx, "AsyncClient", _manager_client(ASK_WHICH_CITY))
    first = assert_ok(
        await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": GARBLED_MIN_SET},
        )
    )
    assert first["intake"]["ready"] is True
    assert first["intake"]["destination_city"] == GARBLED_CITY
    assert first["intake"]["destination_city"] != "杭州"
    assert first["planning"]["status"] == "running"
    detail = await _wait_status(client, conv_id, {"failed"})
    assert detail["planning"]["itinerary_id"] is None
    assert detail["intake"]["destination_city"] == GARBLED_CITY
    coco = [item for item in detail["messages"] if item["role"] == "assistant"][-1]
    assert reason in coco["content"]
    assert "没法帮你出方案" in coco["content"]
    assert detail["planning"]["error_message"] == reason
    logs = detail["planning"]["activity_log"]
    assert logs
    clickable = [item for item in logs if item["clickable"]]
    assert clickable
    fail_steps = [item for item in clickable if item["detail"]["body"] and reason in (item["detail"]["body"] or "")]
    assert fail_steps
    from src.db.session import async_session_maker

    async with async_session_maker() as db:
        rows = list((await db.execute(select(Itinerary).where(Itinerary.conversation_id == conv_id))).scalars())
        assert rows == []


@pytest.mark.asyncio
async def test_garbled_city_not_rewritten_to_hangzhou(client: AsyncClient, monkeypatch) -> None:
    llm = ScriptedLLM(research=[_research_ok()])
    set_planning_hooks(specialist_chat=llm, registry_factory=lambda: ScriptedRegistry())
    created = assert_ok(await client.post("/api/conversations"), 201)
    conv_id = created["id"]
    monkeypatch.setattr(httpx, "AsyncClient", _manager_client(ASK_WHICH_CITY))
    assert_ok(
        await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": GARBLED_MIN_SET},
        )
    )
    detail = await _wait_status(client, conv_id, {"failed"})
    assert detail["planning"]["itinerary_id"] is None
    assert detail["intake"]["destination_city"] == GARBLED_CITY
    assert detail["planning"]["error_message"] == "在国内地图里找不到这个目的地，没有可用的景点信息"


@pytest.mark.asyncio
async def test_budget_over_cap(client: AsyncClient, monkeypatch) -> None:
    llm = ScriptedLLM(budget=[_budget_ok(over_cap=True)])
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
    detail = await _wait_status(client, conv_id, {"succeeded"})
    from src.db.session import async_session_maker

    async with async_session_maker() as db:
        row = await db.get(Itinerary, detail["planning"]["itinerary_id"])
        payload = json_mod.loads(row.payload_json)
        assert payload["budget"]["over_cap"] is True
        assert payload["budget"]["total_amount"] > payload["budget"]["cap_amount"]


@pytest.mark.asyncio
async def test_running_does_not_start_second_job(client: AsyncClient, monkeypatch) -> None:
    gate = asyncio.Event()

    async def slow_llm(**kwargs):
        if kwargs["role"] == "destination_research":
            await gate.wait()
            return {"content": json_mod.dumps(_research_ok(), ensure_ascii=False), "tool_calls": None, "reasoning": None}
        if kwargs["role"] == "budget_expert":
            return {"content": json_mod.dumps(_budget_ok(), ensure_ascii=False), "tool_calls": None, "reasoning": None}
        return {"content": json_mod.dumps(_itinerary_ok(), ensure_ascii=False), "tool_calls": None, "reasoning": None}

    set_planning_hooks(specialist_chat=slow_llm, registry_factory=lambda: ScriptedRegistry())
    created = assert_ok(await client.post("/api/conversations"), 201)
    conv_id = created["id"]
    monkeypatch.setattr(httpx, "AsyncClient", _manager_client(READY_HANGZHOU))
    first = assert_ok(
        await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "从上海出发，带老婆去杭州玩 5 天，预算 2 万，不要太赶"},
        )
    )
    assert first["planning"]["status"] == "running"
    second = assert_ok(
        await client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "从上海出发再出一版去杭州 5 天"},
        )
    )
    assert second["assistant_message"]["content"] == "⏳ 专员还在做，完成后会放到行程里。"
    assert second["planning"]["status"] == "running"
    from src.db.session import async_session_maker

    async with async_session_maker() as db:
        jobs = list((await db.execute(select(PlanningJob).where(PlanningJob.conversation_id == conv_id))).scalars())
        assert len(jobs) == 1
    gate.set()
    await _wait_status(client, conv_id, {"succeeded", "failed"})
