#!/usr/bin/env python3
"""T-009 Chrome 152 CDP 验收。只看 DOM 与 /api，不请求 /src/*.ts。"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

import websockets

BASE = "http://127.0.0.1:5199"
API = "http://127.0.0.1:8099"
SHOTS = Path(__file__).resolve().parent / "t009-shots"
EVIDENCE = Path(__file__).resolve().parent / "t009-evidence.json"
SHOTS.mkdir(parents=True, exist_ok=True)


class Cdp:
    def __init__(self, ws: websockets.ClientConnection) -> None:
        self.ws = ws
        self._id = 0
        self.session_id: str | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._events: asyncio.Queue = asyncio.Queue()
        self.network: list[dict] = []

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
                    if "/api/" in url and "/src/" not in url:
                        self.network.append(
                            {
                                "url": url.split("?", 1)[0],
                                "status": (params.get("response") or {}).get("status"),
                                "method": (params.get("response") or {}).get("headers", {}),
                                "req": params.get("type"),
                            }
                        )
                await self._events.put(msg)

    async def send(self, method: str, params: dict | None = None, session: bool = True) -> dict:
        self._id += 1
        payload: dict = {"id": self._id, "method": method, "params": params or {}}
        if session and self.session_id:
            payload["sessionId"] = self.session_id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[self._id] = fut
        await self.ws.send(json.dumps(payload))
        msg = await asyncio.wait_for(fut, timeout=60)
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
        data = await self.send("Page.captureScreenshot", {"format": "png"})
        path = SHOTS / name
        path.write_bytes(__import__("base64").b64decode(data["data"]))
        return str(path)


SNAP_JS = r"""
(() => {
  const text = document.body ? document.body.innerText : '';
  const cards = [...document.querySelectorAll('.inspiration-card')].map((card) => {
    const img = card.querySelector('.inspiration-photo');
    const city = card.querySelector('.inspiration-city');
    const title = card.querySelector('h3');
    const reason = card.querySelector('.inspiration-reason');
    const imgBox = img ? img.getBoundingClientRect() : null;
    const cap = card.querySelector('.inspiration-caption');
    const capBox = cap ? cap.getBoundingClientRect() : null;
    const cityBox = city ? city.getBoundingClientRect() : null;
    const overlay = !!(imgBox && cityBox && cityBox.top < imgBox.bottom - 4 && cityBox.bottom > imgBox.top + 4);
    return {
      city: city ? city.textContent.trim() : '',
      title: title ? title.textContent.trim() : '',
      reason: reason ? reason.textContent.trim() : '',
      imgOk: !!(img && img.naturalWidth > 0),
      imgW: img ? img.naturalWidth : 0,
      imgH: img ? img.naturalHeight : 0,
      imgSrc: img ? img.getAttribute('src') : '',
      overlay,
      captionBelow: !!(imgBox && capBox && capBox.top >= imgBox.bottom - 2),
    };
  });
  const specs = [...document.querySelectorAll('.spec-row')].map((n) => n.textContent.trim());
  const coco = [...document.querySelectorAll('.coco-text')].map((n) => n.textContent.trim());
  const users = [...document.querySelectorAll('.user-bubble')].map((n) => n.textContent.trim());
  const mapSlot = !!document.querySelector('.map-slot');
  const mapCopy = document.querySelector('.map-slot-copy');
  const amap = !!document.querySelector('.amap-container, .amap-layers, canvas.amap-layer');
  const canvasCount = document.querySelectorAll('.map-slot canvas').length;
  return {
    href: location.href,
    path: location.pathname,
    title: document.title,
    hasMock: text.includes('[Mock]'),
    mockCount: (text.match(/\[Mock\]/g) || []).length,
    welcome: !!document.querySelector('.welcome'),
    welcomeText: (document.querySelector('.welcome') || {}).innerText || '',
    leftNav: [...document.querySelectorAll('.nav-item')].map((n) => n.textContent.trim()),
    composer: !!document.querySelector('textarea[aria-label="给 Coco 发消息"]'),
    inspirationHead: (document.querySelector('.inspiration-panel h2') || {}).textContent || '',
    mapHead: (document.querySelector('.map-slot h2') || {}).textContent || '',
    cards,
    mapSlot,
    mapCopy: mapCopy ? mapCopy.textContent.trim() : '',
    amap,
    canvasCount,
    hasAMap: typeof window.AMap !== 'undefined',
    specs,
    coco,
    users,
    sending: !!(document.querySelector('.send-btn:disabled') && document.querySelector('.coco-dots')),
    waiting: !!document.querySelector('.coco-dots'),
    sendError: (document.querySelector('.field-hint') || {}).textContent || '',
    conversationId: localStorage.getItem('xtrip_conversation_id'),
    tripLink: !!document.querySelector('a.view-trip'),
    modal: !!document.querySelector('#new-plan-title'),
  };
})()
"""


async def wait_snap(cdp: Cdp, pred, timeout=90.0, interval=0.6):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = await cdp.eval(SNAP_JS)
        try:
            if pred(last):
                return last
        except Exception:
            pass
        await asyncio.sleep(interval)
    return last


async def click(cdp: Cdp, selector: str) -> bool:
    ok = await cdp.eval(
        f"""
        (() => {{
          const el = document.querySelector({json.dumps(selector)});
          if (!el) return false;
          el.scrollIntoView({{block:'center'}});
          el.click();
          return true;
        }})()
        """
    )
    return bool(ok)


async def click_text(cdp: Cdp, selector: str, text: str) -> bool:
    return bool(
        await cdp.eval(
            f"""
            (() => {{
              const nodes = [...document.querySelectorAll({json.dumps(selector)})];
              const el = nodes.find((n) => (n.textContent || '').includes({json.dumps(text)}));
              if (!el) return false;
              el.scrollIntoView({{block:'center'}});
              el.click();
              return true;
            }})()
            """
        )
    )


async def fill(cdp: Cdp, selector: str, value: str) -> bool:
    return bool(
        await cdp.eval(
            f"""
            (() => {{
              const el = document.querySelector({json.dumps(selector)});
              if (!el) return false;
              const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
              const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
              setter.call(el, {json.dumps(value)});
              el.dispatchEvent(new Event('input', {{bubbles:true}}));
              el.dispatchEvent(new Event('change', {{bubbles:true}}));
              return true;
            }})()
            """
        )
    )


async def send_chat(cdp: Cdp, text: str) -> None:
    await fill(cdp, 'textarea[aria-label="给 Coco 发消息"]', text)
    await asyncio.sleep(0.2)
    clicked = await click(cdp, 'button[aria-label="发送"]')
    if not clicked:
        raise RuntimeError("发送按钮未点到")


async def fetch_api003(cdp: Cdp, conv_id: str | None) -> dict:
    if not conv_id:
        return {"error": "no conversation id"}
    return await cdp.eval(
        f"""
        (async () => {{
          const res = await fetch('/api/conversations/' + {json.dumps(conv_id)});
          const body = await res.json();
          const data = body.data || {{}};
          const planning = data.planning || {{}};
          const intake = data.intake || {{}};
          const specs = (planning.specialists || []).map((s) => ({{role:s.role, status:s.status}}));
          const coco = (data.messages || []).filter((m) => m.role === 'assistant').map((m) => (m.content || '').slice(0, 240));
          return {{
            http: res.status,
            id: data.id,
            ready: intake.ready,
            missing: intake.missing_fields,
            origin: intake.origin_city,
            dest: intake.destination_city,
            region: intake.region,
            days: intake.duration_days,
            pace: intake.pace,
            followups: intake.followup_rounds_used,
            planning: planning.status,
            itinerary_id: planning.itinerary_id,
            specs,
            coco,
            msg_count: (data.messages || []).length,
          }};
        }})()
        """
    )


async def fetch_trips(cdp: Cdp) -> dict:
    return await cdp.eval(
        """
        (async () => {
          const res = await fetch('/api/itineraries');
          const body = await res.json();
          const items = body.data || body.items || [];
          const list = Array.isArray(items) ? items : (items.items || []);
          return { http: res.status, count: Array.isArray(list) ? list.length : -1 };
        })()
        """
    )


async def fresh_home(cdp: Cdp) -> dict:
    await cdp.eval(
        "localStorage.removeItem('xtrip_conversation_id'); location.href = '/';"
    )
    await asyncio.sleep(1.2)
    snap = await wait_snap(cdp, lambda s: s and s.get("composer") and not s.get("hasMock"), timeout=20)
    return snap


async def wait_coco(cdp: Cdp, timeout=75.0) -> dict:
    return await wait_snap(
        cdp,
        lambda s: s and (s.get("coco") or s.get("sendError")) and not s.get("waiting"),
        timeout=timeout,
    )


def mentions_outbound(texts: list[str]) -> bool:
    blob = " ".join(texts)
    return bool(re.search(r"出境|出国|国内还是出|国内还是境外", blob))


def mentions_pace(texts: list[str]) -> bool:
    blob = " ".join(texts)
    return bool(re.search(r"节奏|轻松|紧凑|不要太赶|适中", blob))


def mentions_origin(texts: list[str]) -> bool:
    blob = " ".join(texts)
    return bool(re.search(r"出发|从哪|哪个城市出发|出发地|出发城市", blob))


def looks_like_plan(texts: list[str]) -> bool:
    blob = " ".join(texts)
    return bool(re.search(r"第\s*[1-5一二三四五]\s*天|行程安排如下|按天", blob))


def recommended_city(texts: list[str], intake_dest: str | None) -> str | None:
    if intake_dest:
        return intake_dest
    blob = " ".join(texts)
    for city in ("青岛", "厦门", "三亚", "北海", "大连", "威海", "舟山", "舟山", "深圳", "珠海", "北戴河", "日照", "烟台", "海口", "汕头", "秦皇岛"):
        if city in blob:
            return city
    return None


async def run() -> dict:
    import urllib.request

    version = json.loads(urllib.request.urlopen("http://127.0.0.1:9610/json/version").read())
    ws_url = version["webSocketDebuggerUrl"]
    evidence: dict = {
        "chrome": version.get("Browser"),
        "cdp": "Target.createTarget + attachToTarget flatten",
        "frontend": BASE,
        "backend": API,
        "vite_use_mock": False,
        "acs": {},
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
        await asyncio.sleep(1.5)
        home = await wait_snap(cdp, lambda s: s and s.get("composer"), timeout=20)
        await cdp.screenshot("01-home.png")

        ac012 = {
            "leftNav": home.get("leftNav"),
            "composer": home.get("composer"),
            "inspirationHead": home.get("inspirationHead"),
            "mapSlot": home.get("mapSlot"),
            "hasMock": home.get("hasMock"),
            "cards": home.get("cards"),
            "path": home.get("path"),
        }
        ac012_pass = (
            home
            and not home.get("hasMock")
            and home.get("composer")
            and "对话" in (home.get("leftNav") or [])
            and not home.get("mapSlot")
            and len(home.get("cards") or []) >= 1
            and all(
                c.get("city") and c.get("title") and c.get("reason") and c.get("imgOk") and c.get("captionBelow") and not c.get("overlay")
                for c in home.get("cards") or []
            )
        )
        evidence["acs"]["AC-012"] = {"result": "PASS" if ac012_pass else "FAIL", **ac012}

        trips_before = await fetch_trips(cdp)
        await click(cdp, ".inspiration-card")
        await asyncio.sleep(0.8)
        after_click = await cdp.eval(SNAP_JS)
        trips_after = await fetch_trips(cdp)
        await cdp.screenshot("02-click-inspiration.png")
        ac020_pass = (
            after_click.get("path") == "/"
            and not after_click.get("tripLink")
            and trips_after.get("count") == trips_before.get("count")
            and not after_click.get("hasMock")
        )
        evidence["acs"]["AC-020"] = {
            "result": "PASS" if ac020_pass else "FAIL",
            "path": after_click.get("path"),
            "tripsBefore": trips_before,
            "tripsAfter": trips_after,
            "tripLink": after_click.get("tripLink"),
            "conversationId": after_click.get("conversationId"),
        }

        await send_chat(cdp, "想出去玩")
        snap002 = await wait_coco(cdp)
        await cdp.screenshot("03-ac002.png")
        api002 = await fetch_api003(cdp, snap002.get("conversationId"))
        specs002 = api002.get("specs") or []
        ac002_pass = (
            bool(snap002.get("coco"))
            and not snap002.get("hasMock")
            and api002.get("planning") in (None, "idle")
            and api002.get("itinerary_id") in (None, "")
            and specs002
            and all(s.get("status") == "not_started" for s in specs002)
            and (
                mentions_origin(snap002.get("coco") or [])
                or "出发" in " ".join(snap002.get("coco") or [])
                or api002.get("missing")
            )
        )
        evidence["acs"]["AC-002"] = {
            "result": "PASS" if ac002_pass else "FAIL",
            "coco": (snap002.get("coco") or [""])[-1][:240] if snap002.get("coco") else "",
            "api": api002,
            "mapHead": snap002.get("mapHead"),
            "hasMock": snap002.get("hasMock"),
        }

        ac013_switched = bool(snap002.get("mapSlot") and snap002.get("mapHead") and not snap002.get("cards"))
        tiles_ok = bool(snap002.get("amap") or snap002.get("canvasCount") or snap002.get("hasAMap"))
        tiles_failed = snap002.get("mapCopy") in ("🗺️ 地图暂时无法显示", "地图暂时无法显示")
        tiles_unconfigured = "未配置" in (snap002.get("mapCopy") or "")
        evidence["acs"]["AC-013"] = {
            "result": "PASS" if ac013_switched else "FAIL",
            "switched": ac013_switched,
            "mapCopy": snap002.get("mapCopy"),
            "amap": snap002.get("amap"),
            "canvasCount": snap002.get("canvasCount"),
            "hasAMap": snap002.get("hasAMap"),
            "tiles": "ok" if tiles_ok and not tiles_failed else ("unconfigured" if tiles_unconfigured else ("failed" if tiles_failed else "unverified")),
        }
        await cdp.screenshot("04-map.png")

        conv_before = snap002.get("conversationId")
        users_before = snap002.get("users")
        await cdp.eval("location.reload()")
        await asyncio.sleep(1.5)
        refreshed = await wait_snap(
            cdp,
            lambda s: s and s.get("conversationId") == conv_before and s.get("users"),
            timeout=20,
        )
        await cdp.screenshot("05-refresh.png")
        api_ref = await fetch_api003(cdp, conv_before)
        refresh_ok = (
            refreshed
            and refreshed.get("conversationId") == conv_before
            and users_before
            and any("想出去玩" in u for u in (refreshed.get("users") or []))
            and api_ref.get("http") == 200
        )
        evidence["refresh"] = {
            "result": "PASS" if refresh_ok else "FAIL",
            "id": conv_before,
            "users": refreshed.get("users") if refreshed else [],
            "api": api_ref,
        }

        # AC-001 new conversation
        await fresh_home(cdp)
        await send_chat(cdp, "从上海出发，带配偶去杭州 5 天，预算 2 万，不要太赶")
        snap001 = await wait_coco(cdp, timeout=80)
        await cdp.screenshot("06-ac001.png")
        api001 = await fetch_api003(cdp, snap001.get("conversationId"))
        dest_running = any(
            s.get("role") == "destination_research" and s.get("status") == "running" for s in (api001.get("specs") or [])
        )
        ac001_pass = (
            api001.get("http") == 200
            and api001.get("planning") == "running"
            and dest_running
            and not mentions_outbound(snap001.get("coco") or [])
            and api001.get("ready") is True
        )
        evidence["acs"]["AC-001"] = {
            "result": "PASS" if ac001_pass else "FAIL",
            "coco": (snap001.get("coco") or [""])[-1][:240] if snap001.get("coco") else "",
            "api": api001,
            "askedOutbound": mentions_outbound(snap001.get("coco") or []),
            "uiSpecs": snap001.get("specs"),
        }

        # AC-009
        await fresh_home(cdp)
        await send_chat(cdp, "从北京出发带小孩想看海 4 天预算 8 千别太赶")
        snap009 = await wait_coco(cdp, timeout=80)
        await cdp.screenshot("07-ac009.png")
        api009 = await fetch_api003(cdp, snap009.get("conversationId"))
        city = recommended_city(snap009.get("coco") or [], api009.get("dest"))
        dest_started = any(
            s.get("status") in ("running", "succeeded") for s in (api009.get("specs") or [])
        ) or api009.get("planning") == "running"
        asked_pick_city = bool(re.search(r"选一个|点选|先选.*城", " ".join(snap009.get("coco") or [])))
        ac009_pass = bool(city) and dest_started and not asked_pick_city
        evidence["acs"]["AC-009"] = {
            "result": "PASS" if ac009_pass else "FAIL",
            "city": city,
            "coco": (snap009.get("coco") or [""])[-1][:240] if snap009.get("coco") else "",
            "api": api009,
            "askedPickCity": asked_pick_city,
        }

        # AC-011 two follow-up rounds still missing origin or duration
        await fresh_home(cdp)
        await send_chat(cdp, "想和朋友去海边，预算一万，轻松一点")
        s1 = await wait_coco(cdp, timeout=80)
        await send_chat(cdp, "两个人，国内就行")
        s2 = await wait_coco(cdp, timeout=80)
        await send_chat(cdp, "你先看着办吧，出发地和玩几天我还没定")
        s3 = await wait_coco(cdp, timeout=80)
        await cdp.screenshot("08-ac011.png")
        api011 = await fetch_api003(cdp, s3.get("conversationId"))
        coco_all = (s1.get("coco") or []) + (s2.get("coco") or []) + (s3.get("coco") or [])
        last = (s3.get("coco") or [""])[-1]
        gap_explained = bool(re.search(r"缺|出发|几天|时长|天数", last))
        no_plan = not looks_like_plan([last]) and api011.get("itinerary_id") in (None, "")
        specs_idle = all(s.get("status") == "not_started" for s in (api011.get("specs") or [])) or api011.get("planning") == "idle"
        ac011_pass = gap_explained and no_plan and specs_idle and (api011.get("followups") or 0) >= 2
        evidence["acs"]["AC-011"] = {
            "result": "PASS" if ac011_pass else "FAIL",
            "rounds": [((x.get("coco") or [""])[-1][:180] if x.get("coco") else "") for x in (s1, s2, s3)],
            "last": last[:240],
            "api": api011,
            "gapExplained": gap_explained,
            "noPlan": no_plan,
        }

        # AC-014 new plan prefill
        await fresh_home(cdp)
        await click_text(cdp, ".nav-item", "新建计划")
        await asyncio.sleep(0.5)
        modal = await cdp.eval(SNAP_JS)
        await fill(cdp, "#plan-where", "杭州")
        await fill(cdp, "#plan-when", "5 天")
        await fill(cdp, "#plan-adults", "2")
        await fill(cdp, "#plan-children", "0")
        await fill(cdp, "#plan-budget", "20000")
        await click_text(cdp, ".pace-chip", "轻松")
        await cdp.screenshot("09-new-plan.png")
        await click_text(cdp, ".cta-btn", "开始聊")
        snap014 = await wait_coco(cdp, timeout=80)
        await cdp.screenshot("10-ac014.png")
        api014 = await fetch_api003(cdp, snap014.get("conversationId"))
        coco014 = snap014.get("coco") or []
        asked_pace = mentions_pace(coco014)
        asked_origin = mentions_origin(coco014)
        only_gap = asked_origin and not asked_pace
        # 若已齐则可能直接开工；AC 要求只追问仍缺的出发地
        missing = api014.get("missing") or []
        ac014_pass = (
            "杭州" == (api014.get("dest") or "")
            and api014.get("days") == 5
            and api014.get("pace") in ("relaxed", "轻松")
            and (only_gap or (api014.get("ready") and api014.get("planning") == "running"))
            and "pace" not in missing
        )
        evidence["acs"]["AC-014"] = {
            "result": "PASS" if ac014_pass else "FAIL",
            "modalOpened": modal.get("modal"),
            "coco": (coco014[-1][:240] if coco014 else ""),
            "askedPace": asked_pace,
            "askedOrigin": asked_origin,
            "api": api014,
        }

        evidence["network_api"] = [
            {"url": n["url"], "status": n["status"]}
            for n in cdp.network
            if "/api/" in n["url"]
        ][-40:]
        evidence["hasMockAny"] = any(
            (evidence["acs"].get(k) or {}).get("hasMock") for k in evidence["acs"]
        )

    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence


if __name__ == "__main__":
    out = asyncio.run(run())
    print(json.dumps({k: (v.get("result") if isinstance(v, dict) and "result" in v else v) for k, v in out.get("acs", {}).items()}, ensure_ascii=False))
    print("refresh", out.get("refresh", {}).get("result"))
    print("evidence", EVIDENCE)
