#!/usr/bin/env python3
"""One directed recheck: open fail-step modal on existing AC-004 conversation."""

from __future__ import annotations

import asyncio
import json
import time
import urllib.request
from pathlib import Path

import websockets

FRONT = "http://127.0.0.1:5199/"
CDP_PORT = 9612
FAIL_ID = "conv_5903a8247d5a2da1"
SHOTS = Path(__file__).resolve().parent / "t010-r1-shots"
OUT = Path(__file__).resolve().parent / "t010-r1-modal.json"


class CDP:
    def __init__(self, ws) -> None:
        self.ws = ws
        self._id = 0
        self.session_id = None
        self._pending: dict[int, asyncio.Future] = {}
        self._events: asyncio.Queue = asyncio.Queue()

    async def reader(self) -> None:
        async for raw in self.ws:
            msg = json.loads(raw)
            if "id" in msg and msg["id"] in self._pending:
                self._pending.pop(msg["id"]).set_result(msg)
            else:
                await self._events.put(msg)

    async def send(self, method: str, params: dict | None = None, session: bool = True) -> dict:
        self._id += 1
        payload: dict = {"id": self._id, "method": method, "params": params or {}}
        if session and self.session_id:
            payload["sessionId"] = self.session_id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[self._id] = fut
        await self.ws.send(json.dumps(payload))
        res = await asyncio.wait_for(fut, timeout=20)
        if "error" in res:
            raise RuntimeError(f"{method}: {res['error']}")
        return res.get("result") or {}

    async def eval(self, expression: str, await_promise: bool = False):
        res = await self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": await_promise},
        )
        inner = res.get("result") or {}
        if inner.get("subtype") == "error":
            raise RuntimeError(inner.get("description") or "eval error")
        return inner.get("value")

    async def click_xy(self, x: float, y: float) -> None:
        await self.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await self.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})

    async def shot(self, name: str) -> str:
        SHOTS.mkdir(parents=True, exist_ok=True)
        data = await self.send("Page.captureScreenshot", {"format": "png"})
        path = SHOTS / name
        path.write_bytes(__import__("base64").b64decode(data["data"]))
        return str(path)


