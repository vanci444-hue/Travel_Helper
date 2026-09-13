#!/usr/bin/env python3
"""T-010 retry-1 browser CDP harness. No keys, no full itinerary, no Vite /src curl."""

from __future__ import annotations

import asyncio
import json
import time
import urllib.request
from pathlib import Path

import websockets

FRONT = "http://127.0.0.1:5199/"
CDP_PORT = 9612
SHOTS = Path(__file__).resolve().parent / "t010-r1-shots"
EVIDENCE = Path(__file__).resolve().parent / "t010-r1-evidence.json"
FAIL_TEXT = "上海出发带配偶去䶮䶮䶮阿巴市 5 天、预算 2 万、不要太赶"
OK_TEXT = "上海出发带配偶去杭州 5 天、预算 2 万、不要太赶"
POLL = 1.5
INTAKE_GRACE = 20.0
PLAN_TIMEOUT = 180.0


class CDP:
    def __init__(self, ws: websockets.ClientConnection) -> None:
        self.ws = ws
        self._id = 0
        self.session_id: str | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._events: asyncio.Queue = asyncio.Queue()
        self.api_hits: list[dict] = []

    async def reader(self) -> None:
        async for raw in self.ws:
            msg = json.loads(raw)
            if "id" in msg and msg["id"] in self._pending:
                self._pending.pop(msg["id"]).set_result(msg)
            else:
                method = msg.get("method")
                params = msg.get("params") or {}
                if method == "Network.requestWillBeSent":
                    url = (params.get("request") or {}).get("url") or ""
                    if "/api/" in url:
                        self.api_hits.append({"url": url.split("?")[0], "phase": "sent"})
                if method == "Network.responseReceived":
                    url = (params.get("response") or {}).get("url") or ""
                    status = (params.get("response") or {}).get("status")
                    if "/api/" in url:
                        self.api_hits.append(
                            {"url": url.split("?")[0], "status": status, "phase": "resp"}
                        )
                await self._events.put(msg)

    async def send(self, method: str, params: dict | None = None, session: bool = True) -> dict:
        self._id += 1
        msg: dict = {"id": self._id, "method": method, "params": params or {}}
        if session and self.session_id:
            msg["sessionId"] = self.session_id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[self._id] = fut
        await self.ws.send(json.dumps(msg))
        res = await asyncio.wait_for(fut, timeout=30)
        if "error" in res:
            raise RuntimeError(f"{method}: {res['error']}")
        return res.get("result") or {}

    async def eval(self, expression: str, await_promise: bool = False):
        res = await self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
            },
        )
        inner = res.get("result") or {}
        if inner.get("subtype") == "error":
            raise RuntimeError(inner.get("description") or "eval error")
        return inner.get("value")

    async def click_sel(self, selector: str, text_contains: str | None = None) -> dict:
        needle = json.dumps(text_contains, ensure_ascii=False)
        js = f"""
        (() => {{
          const nodes = [...document.querySelectorAll({selector!r})];
          const needle = {needle};
          const el = nodes.find((n) => {{
            const okText = needle ? (n.innerText || '').includes(needle) : true;
            return okText && n.getClientRects().length;
          }}) || nodes.find((n) => n.getClientRects().length);
          if (!el) return {{ok:false}};
          const r = el.getBoundingClientRect();
          return {{ok:true, x: r.x + r.width/2, y: r.y + r.height/2, text: (el.innerText||'').slice(0,80)}};
        }})()
        """
        box = await self.eval(js)
        if not box or not box.get("ok"):
            return {"ok": False, "selector": selector, "text_contains": text_contains}
        x, y = box["x"], box["y"]
        await self.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await self.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        return {"ok": True, "text": box.get("text"), "x": x, "y": y}

    async def shot(self, name: str) -> str:
        SHOTS.mkdir(parents=True, exist_ok=True)
        data = await self.send("Page.captureScreenshot", {"format": "png"})
        path = SHOTS / name
        path.write_bytes(__import__("base64").b64decode(data["data"]))
        return str(path)


def browser_ws() -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=5) as resp:
        body = json.loads(resp.read().decode())
    return body["webSocketDebuggerUrl"], body.get("Browser", "")


