#!/usr/bin/env python3
"""T-011 第1次返工复验。只看 DOM 与 /api，不请求 /src/*.ts。不写 Key/完整行程正文。"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import websockets

BASE = "http://127.0.0.1:5199"
API = "http://127.0.0.1:8099"
CDP_PORT = 9614
REPORT_DIR = Path(__file__).resolve().parent
SHOTS = REPORT_DIR / "t011-shots"
EVIDENCE = REPORT_DIR / "t011-retest1.json"
SHOTS.mkdir(parents=True, exist_ok=True)

# 开发刚改过的样本不当唯一样本；本轮未改、列表仍有建议。
SUGGEST_ID = "itn_541d4713e1061407"
SUGGEST_CONV = "conv_a66b5537023f598c"
SUGGEST_TEXT = "白天少走路，多坐公交"
LOOSEN_ID = "itn_63f6c180617024d5"
LOOSEN_CONV = "conv_d4db2cfd218d672d"
LOOSEN_TEXT = "第三天不要排那么满"
SPOT_ID = "itn_8d75be294e483e2a"
TIMEOUT_TEXT = "Coco 暂时没有回复"


class Cdp:
    def __init__(self, ws: websockets.ClientConnection) -> None:
        self.ws = ws
        self._id = 0
        self.session_id: str | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self.network: list[dict] = []
        self.src_hits = 0

    async def start(self) -> None:
        asyncio.create_task(self._reader())

    async def _reader(self) -> None:
        async for raw in self.ws:
            msg = json.loads(raw)
            if "id" in msg and msg["id"] in self._pending:
                self._pending[msg["id"]].set_result(msg)
            else:
                method = msg.get("method")
                params = msg.get("params") or {}
                if method == "Network.responseReceived":
                    url = (params.get("response") or {}).get("url", "")
                    status = (params.get("response") or {}).get("status")
                    if "/api/" in url and "/src/" not in url:
                        rec = {
                            "url": url.split("?", 1)[0],
                            "status": status,
                            "type": params.get("type"),
                        }
                        self.network.append(rec)
                    if "/src/" in url and url.endswith((".ts", ".tsx")):
                        self.src_hits += 1
                if method == "Network.requestWillBeSent":
                    url = (params.get("request") or {}).get("url", "")
                    if "/src/" in url and url.endswith((".ts", ".tsx")):
                        self.src_hits += 1

    async def send(self, method: str, params: dict | None = None, session: bool = True) -> dict:
        self._id += 1
        payload: dict = {"id": self._id, "method": method, "params": params or {}}
        if session and self.session_id:
            payload["sessionId"] = self.session_id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[self._id] = fut
        await self.ws.send(json.dumps(payload))
        msg = await asyncio.wait_for(fut, timeout=25)
        if "error" in msg:
            raise RuntimeError(f"{method}: {msg['error']}")
        return msg.get("result") or {}

    async def eval(self, expression: str, await_promise: bool = True) -> object:
        result = await self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
            },
        )
        if result.get("exceptionDetails"):
            text = result["exceptionDetails"].get("text") or json.dumps(result["exceptionDetails"])
            raise RuntimeError(f"eval: {text}")
        return (result.get("result") or {}).get("value")

    async def screenshot(self, name: str) -> str:
        try:
            data = await self.send(
                "Page.captureScreenshot",
                {"format": "png", "captureBeyondViewport": False},
            )
            path = SHOTS / name
            path.write_bytes(__import__("base64").b64decode(data["data"]))
            return str(path)
        except Exception as exc:
            return f"FAILED:{type(exc).__name__}"


SNAP_JS = r"""
(() => {
  const text = document.body ? document.body.innerText : '';
  const chips = [...document.querySelectorAll('.day-chip')].map((n) => ({
    text: (n.textContent || '').trim(),
    selected: n.classList.contains('is-selected') || n.getAttribute('aria-selected') === 'true',
  }));
  const days = [...document.querySelectorAll('[data-day]')].map((n) => ({
    day: n.getAttribute('data-day'),
    cards: n.querySelectorAll('.itinerary-card').length,
    legs: [...n.querySelectorAll('.transit-leg')].map((leg) => (leg.textContent || '').trim()),
    titles: [...n.querySelectorAll('.itinerary-card strong')].map((t) => (t.textContent || '').trim()),
  }));
  const suggest = [...document.querySelectorAll('.suggest-chip')].map((n) => (n.textContent || '').trim());
  const users = [...document.querySelectorAll('.side-bubble')].map((n) => (n.textContent || '').trim());
  const coco = [...document.querySelectorAll('.side-row.coco')].map((n) => (n.textContent || '').replace(/^C\s*Coco/, '').trim());
  return {
    href: location.href,
    path: location.pathname,
    title: (document.querySelector('.detail-title-row h1') || {}).textContent || '',
    hasMock: text.includes('[Mock]'),
    hasPdf: /PDF|导出行程|下载行程/.test(text),
    hasPassport: /护照|签证/.test(text),
    hasBudget: /预算/.test(text),
    hasChecklist: /行前清单/.test(text),
    hasMapBtn: /地图模式|返回行程/.test(text),
    mapUnconfigured: text.includes('地图未配置'),
    chips,
    days,
    dayCount: days.length || chips.length,
    suggest,
    users,
    cocoLast: coco.slice(-1)[0] || '',
    cocoHasTimeout: coco.some((t) => t.includes('暂时没有回复')),
    tripRows: document.querySelectorAll('.trip-row').length,
    composer: !!document.querySelector('textarea[aria-label="给 Coco 发修改"], textarea[aria-label="给 Coco 发消息"]'),
    revising: text.includes('Coco 正在改这份行程'),
  };
})()
"""


async def snap(cdp: Cdp) -> dict:
    return await cdp.eval(SNAP_JS) or {}


async def wait_snap(cdp: Cdp, pred, timeout: float = 20.0) -> dict:
    last = {}
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        last = await snap(cdp)
        if pred(last):
            return last
        await asyncio.sleep(0.3)
    return last


async def fetch_itinerary(cdp: Cdp, itinerary_id: str) -> dict:
    return await cdp.eval(
        f"""
        (async () => {{
          const res = await fetch('/api/itineraries/' + {json.dumps(itinerary_id)});
          const body = await res.json();
          const d = body.data || {{}};
          const days = (d.days || []).map((day) => ({{
            day: day.day_index,
            n: (day.cards || []).length,
            titles: (day.cards || []).map((c) => (c.title || '').slice(0, 16)),
            types: (day.cards || []).map((c) => c.type),
            lodging: (day.cards || []).filter((c) => c.type === 'lodging').map((c) => (c.title || '').slice(0, 16)),
            legs: (day.legs || []).map((leg) => ({{
              mode: leg.mode,
              source: leg.source,
              duration_min: leg.duration_min,
              distance_m: leg.distance_m,
              summary: (leg.summary || '').slice(0, 40),
            }})),
          }}));
          return {{
            http: res.status,
            id: d.id,
            conv: d.conversation_id,
            city: d.destination_city,
            days: d.duration_days,
            updated: d.updated_at,
            qs: (d.quick_suggestions || []).map((q) => (q.text || '').slice(0, 20)),
            dayRows: days,
          }};
        }})()
        """
    )


async def fetch_planning(cdp: Cdp, conv_id: str) -> dict:
    return await cdp.eval(
        f"""
        (async () => {{
          const res = await fetch('/api/conversations/' + {json.dumps(conv_id)});
          const body = await res.json();
          const d = body.data || {{}};
          const p = d.planning || {{}};
          const msgs = d.messages || [];
          const specs = (p.specialists || []).map((s) => ({{ role: s.role, status: s.status }}));
          return {{
            http: res.status,
            id: d.id,
            planning: p.status,
            itinerary_id: p.itinerary_id,
            specs,
            running: specs.some((s) => s.status === 'running') || p.status === 'running',
            allSucceeded: specs.length >= 3 && specs.every((s) => s.status === 'succeeded'),
            user_n: msgs.filter((m) => m.role === 'user').length,
            last_user: (([...msgs].reverse().find((m) => m.role === 'user') || {{}}).content || '').slice(0, 40),
            last_assistant: (([...msgs].reverse().find((m) => m.role === 'assistant') || {{}}).content || '').slice(0, 80),
          }};
        }})()
        """
    )


async def wait_detail(cdp: Cdp, itinerary_id: str, timeout: float = 25.0) -> dict:
    return await wait_snap(
        cdp,
        lambda s: s
        and itinerary_id in (s.get("path") or "")
        and s.get("hasBudget")
        and (s.get("dayCount") or 0) >= 1
        and not s.get("revising"),
        timeout=timeout,
    )


async def open_trips(cdp: Cdp) -> dict:
    clicked = await cdp.eval(
        """
        (() => {
          const btn = [...document.querySelectorAll('.nav-item')].find((n) => (n.textContent || '').includes('行程'));
          if (!btn) return false;
          btn.click();
          return true;
        })()
        """
    )
    if not clicked:
        await cdp.send("Page.navigate", {"url": BASE + "/trips"})
    return await wait_snap(cdp, lambda s: s and s.get("tripRows", 0) > 0, timeout=15)


async def click_trip_by_id(cdp: Cdp, itinerary_id: str) -> bool:
    await wait_snap(cdp, lambda s: s and s.get("tripRows", 0) > 0, timeout=20)
    result = await cdp.eval(
        f"""
        (async () => {{
          try {{
            const res = await fetch('/api/itineraries?page=1&page_size=20');
            const text = await res.text();
            let body = {{}};
            try {{ body = JSON.parse(text); }} catch (e) {{
              return {{ok:false, reason:'bad-json', status: res.status}};
            }}
            const items = body.data || [];
            const idx = items.findIndex((it) => it.id === {json.dumps(itinerary_id)});
            const rows = [...document.querySelectorAll('.trip-row')];
            if (idx < 0 || !rows[idx]) return {{ok:false, reason:'no-row', idx, rows: rows.length, status: res.status}};
            rows[idx].scrollIntoView({{block:'center'}});
            rows[idx].click();
            return {{ok:true, idx, status: res.status}};
          }} catch (e) {{
            return {{ok:false, reason: String(e)}};
          }}
        }})()
        """
    )
    return bool(isinstance(result, dict) and result.get("ok"))


async def box_of(cdp: Cdp, expression: str) -> dict | None:
    return await cdp.eval(
        f"""
        (() => {{
          const el = {expression};
          if (!el) return null;
          el.scrollIntoView({{block:'center'}});
          const r = el.getBoundingClientRect();
          return {{x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height}};
        }})()
        """
    )


async def mouse_click(cdp: Cdp, x: float, y: float) -> None:
    await cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    await cdp.send(
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
    )
    await cdp.send(
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
    )


async def click_chip(cdp: Cdp, text: str) -> dict:
    box = await box_of(
        cdp,
        f"[...document.querySelectorAll('.suggest-chip')].find((n) => (n.textContent || '').includes({json.dumps(text)}))",
    )
    if not box:
        return {"ok": False, "reason": "no-chip"}
    await mouse_click(cdp, box["x"], box["y"])
    return {"ok": True, "box": box}


async def fill_and_send(cdp: Cdp, value: str) -> dict:
    filled = await cdp.eval(
        f"""
        (() => {{
          const el = document.querySelector('textarea[aria-label="给 Coco 发修改"]');
          if (!el) return false;
          const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
          setter.call(el, {json.dumps(value)});
          el.dispatchEvent(new Event('input', {{bubbles:true}}));
          return true;
        }})()
        """
    )
    if not filled:
        return {"ok": False, "reason": "no-textarea"}
    box = await box_of(cdp, 'document.querySelector(\'button[aria-label="发送"]\')')
    if not box:
        return {"ok": False, "reason": "no-send"}
    await mouse_click(cdp, box["x"], box["y"])
    return {"ok": True, "box": box}


def flatten_legs(api: dict) -> list[dict]:
    out = []
    for row in api.get("dayRows") or []:
        for leg in row.get("legs") or []:
            out.append(
                {
                    "day": row.get("day"),
                    "mode": leg.get("mode"),
                    "duration_min": leg.get("duration_min"),
                    "summary": leg.get("summary"),
                    "source": leg.get("source"),
                }
            )
    return out


def flatten_lodging(api: dict) -> list[str]:
    out = []
    for row in api.get("dayRows") or []:
        out.extend(row.get("lodging") or [])
    return out


def flatten_titles(api: dict) -> list[tuple]:
    return [(row.get("day"), row.get("n"), row.get("titles")) for row in (api.get("dayRows") or [])]


def scheme_delta(before: dict, after: dict) -> dict:
    b_legs = flatten_legs(before)
    a_legs = flatten_legs(after)
    b_lodging = flatten_lodging(before)
    a_lodging = flatten_lodging(after)
    b_titles = flatten_titles(before)
    a_titles = flatten_titles(after)
    return {
        "updated_changed": before.get("updated") != after.get("updated"),
        "id_same": before.get("id") == after.get("id"),
        "cards_changed": b_titles != a_titles,
        "legs_changed": b_legs != a_legs,
        "lodging_changed": b_lodging != a_lodging,
        "before_days": [(r.get("day"), r.get("n")) for r in (before.get("dayRows") or [])],
        "after_days": [(r.get("day"), r.get("n")) for r in (after.get("dayRows") or [])],
        "before_legs": b_legs,
        "after_legs": a_legs,
        "before_lodging": b_lodging,
        "after_lodging": a_lodging,
    }


async def wait_revision(cdp: Cdp, itinerary_id: str, before_updated: str, timeout: float = 185.0) -> tuple[dict, dict, float]:
    started = time.monotonic()
    last_api: dict = {}
    last_snap: dict = {}
    while time.monotonic() - started < timeout:
        last_snap = await snap(cdp)
        last_api = await fetch_itinerary(cdp, itinerary_id)
        changed = last_api.get("updated") and last_api.get("updated") != before_updated
        done = not last_snap.get("revising")
        timeout_ui = last_snap.get("cocoHasTimeout") or TIMEOUT_TEXT in (last_snap.get("cocoLast") or "")
        if timeout_ui and done:
            return last_snap, last_api, time.monotonic() - started
        if changed and done:
            return last_snap, last_api, time.monotonic() - started
        await asyncio.sleep(1.0)
    return last_snap, last_api, time.monotonic() - started


def judge(ok: bool, **extra) -> dict:
    out = {"result": "PASS" if ok else "FAIL"}
    out.update(extra)
    return out


async def run() -> dict:
    import urllib.request

    version = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version").read())
    ws_url = version["webSocketDebuggerUrl"]
    evidence: dict = {
        "round": "retest1",
        "chrome": version.get("Browser"),
        "cdp": "Target.createTarget + attachToTarget flatten",
        "frontend": BASE,
        "backend": API,
        "vite_use_mock": False,
        "reused_services": {
            "backend_8099": {
                "note": "开发残留 PID 28142 在本轮开始后已退出；Tester 用项目 .venv 重新拉起",
                "tester_started": True,
            },
            "frontend_5199": {"pid": 98000, "started": "2026-09-13 16:46:48", "tester_started": False},
        },
        "samples": {
            "ac019": SUGGEST_ID,
            "ac018": LOOSEN_ID,
            "spot": SPOT_ID,
            "excluded_dev_only": ["itn_15845ef143d2cc56", "itn_e6e7ea18e5abc6c2"],
        },
        "acs": {},
        "tech": {},
        "experience": {},
    }

    async with websockets.connect(ws_url, max_size=20_000_000) as ws:
        cdp = Cdp(ws)
        await cdp.start()
        created = await cdp.send("Target.createTarget", {"url": "about:blank"}, session=False)
        target_id = created["targetId"]
        attached = await cdp.send(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
            session=False,
        )
        cdp.session_id = attached["sessionId"]
        await cdp.send("Page.enable")
        await cdp.send("Runtime.enable")
        await cdp.send("Network.enable")
        await cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
        )

        await cdp.send("Page.navigate", {"url": BASE + "/"})
        home = await wait_snap(cdp, lambda s: s and (s.get("composer") or s.get("path") == "/"), timeout=20)
        await cdp.screenshot("r1-00-home.png")
        evidence["home"] = {"hasMock": home.get("hasMock"), "path": home.get("path")}
        if home.get("hasMock"):
            evidence["acs"]["AC-019"] = {"result": "FAIL", "reason": "首页出现 [Mock]"}
            EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            return evidence

        trips = await open_trips(cdp)
        await cdp.screenshot("r1-01-trips.png")
        evidence["trips"] = {"rows": trips.get("tripRows"), "hasMock": trips.get("hasMock")}

        # --- AC-019 click chip ---
        clicked_row = await click_trip_by_id(cdp, SUGGEST_ID)
        before_page = await wait_detail(cdp, SUGGEST_ID, timeout=25)
        before_api = await fetch_itinerary(cdp, SUGGEST_ID)
        before_plan = await fetch_planning(cdp, SUGGEST_CONV)
        await cdp.screenshot("r1-019-before.png")
        chip_click = await click_chip(cdp, SUGGEST_TEXT)
        immediately = await wait_snap(
            cdp,
            lambda s: s
            and (
                SUGGEST_TEXT in " ".join(s.get("users") or [])
                or not s.get("suggest")
                or s.get("revising")
            ),
            timeout=8,
        )
        await cdp.screenshot("r1-019-clicked.png")
        snap_019, api_019, wait_019 = await wait_revision(
            cdp, SUGGEST_ID, before_api.get("updated") or "", timeout=185
        )
        after_plan = await fetch_planning(cdp, SUGGEST_CONV)
        await cdp.screenshot("r1-019-after.png")
        delta_019 = scheme_delta(before_api, api_019)
        user_sug = any(SUGGEST_TEXT in (u or "") for u in (snap_019.get("users") or []) + (immediately.get("users") or []))
        chips_gone = len(immediately.get("suggest") or []) == 0 and len(snap_019.get("suggest") or []) == 0
        coco_last = snap_019.get("cocoLast") or after_plan.get("last_assistant") or ""
        timeout_ui = bool(snap_019.get("cocoHasTimeout")) or TIMEOUT_TEXT in coco_last
        coco_replied = bool(coco_last) and not timeout_ui
        same_019 = api_019.get("id") == SUGGEST_ID == after_plan.get("itinerary_id")
        observable = bool(delta_019["cards_changed"] or delta_019["legs_changed"] or delta_019["lodging_changed"])
        ac019 = (
            bool(clicked_row)
            and bool(chip_click.get("ok"))
            and user_sug
            and chips_gone
            and same_019
            and coco_replied
            and observable
            and not before_page.get("hasMock")
        )
        evidence["acs"]["AC-019"] = judge(
            ac019,
            clicked_row=clicked_row,
            chip_click=chip_click,
            wait_seconds=round(wait_019, 1),
            user_has_text=user_sug,
            chips_before=before_page.get("suggest"),
            chips_immediate=immediately.get("suggest"),
            chips_gone=chips_gone,
            same_id=same_019,
            timeout_ui=timeout_ui,
            coco_replied=coco_replied,
            coco_last=coco_last[:80],
            revising_end=snap_019.get("revising"),
            observable=observable,
            delta=delta_019,
            before_plan={"planning": before_plan.get("planning"), "user_n": before_plan.get("user_n")},
            after_plan=after_plan,
        )

        # --- AC-018 typed loosen on a different itinerary ---
        await open_trips(cdp)
        clicked_loosen = await click_trip_by_id(cdp, LOOSEN_ID)
        loosen_page = await wait_detail(cdp, LOOSEN_ID, timeout=25)
        before_018 = await fetch_itinerary(cdp, LOOSEN_ID)
        before_018_plan = await fetch_planning(cdp, LOOSEN_CONV)
        await cdp.screenshot("r1-018-before.png")
        day3_before = next((r for r in (before_018.get("dayRows") or []) if r.get("day") == 3), {})
        send_018 = await fill_and_send(cdp, LOOSEN_TEXT)
        immediately_018 = await wait_snap(
            cdp,
            lambda s: s and (LOOSEN_TEXT in " ".join(s.get("users") or []) or s.get("revising")),
            timeout=8,
        )
        snap_018, api_018, wait_018 = await wait_revision(
            cdp, LOOSEN_ID, before_018.get("updated") or "", timeout=185
        )
        after_018_plan = await fetch_planning(cdp, LOOSEN_CONV)
        await cdp.screenshot("r1-018-after.png")
        day3_after = next((r for r in (api_018.get("dayRows") or []) if r.get("day") == 3), {})
        user_018 = any(LOOSEN_TEXT in (u or "") for u in (snap_018.get("users") or []) + (immediately_018.get("users") or []))
        same_018 = api_018.get("id") == LOOSEN_ID == after_018_plan.get("itinerary_id")
        timeout_018 = bool(snap_018.get("cocoHasTimeout")) or TIMEOUT_TEXT in (snap_018.get("cocoLast") or "")
        coco_018 = bool(snap_018.get("cocoLast")) and not timeout_018
        loosened = (day3_after.get("n") or 99) < (day3_before.get("n") or 0) or (
            (day3_after.get("n") or 0) <= (day3_before.get("n") or 0)
            and (day3_after.get("titles") or []) != (day3_before.get("titles") or [])
        )
        # 变少或变松：卡片数下降，或同数但点位换松。本轮以第 3 天卡片变少为主。
        ac018 = (
            bool(clicked_loosen)
            and bool(send_018.get("ok"))
            and user_018
            and same_018
            and coco_018
            and loosened
            and not loosen_page.get("hasMock")
        )
        evidence["acs"]["AC-018"] = judge(
            ac018,
            clicked_row=clicked_loosen,
            send=send_018,
            wait_seconds=round(wait_018, 1),
            user_has_text=user_018,
            same_id=same_018,
            timeout_ui=timeout_018,
            coco_replied=coco_018,
            coco_last=(snap_018.get("cocoLast") or "")[:80],
            day3_before_n=day3_before.get("n"),
            day3_after_n=day3_after.get("n"),
            day3_before_titles=day3_before.get("titles"),
            day3_after_titles=day3_after.get("titles"),
            loosened=loosened,
            after_plan=after_018_plan,
            suggest_after=snap_018.get("suggest"),
        )

        # --- 抽检：打开另一份详情仍有报告 + 地图入口 ---
        await open_trips(cdp)
        clicked_spot = await click_trip_by_id(cdp, SPOT_ID)
        spot = await wait_detail(cdp, SPOT_ID, timeout=25)
        await cdp.screenshot("r1-spot-detail.png")
        spot_ok = (
            bool(clicked_spot)
            and SPOT_ID in (spot.get("path") or "")
            and spot.get("hasBudget")
            and spot.get("hasChecklist")
            and spot.get("hasMapBtn")
            and (spot.get("dayCount") or 0) >= 1
            and not spot.get("hasMock")
        )
        evidence["acs"]["spot_report_map"] = judge(
            spot_ok,
            path=spot.get("path"),
            hasBudget=spot.get("hasBudget"),
            hasChecklist=spot.get("hasChecklist"),
            hasMapBtn=spot.get("hasMapBtn"),
            dayCount=spot.get("dayCount"),
            hasMock=spot.get("hasMock"),
            mapUnconfigured=spot.get("mapUnconfigured"),
        )

        evidence["tech"]["src_hits"] = cdp.src_hits
        evidence["tech"]["api_sample"] = [
            rec for rec in cdp.network if "/api/" in rec.get("url", "")
        ][-20:]
        evidence["experience"] = {
            "timeout_180s": {
                "ac019_wait": evidence["acs"]["AC-019"].get("wait_seconds"),
                "ac019_timeout_ui": evidence["acs"]["AC-019"].get("timeout_ui"),
                "ac018_wait": evidence["acs"]["AC-018"].get("wait_seconds"),
                "ac018_timeout_ui": evidence["acs"]["AC-018"].get("timeout_ui"),
            },
            "chip_mapping": {
                "observable": evidence["acs"]["AC-019"].get("observable"),
                "legs_changed": delta_019.get("legs_changed"),
                "cards_changed": delta_019.get("cards_changed"),
                "lodging_changed": delta_019.get("lodging_changed"),
            },
            "no_curl_src": {"src_hits": cdp.src_hits, "tester_curled_src": False},
        }
        EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        return evidence


if __name__ == "__main__":
    result = asyncio.run(run())
    print(json.dumps({k: result.get(k) for k in ("chrome", "samples", "acs", "experience", "tech")}, ensure_ascii=False, indent=2))