async def attach_new(cdp: CDP) -> None:
    created = await cdp.send("Target.createTarget", {"url": "about:blank"}, session=False)
    target_id = created["targetId"]
    attached = await cdp.send("Target.attachToTarget", {"targetId": target_id, "flatten": True}, session=False)
    cdp.session_id = attached["sessionId"]
    await cdp.send("Page.enable")
    await cdp.send("Runtime.enable")
    await cdp.send("Network.enable")
    await cdp.send(
        "Emulation.setDeviceMetricsOverride",
        {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
    )
    await cdp.send("Page.navigate", {"url": FRONT})
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        ready = await cdp.eval("!!document.querySelector('textarea[aria-label=\"给 Coco 发消息\"]')")
        if ready:
            break
        await asyncio.sleep(0.3)
    await cdp.eval(f"localStorage.setItem('xtrip_conversation_id', {FAIL_ID!r})")
    await cdp.send("Page.reload", {"ignoreCache": True})
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        snap = await cdp.eval(
            """
            (() => ({
              id: localStorage.getItem('xtrip_conversation_id'),
              failStep: !! [...document.querySelectorAll('.activity-step')].find(n => (n.innerText||'').includes('没有完成')),
              planning: document.querySelector('.coco-text.is-fail') ? 'failed-ui' : 'other',
              stepCount: document.querySelectorAll('.activity-step').length,
            }))()
            """
        )
        if snap and snap.get("id") == FAIL_ID and snap.get("failStep"):
            return
        await asyncio.sleep(0.4)
    raise RuntimeError("fail conversation UI not ready")


async def main() -> None:
    with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=5) as resp:
        ws_url = json.loads(resp.read().decode())["webSocketDebuggerUrl"]
    async with websockets.connect(ws_url, max_size=20_000_000) as ws:
        cdp = CDP(ws)
        reader = asyncio.create_task(cdp.reader())
        try:
            await attach_new(cdp)
            api = await cdp.eval(
                f"""
                (async () => {{
                  const res = await fetch('/api/conversations/{FAIL_ID}');
                  const body = await res.json();
                  const logs = body.data?.planning?.activity_log || [];
                  const failish = logs.filter((e) => /未完成|失败|没有完成|找不到/.test(e.title || '') || e.title === '这一步没有完成');
                  return {{
                    http: res.status,
                    planning: body.data?.planning?.status,
                    dest: body.data?.intake?.destination_city,
                    error_message: (body.data?.planning?.error_message || '').slice(0, 200),
                    itinerary_id: body.data?.planning?.itinerary_id,
                    failLogs: failish.map((e) => ({{
                      id: e.id,
                      title: e.title,
                      clickable: e.clickable,
                      heading: (e.detail && e.detail.heading || '').slice(0, 80),
                      body: (e.detail && e.detail.body || '').slice(0, 160),
                    }})),
                  }};
                }})()
                """,
                True,
            )
            box = await cdp.eval(
                """
                (() => {
                  const steps = [...document.querySelectorAll('.activity-step')];
                  const el = steps.find((n) => (n.innerText || '').includes('没有完成'))
                    || steps.find((n) => n.classList.contains('is-clickable') && /失败|未完成/.test(n.innerText || ''));
                  if (!el) return {ok:false, titles: steps.map(n => n.innerText).slice(-6)};
                  el.scrollIntoView({block:'center'});
                  const r = el.getBoundingClientRect();
                  return {
                    ok: true,
                    text: (el.innerText || '').trim().slice(0, 80),
                    clickable: el.classList.contains('is-clickable'),
                    disabled: el.disabled,
                    x: r.x + r.width/2,
                    y: r.y + r.height/2,
                    top: r.top,
                    bottom: r.bottom,
                  };
                })()
                """
            )
            await cdp.shot("06-fail-step-inview.png")
            if not box or not box.get("ok"):
                OUT.write_text(json.dumps({"api": api, "box": box, "ok": False}, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps({"ok": False, "box": box}, ensure_ascii=False))
                return
            await cdp.click_xy(box["x"], box["y"])
            deadline = time.monotonic() + 8
            modal = None
            while time.monotonic() < deadline:
                modal = await cdp.eval(
                    """
                    (() => {
                      const modal = document.querySelector('.log-detail-modal');
                      if (!modal) return null;
                      return {
                        heading: (document.querySelector('#log-detail-title')?.innerText || '').slice(0, 160),
                        body: (document.querySelector('.log-detail-body')?.innerText || '').slice(0, 400),
                      };
                    })()
                    """
                )
                if modal and modal.get("heading"):
                    break
                await asyncio.sleep(0.3)
            shot = await cdp.shot("07-fail-modal.png")
            closed = False
            if modal:
                close_box = await cdp.eval(
                    """
                    (() => {
                      const btn = [...document.querySelectorAll('.log-detail-modal button')].find((n) => (n.innerText||'').includes('关闭'));
                      if (!btn) return {ok:false};
                      const r = btn.getBoundingClientRect();
                      return {ok:true, x: r.x+r.width/2, y: r.y+r.height/2};
                    })()
                    """
                )
                if close_box and close_box.get("ok"):
                    await cdp.click_xy(close_box["x"], close_box["y"])
                    await asyncio.sleep(0.4)
                    closed = not await cdp.eval("!!document.querySelector('.log-detail-modal')")
            after = await cdp.eval(
                """
                (() => ({
                  path: location.pathname,
                  id: localStorage.getItem('xtrip_conversation_id'),
                  modal: !!document.querySelector('.log-detail-modal'),
                  composer: !!document.querySelector('textarea[aria-label="给 Coco 发消息"]'),
                }))()
                """
            )
            await cdp.shot("08-fail-modal-closed.png")
            heading = (modal or {}).get("heading") or ""
            body = (modal or {}).get("body") or ""
            blob = (heading + "\n" + body).lower()
            leaks = [p for p in ("sk-", "bearer ", "api_key", "apikey", "authorization=", "security_js") if p in blob]
            result = {
                "ok": bool(heading and body and not leaks and closed and (after or {}).get("path") == "/"),
                "box": box,
                "heading": heading,
                "body": body,
                "bodyLen": len(body),
                "leaks": leaks,
                "closed": closed,
                "after": after,
                "api": api,
                "shot": shot,
            }
            OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({
                "ok": result["ok"],
                "heading": heading,
                "bodyLen": len(body),
                "leaks": leaks,
                "closed": closed,
                "clickable": box.get("clickable"),
                "failLogCount": len((api or {}).get("failLogs") or []),
            }, ensure_ascii=False))
        finally:
            reader.cancel()


if __name__ == "__main__":
    asyncio.run(main())