SNAP_JS = r"""
(async () => {
  const id = localStorage.getItem('xtrip_conversation_id');
  const hasMock = !!(document.querySelector('.mock-badge') || (document.body.innerText || '').includes('[Mock]'));
  const cocoNodes = [...document.querySelectorAll('.coco-text')].map((n) => (n.innerText || '').trim());
  const cocoLast = cocoNodes.at(-1) || '';
  const logHead = document.querySelector('.activity-log-head')?.innerText || '';
  const steps = [...document.querySelectorAll('.activity-step')].map((n) => ({
    text: (n.innerText || '').trim(),
    clickable: n.classList.contains('is-clickable'),
    disabled: n.disabled,
  }));
  const specs = [...document.querySelectorAll('.spec-row')].map((n) => (n.innerText || '').trim());
  const trip = document.querySelector('a.view-trip');
  const modal = document.querySelector('.log-detail-modal');
  let api = null;
  if (id) {
    const res = await fetch('/api/conversations/' + id);
    const body = await res.json();
    const d = body.data || {};
    api = {
      http: res.status,
      planning: d.planning?.status || null,
      itinerary_id: d.planning?.itinerary_id || null,
      error_message: d.planning?.error_message || null,
      dest: d.intake?.destination_city || null,
      origin: d.intake?.origin_city || null,
      days: d.intake?.duration_days || null,
      logCount: (d.planning?.activity_log || []).length,
      specs: (d.planning?.specialists || []).map((s) => ({
        role: s.role,
        status: s.status,
        summary: (s.summary || '').slice(0, 80),
      })),
      logTitles: (d.planning?.activity_log || []).map((e) => e.title).slice(0, 16),
    };
  }
  return {
    path: location.pathname,
    id,
    hasMock,
    welcome: !!document.querySelector('.welcome'),
    composer: !!document.querySelector('textarea[aria-label="给 Coco 发消息"]'),
    cocoLast: cocoLast.slice(0, 240),
    cocoHasDayCard: /第\s*\d+\s*天/.test(cocoLast) && /上午|下午|晚上/.test(cocoLast),
    failStripe: !!document.querySelector('.coco-text.is-fail'),
    tripLink: !!trip,
    tripHref: trip ? trip.getAttribute('href') : null,
    logHead,
    actionCount: steps.length,
    actions: steps.slice(0, 16),
    specs,
    modal: modal ? {
      heading: (document.querySelector('#log-detail-title')?.innerText || '').slice(0, 120),
      body: (document.querySelector('.log-detail-body')?.innerText || '').slice(0, 400),
    } : null,
    api,
  };
})()
"""


