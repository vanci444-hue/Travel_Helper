#!/usr/bin/env python3
"""T-012 Chrome 152 CDP：并排打开两份真行程详情。只看 DOM 与 /api，不请求 /src/*.ts。"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import websockets

BASE = "http://127.0.0.1:5199"
API = "http://127.0.0.1:8099"
CDP_PORT = 9615
REPORT_DIR = Path(__file__).resolve().parent
SHOTS = REPORT_DIR / "t012-shots"
EVIDENCE = REPORT_DIR / "t012-evidence.json"
SHOTS.mkdir(parents=True, exist_ok=True)

FAMILY_ID = "itn_d4d2b9088b2d5460"
COUPLE_ID = "itn_f173091eb7516ae0"

SNAP_JS = r"""
(() => {
  const path = location.pathname;
  const h1 = document.querySelector('h1')?.textContent?.trim() || '';
  const sub = document.querySelector('.detail-sub')?.textContent?.trim() || '';
  const mock = !!document.querySelector('.mock-badge') || /\[Mock\]/.test(document.body.innerText || '');
  const days = [...document.querySelectorAll('.day-section')].map((sec) => {
    const label = sec.querySelector('h2')?.textContent?.trim() || '';
    const cards = [...sec.querySelectorAll('.itinerary-card')].map((card) => {
      const title = card.querySelector('strong')?.textContent?.trim()
        || card.querySelector('.itinerary-card-main')?.textContent?.trim()
        || '';
      const meta = card.querySelector('.itinerary-card-meta')?.textContent?.trim() || '';
      return { title: title.slice(0, 40), meta: meta.slice(0, 80) };
    });
    return { day: sec.getAttribute('data-day'), label, cardCount: cards.length, titles: cards.map((c) => c.title) };
  });
  return {
    path,
    title: h1.slice(0, 40),
    sub: sub.slice(0, 80),
    hasMock: mock,
    days,
    bodyHasMock: /\[Mock\]/.test(document.body.innerText || ''),
  };
})()
"""

FETCH_JS = r"""
(async (id) => {
  const res = await fetch('/api/itineraries/' + id);
  const raw = await res.json();
  const d = raw.data || {};
  const days = (d.days || []).map((day) => {
    const cards = day.cards || [];
    return {
      day_index: day.day_index,
      attraction: cards.filter((c) => c.type === 'attraction').length,
      lodging: cards.filter((c) => c.type === 'lodging').length,
      other: cards.filter((c) => c.type !== 'attraction' && c.type !== 'lodging').length,
      titles: cards.map((c) => (c.title || '').slice(0, 30)),
      types: cards.map((c) => c.type),
      child_flags: cards.map((c) => c.suitable_for_children),
      intro_heads: cards.map((c) => String(c.intro || '').slice(0, 40)),
      intro_has_pitfall: cards.map((c) => /避坑/.test(c.intro || '')),
      intro_has_couple: cards.map((c) => /情侣/.test(c.intro || '')),
    };
  });
  return {
    ok: !!raw.success,
    status: res.status,
    id: d.id,
    conversation_id: d.conversation_id,
    destination_city: d.destination_city,
    origin_city: d.origin_city,
    duration_days: d.duration_days,
    pace: d.pace,
    companion_type: d.companion_type,
    title: (d.title || '').slice(0, 40),
    days,
    created_at: d.created_at,
    updated_at: d.updated_at,
  };
})
"""


class Conn:
    def __init__(self, ws: websockets.ClientConnection) -> None:
        self.ws = ws
        self._id = 0
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
                continue
            method = msg.get("method")
            params = msg.get("params") or {}
            if method == "Network.responseReceived":
                url = ((params.get("response") or {}).get("url") or "")
                status = (params.get("response") or {}).get("status")
                if "/api/" in url and "/src/" not in url:
                    self.network.append({"url": url.split("?", 1)[0], "status": status})
            if method == "Network.requestWillBeSent":
                url = ((params.get("request") or {}).get("url") or "")
                if "/src/" in url and url.endswith((".ts", ".tsx")):
                    self.src_hits += 1

    async def send(self, method: str, params: dict | None = None, session_id: str | None = None) -> dict:
        self._id += 1
        payload: dict = {"id": self._id, "method": method, "params": params or {}}
        if session_id:
            payload["sessionId"] = session_id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[self._id] = fut
        await self.ws.send(json.dumps(payload))
        msg = await asyncio.wait_for(fut, timeout=25)
        if "error" in msg:
            raise RuntimeError(f"{method}: {msg['error']}")
        return msg.get("result") or {}

    async def eval(self, session_id: str, expression: str, await_promise: bool = True) -> object:
        result = await self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
            },
            session_id=session_id,
        )
        if result.get("exceptionDetails"):
            text = result["exceptionDetails"].get("text") or json.dumps(result["exceptionDetails"])
            raise RuntimeError(f"eval: {text}")
        return (result.get("result") or {}).get("value")

    async def screenshot(self, session_id: str, name: str) -> str:
        data = await self.send(
            "Page.captureScreenshot",
            {"format": "png", "captureBeyondViewport": False},
            session_id=session_id,
        )
        path = SHOTS / name
        path.write_bytes(__import__("base64").b64decode(data["data"]))
        return str(path)


async def wait_eval(conn: Conn, session_id: str, expression: str, pred, timeout: float = 30.0):
    started = time.monotonic()
    last = None
    while time.monotonic() - started < timeout:
        last = await conn.eval(session_id, expression)
        if pred(last):
            return last
        await asyncio.sleep(0.3)
    return last


async def open_page(conn: Conn, url: str, left: int, top: int, width: int, height: int) -> str:
    created = await conn.send(
        "Target.createTarget",
        {"url": "about:blank", "newWindow": True, "width": width, "height": height},
    )
    target_id = created["targetId"]
    attached = await conn.send("Target.attachToTarget", {"targetId": target_id, "flatten": True})
    session_id = attached["sessionId"]
    await conn.send("Page.enable", session_id=session_id)
    await conn.send("Runtime.enable", session_id=session_id)
    await conn.send("Network.enable", session_id=session_id)
    try:
        win = await conn.send("Browser.getWindowForTarget", {"targetId": target_id})
        window_id = win.get("windowId")
        if window_id is not None:
            await conn.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_id,
                    "bounds": {
                        "left": left,
                        "top": top,
                        "width": width,
                        "height": height,
                        "windowState": "normal",
                    },
                },
            )
    except Exception:
        pass
    await conn.send(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
        session_id=session_id,
    )
    await conn.send("Page.navigate", {"url": url}, session_id=session_id)
    return session_id


async def run() -> dict:
    import urllib.request

    version = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version").read())
    ws_url = version["webSocketDebuggerUrl"]
    evidence: dict = {
        "chrome": version.get("Browser"),
        "cdp": "Target.createTarget + attachToTarget flatten + newWindow side-by-side",
        "frontend": BASE,
        "backend": API,
        "vite_use_mock": False,
        "src_curl": False,
        "samples": {},
        "acs": {},
        "tech": {},
        "experience": {},
    }

    async with websockets.connect(ws_url, max_size=20_000_000) as ws:
        conn = Conn(ws)
        await conn.start()

        family_sid = await open_page(conn, f"{BASE}/itineraries/{FAMILY_ID}", 0, 40, 900, 900)
        couple_sid = await open_page(conn, f"{BASE}/itineraries/{COUPLE_ID}", 900, 40, 900, 900)

        family_dom = await wait_eval(
            conn,
            family_sid,
            SNAP_JS,
            lambda s: s and s.get("days") and len(s.get("days") or []) >= 3 and FAMILY_ID in (s.get("path") or ""),
        )
        couple_dom = await wait_eval(
            conn,
            couple_sid,
            SNAP_JS,
            lambda s: s and s.get("days") and len(s.get("days") or []) >= 3 and COUPLE_ID in (s.get("path") or ""),
        )

        family_shot = await conn.screenshot(family_sid, "01-family-relaxed.png")
        couple_shot = await conn.screenshot(couple_sid, "02-couple-packed.png")

        await conn.eval(family_sid, "document.querySelector('[data-day=\"2\"]')?.scrollIntoView({block:'start'})")
        await asyncio.sleep(0.4)
        family_day2 = await conn.screenshot(family_sid, "03-family-day2.png")
        await conn.eval(couple_sid, "document.querySelector('[data-day=\"2\"]')?.scrollIntoView({block:'start'})")
        await asyncio.sleep(0.4)
        couple_day2 = await conn.screenshot(couple_sid, "04-couple-day2.png")

        family_api = await conn.eval(family_sid, f"({FETCH_JS})('{FAMILY_ID}')")
        couple_api = await conn.eval(couple_sid, f"({FETCH_JS})('{COUPLE_ID}')")

        family_counts = [d.get("attraction", 0) for d in (family_api or {}).get("days") or []]
        couple_counts = [d.get("attraction", 0) for d in (couple_api or {}).get("days") or []]
        family_titles = [tuple(d.get("titles") or []) for d in (family_api or {}).get("days") or []]
        couple_titles = [tuple(d.get("titles") or []) for d in (couple_api or {}).get("days") or []]
        same_payload = family_titles == couple_titles and family_counts == couple_counts

        family_pitfall = any(any(d.get("intro_has_pitfall") or []) for d in (family_api or {}).get("days") or [])
        couple_intro = any(any(d.get("intro_has_couple") or []) for d in (couple_api or {}).get("days") or [])
        density_ok = (
            bool(family_counts)
            and bool(couple_counts)
            and all(1 <= n <= 2 for n in family_counts)
            and all(3 <= n <= 4 for n in couple_counts)
        )
        type_ok = family_pitfall or couple_intro
        same_city_days = (
            (family_api or {}).get("destination_city") == (couple_api or {}).get("destination_city")
            and (family_api or {}).get("duration_days") == (couple_api or {}).get("duration_days")
            and bool((family_api or {}).get("destination_city"))
        )
        only_companion_pace_diff = (
            (family_api or {}).get("companion_type") != (couple_api or {}).get("companion_type")
            and (family_api or {}).get("pace") != (couple_api or {}).get("pace")
        )
        two_ids = (family_api or {}).get("id") != (couple_api or {}).get("id") and bool((family_api or {}).get("id"))
        no_mock = not (family_dom or {}).get("hasMock") and not (couple_dom or {}).get("hasMock")
        not_hangzhou_main = "杭州" not in str((family_api or {}).get("destination_city")) and "杭州" not in str(
            (couple_api or {}).get("destination_city")
        )
        ac_pass = all(
            [two_ids, same_city_days, only_companion_pace_diff, (density_ok or type_ok), not same_payload, no_mock]
        )

        evidence["samples"] = {
            "family": {"dom": family_dom, "api": family_api, "shots": [family_shot, family_day2]},
            "couple": {"dom": couple_dom, "api": couple_api, "shots": [couple_shot, couple_day2]},
        }
        evidence["tech"] = {
            "two_ids": two_ids,
            "ids": [(family_api or {}).get("id"), (couple_api or {}).get("id")],
            "same_city_days": same_city_days,
            "city": (family_api or {}).get("destination_city"),
            "days": (family_api or {}).get("duration_days"),
            "family_pace_companion": [(family_api or {}).get("pace"), (family_api or {}).get("companion_type")],
            "couple_pace_companion": [(couple_api or {}).get("pace"), (couple_api or {}).get("companion_type")],
            "family_attraction_counts": family_counts,
            "couple_attraction_counts": couple_counts,
            "density_ok": density_ok,
            "type_ok": type_ok,
            "family_pitfall": family_pitfall,
            "couple_intro_couple": couple_intro,
            "same_payload_titles_only": same_payload,
            "no_mock_badge": no_mock,
            "not_hangzhou_main_path": not_hangzhou_main,
            "api_via_vite_proxy": True,
            "src_hits_in_cdp_listener": conn.src_hits,
            "itinerary_api_urls": [n for n in conn.network if "/itineraries/" in n.get("url", "")],
        }
        evidence["acs"]["AC-008"] = {
            "result": "PASS" if ac_pass else "FAIL",
            "density_or_type": density_ok or type_ok,
            "not_title_swap": not same_payload,
        }
        evidence["overall"] = "PASS" if ac_pass else "FAIL"

    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "overall": evidence["overall"],
                "chrome": evidence["chrome"],
                "acs": evidence["acs"],
                "tech": {k: evidence["tech"][k] for k in (
                    "two_ids",
                    "ids",
                    "same_city_days",
                    "city",
                    "days",
                    "family_pace_companion",
                    "couple_pace_companion",
                    "family_attraction_counts",
                    "couple_attraction_counts",
                    "density_ok",
                    "type_ok",
                    "same_payload_titles_only",
                    "no_mock_badge",
                )},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return evidence


if __name__ == "__main__":
    asyncio.run(run())