async def wait_selector(cdp: CDP, selector: str, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = await cdp.eval(f"!!document.querySelector({selector!r})")
        if found:
            return True
        await asyncio.sleep(0.3)
    return False


async def new_session(cdp: CDP) -> None:
    await cdp.send("Target.createTarget", {"url": FRONT}, session=False)
    created = None
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            ev = await asyncio.wait_for(cdp._events.get(), timeout=2)
        except TimeoutError:
            continue
        if ev.get("method") == "Target.targetCreated":
            info = (ev.get("params") or {}).get("targetInfo") or {}
            if info.get("type") == "page" and FRONT.rstrip("/") in (info.get("url") or FRONT):
                created = info.get("targetId")
                break
            if info.get("type") == "page" and (info.get("url") or "").startswith("http://127.0.0.1:5199"):
                created = info.get("targetId")
                break
            if info.get("type") == "page":
                created = info.get("targetId")
                break
    if not created:
        listing = await cdp.send("Target.getTargets", session=False)
        for t in listing.get("targetInfos") or []:
            if t.get("type") == "page" and "5199" in (t.get("url") or ""):
                created = t.get("targetId")
                break
        if not created:
            for t in listing.get("targetInfos") or []:
                if t.get("type") == "page":
                    created = t.get("targetId")
                    break
    if not created:
        raise RuntimeError("Target.createTarget did not yield a page")
    attached = await cdp.send(
        "Target.attachToTarget",
        {"targetId": created, "flatten": True},
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
    await wait_selector(cdp, 'textarea[aria-label="给 Coco 发消息"]', 20)
    await cdp.eval(
        "localStorage.removeItem('xtrip_conversation_id'); sessionStorage.clear();"
    )
    await cdp.send("Page.reload", {"ignoreCache": True})
    await wait_selector(cdp, 'textarea[aria-label="给 Coco 发消息"]', 20)
    # wait until stored id is gone / welcome
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        snap = await cdp.eval(SNAP_JS, True)
        if snap and not snap.get("id") and snap.get("composer"):
            break
        await asyncio.sleep(0.3)


async def send_chat(cdp: CDP, text: str) -> dict:
    focused = await cdp.click_sel('textarea[aria-label="给 Coco 发消息"]')
    await cdp.eval(
        f"""
        (() => {{
          const ta = document.querySelector('textarea[aria-label="给 Coco 发消息"]');
          const proto = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
          proto.set.call(ta, {text!r});
          ta.dispatchEvent(new Event('input', {{bubbles:true}}));
          return ta.value.length;
        }})()
        """
    )
    clicked = await cdp.click_sel('button[aria-label="发送"]')
    return {"focus": focused, "send": clicked}


def dest_rewritten(dest: str | None, coco: str) -> bool:
    blob = f"{dest or ''} {coco}"
    return "杭州" in blob


async def wait_planning(cdp: CDP, mode: str) -> dict:
    """mode=fail waits for failed after running; mode=ok waits for running|succeeded."""
    t0 = time.monotonic()
    timeline = []
    first_coco = None
    saw_running = False
    running_at = None
    last = None
    while True:
        elapsed = time.monotonic() - t0
        last = await cdp.eval(SNAP_JS, True)
        status = (last or {}).get("api", {}) or {}
        planning = status.get("planning")
        coco = (last or {}).get("cocoLast") or ""
        if coco and first_coco is None and planning is not None:
            first_coco = coco
        rec = {
            "t": round(elapsed, 1),
            "planning": planning,
            "dest": status.get("dest"),
            "logCount": status.get("logCount"),
            "id": last.get("id") if last else None,
        }
        if not timeline or timeline[-1].get("planning") != planning:
            timeline.append(rec)
        if planning == "running" and not saw_running:
            saw_running = True
            running_at = elapsed
        if mode == "fail":
            if planning == "failed":
                return {
                    "ok": True,
                    "elapsed": round(elapsed, 1),
                    "running_at": round(running_at, 1) if running_at is not None else None,
                    "from_running": round(elapsed - running_at, 1) if running_at is not None else None,
                    "snap": last,
                    "timeline": timeline,
                }
            if planning == "succeeded":
                return {
                    "ok": False,
                    "why": "succeeded_instead_of_failed",
                    "elapsed": round(elapsed, 1),
                    "snap": last,
                    "timeline": timeline,
                }
            if planning in (None, "idle") and first_coco and elapsed > INTAKE_GRACE and not saw_running:
                return {
                    "ok": False,
                    "why": "stayed_idle_after_intake",
                    "elapsed": round(elapsed, 1),
                    "snap": last,
                    "timeline": timeline,
                    "first_coco": first_coco[:240],
                }
            if elapsed > PLAN_TIMEOUT:
                return {
                    "ok": False,
                    "why": "timeout",
                    "elapsed": round(elapsed, 1),
                    "snap": last,
                    "timeline": timeline,
                }
        else:
            if planning in ("running", "succeeded"):
                return {
                    "ok": True,
                    "elapsed": round(elapsed, 1),
                    "snap": last,
                    "timeline": timeline,
                }
            if planning == "failed":
                return {
                    "ok": False,
                    "why": "failed_on_success_path",
                    "elapsed": round(elapsed, 1),
                    "snap": last,
                    "timeline": timeline,
                }
            if planning in (None, "idle") and first_coco and elapsed > INTAKE_GRACE and not saw_running:
                return {
                    "ok": False,
                    "why": "stayed_idle_after_intake",
                    "elapsed": round(elapsed, 1),
                    "snap": last,
                    "timeline": timeline,
                }
            if elapsed > 90:
                return {
                    "ok": False,
                    "why": "timeout_waiting_running",
                    "elapsed": round(elapsed, 1),
                    "snap": last,
                    "timeline": timeline,
                }
        await asyncio.sleep(POLL)


def leak_hits(text: str) -> list[str]:
    hits = []
    low = text.lower()
    for pat in ("sk-", "bearer ", "api_key", "apikey", "authorization=", "security_js"):
        if pat in low:
            hits.append(pat.strip())
    if "GET /" in text or "POST /" in text:
        hits.append("raw-http")
    return hits


async def click_fail_step(cdp: CDP) -> dict:
    opened = await cdp.eval("document.querySelector('.activity-log-head')?.getAttribute('aria-expanded')")
    if opened == "false":
        await cdp.click_sel(".activity-log-head")
        await asyncio.sleep(0.4)
    pick = await cdp.eval(
        """
        (() => {
          const steps = [...document.querySelectorAll('.activity-step.is-clickable')];
          const fail = steps.find((n) => /未完成|失败|找不到|无结果/.test(n.innerText || ''));
          const el = fail || steps.at(-1) || steps[0];
          if (!el) return {ok:false, count: steps.length};
          return {ok:true, title: (el.innerText||'').trim(), count: steps.length,
                  preferFail: !!fail};
        })()
        """
    )
    if not pick or not pick.get("ok"):
        return {"ok": False, "pick": pick}
    clicked = await cdp.click_sel(
        ".activity-step.is-clickable",
        "未完成" if pick.get("preferFail") else None,
    )
    if not clicked.get("ok"):
        clicked = await cdp.click_sel(".activity-step.is-clickable")
    deadline = time.monotonic() + 8
    modal = None
    while time.monotonic() < deadline:
        snap = await cdp.eval(SNAP_JS, True)
        modal = (snap or {}).get("modal")
        if modal and modal.get("heading"):
            break
        await asyncio.sleep(0.3)
    shot = await cdp.shot("04-fail-modal.png")
    body = (modal or {}).get("body") or ""
    heading = (modal or {}).get("heading") or ""
    closed = await cdp.click_sel(".log-detail-modal button", "关闭")
    await asyncio.sleep(0.4)
    after = await cdp.eval(SNAP_JS, True)
    return {
        "ok": bool(modal and heading and body),
        "pick": pick,
        "clicked": clicked,
        "heading": heading[:120],
        "body": body[:240],
        "bodyLen": len(body),
        "leaks": leak_hits(heading + "\n" + body),
        "closed": closed.get("ok"),
        "modalGone": not ((after or {}).get("modal")),
        "stillConversation": (after or {}).get("path") == "/",
        "conversationIdSame": (after or {}).get("id") == ((await cdp.eval("localStorage.getItem('xtrip_conversation_id')"))),
        "shot": shot,
        "afterPath": (after or {}).get("path"),
    }


async def run() -> dict:
    ws_url, browser = browser_ws()
    evidence = {
        "chrome": browser,
        "cdp": "Target.createTarget + attachToTarget flatten",
        "frontend": FRONT,
        "backend": "http://127.0.0.1:8099",
        "vite_use_mock": False,
        "acs": {},
        "tech": {},
    }
    async with websockets.connect(ws_url, max_size=20_000_000) as ws:
        cdp = CDP(ws)
        reader = asyncio.create_task(cdp.reader())
        try:
            await new_session(cdp)
            home = await cdp.eval(SNAP_JS, True)
            await cdp.shot("01-home.png")
            evidence["home"] = {
                "hasMock": bool(home.get("hasMock")),
                "composer": bool(home.get("composer")),
                "path": home.get("path"),
                "welcome": bool(home.get("welcome")),
            }

            # ---- AC-004 ----
            await send_chat(cdp, FAIL_TEXT)
            await cdp.shot("02-fail-sent.png")
            fail_wait = await wait_planning(cdp, "fail")
            snap = fail_wait.get("snap") or {}
            api = snap.get("api") or {}
            coco = snap.get("cocoLast") or ""
            err = api.get("error_message") or ""
            dest = api.get("dest")
            rewritten = dest_rewritten(dest, coco)
            reason_in_coco = bool(err) and (err[:12] in coco or "没法帮你出方案" in coco or "找不到" in coco or "原因" in coco)
            aligned = bool(err) and (err in coco or any(part in coco for part in err.split("，")[:1] if part))
            await cdp.shot("03-fail-done.png")
            modal = {"ok": False}
            if fail_wait.get("ok") and (snap.get("actionCount") or 0) > 0:
                modal = await click_fail_step(cdp)
            ac004 = {
                "result": None,
                "wait_seconds": fail_wait.get("elapsed"),
                "running_at": fail_wait.get("running_at"),
                "from_running": fail_wait.get("from_running"),
                "why": fail_wait.get("why"),
                "hasMock": snap.get("hasMock"),
                "cocoLast": coco,
                "error_message": err[:200] if err else "",
                "reasonInCoco": reason_in_coco,
                "errorAligned": aligned,
                "itinerary_id": api.get("itinerary_id"),
                "tripLink": snap.get("tripLink"),
                "failStripe": snap.get("failStripe"),
                "dest": dest,
                "rewrittenToHangzhou": rewritten,
                "specs": api.get("specs"),
                "logCount": api.get("logCount"),
                "logTitles": api.get("logTitles"),
                "failStep": modal,
                "http": api.get("http"),
                "planning": api.get("planning"),
                "timeline": fail_wait.get("timeline"),
                "conversation_id": snap.get("id"),
            }
            pass004 = (
                fail_wait.get("ok")
                and api.get("planning") == "failed"
                and not api.get("itinerary_id")
                and not snap.get("tripLink")
                and not rewritten
                and reason_in_coco
                and aligned
                and modal.get("ok")
                and not modal.get("leaks")
                and modal.get("closed")
                and modal.get("stillConversation")
                and not snap.get("hasMock")
            )
            ac004["result"] = "PASS" if pass004 else "FAIL"
            evidence["acs"]["AC-004"] = ac004

            # ---- AC-003 regression ----
            await new_session(cdp)
            await send_chat(cdp, OK_TEXT)
            ok_wait = await wait_planning(cdp, "ok")
            ok_snap = ok_wait.get("snap") or {}
            ok_api = ok_snap.get("api") or {}
            await cdp.shot("05-ok-running.png")
            ac003 = {
                "result": None,
                "scope": "regression: wait running|succeeded, dest=杭州; not full 60s scheme",
                "wait_seconds": ok_wait.get("elapsed"),
                "why": ok_wait.get("why"),
                "hasMock": ok_snap.get("hasMock"),
                "planning": ok_api.get("planning"),
                "dest": ok_api.get("dest"),
                "origin": ok_api.get("origin"),
                "itinerary_id": ok_api.get("itinerary_id"),
                "specs": ok_api.get("specs") or ok_snap.get("specs"),
                "logCount": ok_api.get("logCount"),
                "conversation_id": ok_snap.get("id"),
                "timeline": ok_wait.get("timeline"),
            }
            pass003 = (
                ok_wait.get("ok")
                and ok_api.get("planning") in ("running", "succeeded")
                and ok_api.get("dest") == "杭州"
                and not ok_snap.get("hasMock")
            )
            ac003["result"] = "PASS" if pass003 else "FAIL"
            evidence["acs"]["AC-003"] = ac003

            evidence["acs"]["AC-024"] = {
                "result": "PASS" if (modal.get("ok") and not modal.get("leaks") and modal.get("closed")) else "FAIL",
                "scope": "this-round fail-step modal only; success-path click reused prior PASS + frontend unchanged",
                "clicked": modal.get("clicked"),
                "heading": modal.get("heading"),
                "body": modal.get("body"),
                "bodyLen": modal.get("bodyLen"),
                "leaks": modal.get("leaks"),
                "closed": modal.get("closed"),
                "stillConversation": modal.get("stillConversation"),
            }

            api_only = [h for h in cdp.api_hits if "/src/" not in (h.get("url") or "")]
            src_hits = [h for h in cdp.api_hits if "/src/" in (h.get("url") or "")]
            evidence["tech"] = {
                "page_api_hits": api_only[-20:],
                "src_module_hits_seen_by_cdp_not_curl": len(src_hits),
                "checked": "DOM + page fetch /api only; no Tester curl of Vite /src",
            }
        finally:
            reader.cancel()
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "AC-004": evidence["acs"].get("AC-004", {}).get("result"),
        "AC-003": evidence["acs"].get("AC-003", {}).get("result"),
        "AC-024": evidence["acs"].get("AC-024", {}).get("result"),
        "evidence": str(EVIDENCE),
    }, ensure_ascii=False))
    return evidence


if __name__ == "__main__":
    asyncio.run(run())
