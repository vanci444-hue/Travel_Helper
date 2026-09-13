#!/usr/bin/env python3
"""T-013 一次定向复核：窄屏溢出元素、重新加载 fetch、文件选择处理。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import websockets

CDP_PORT = 9616
REPORT_DIR = Path(__file__).resolve().parent
OUT = REPORT_DIR / "t013-recheck.json"
FIXTURE = REPORT_DIR / "t013-reload-fixture.json"
MAP = REPORT_DIR.parents[1] / "docs" / "project-map.json"


class Conn:
    def __init__(self, ws: websockets.ClientConnection) -> None:
        self.ws = ws
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}

    async def start(self) -> None:
        asyncio.create_task(self._reader())

    async def _reader(self) -> None:
        async for raw in self.ws:
            msg = json.loads(raw)
            if "id" in msg and msg["id"] in self._pending:
                self._pending[msg["id"]].set_result(msg)

    async def send(self, method: str, params: dict | None = None, session_id: str | None = None) -> dict:
        self._id += 1
        payload: dict = {"id": self._id, "method": method, "params": params or {}}
        if session_id:
            payload["sessionId"] = session_id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[self._id] = fut
        await self.ws.send(json.dumps(payload))
        msg = await asyncio.wait_for(fut, timeout=20)
        if "error" in msg:
            raise RuntimeError(f"{method}: {msg['error']}")
        return msg.get("result") or {}

    async def eval(self, session_id: str, expression: str, await_promise: bool = True) -> object:
        result = await self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": await_promise},
            session_id=session_id,
        )
        if result.get("exceptionDetails"):
            raise RuntimeError(result["exceptionDetails"])
        return (result.get("result") or {}).get("value")


async def main() -> None:
    import urllib.request

    version = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version").read())
    targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list").read())
    page = next((t for t in targets if "project-console" in (t.get("url") or "")), None)
    if not page:
        raise RuntimeError(f"no console target: {targets}")

    async with websockets.connect(version["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
        conn = Conn(ws)
        await conn.start()
        attached = await conn.send("Target.attachToTarget", {"targetId": page["id"], "flatten": True})
        sid = attached["sessionId"]
        await conn.send("Runtime.enable", session_id=sid)
        await conn.send("Page.enable", session_id=sid)

        await conn.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True},
            session_id=sid,
        )
        await conn.eval(sid, "document.querySelector('[data-sample=\"live\"]').click()", await_promise=False)
        await asyncio.sleep(0.4)

        overflow = await conn.eval(
            sid,
            """
(() => {
  const html = document.documentElement;
  const body = document.body;
  const vw = html.clientWidth;
  const offenders = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width > vw + 1) {
      offenders.push({
        tag: el.tagName,
        cls: (el.className || '').toString().slice(0,80),
        id: el.id,
        w: Math.round(r.width),
        left: Math.round(r.left),
        text: (el.innerText || '').replace(/\\s+/g,' ').slice(0,80),
      });
    }
  }
  offenders.sort((a,b) => b.w - a.w);
  return {
    inner: {w: window.innerWidth, h: window.innerHeight},
    html: {cw: html.clientWidth, sw: html.scrollWidth},
    body: {cw: body.clientWidth, sw: body.scrollWidth},
    wrapDisplay: getComputedStyle(document.querySelector('.wrap')).display,
    offenders: offenders.slice(0, 12),
  };
})()
""",
        )

        # Reload fetch hook
        await conn.eval(
            sid,
            """
(() => {
  window.__reloads = [];
  const orig = window.fetch;
  window.fetch = function() {
    const args = arguments;
    return orig.apply(this, args).then((res) => {
      window.__reloads.push({url: String(args[0]), status: res.status, ok: res.ok});
      return res;
    }).catch((err) => {
      window.__reloads.push({url: String(args[0]), error: String(err)});
      throw err;
    });
  };
})()
""",
            await_promise=False,
        )
        await conn.eval(sid, "document.getElementById('btn-reload').click()", await_promise=False)
        await asyncio.sleep(0.8)
        reload_info = await conn.eval(
            sid,
            """
({
  fetches: window.__reloads,
  banner: document.getElementById('banner').innerText,
  navCount: document.querySelectorAll('.nav-page').length,
  h2: document.querySelector('h2') && document.querySelector('h2').innerText
})
""",
        )

        # File picker via File + change on the input (CDP handleFileChooser 不存在)
        live = json.loads(MAP.read_text())
        live["project"]["notes"] = ["T013-FILE-PICKER-MARKER"] + list(live["project"].get("notes") or [])
        FIXTURE.write_text(json.dumps(live, ensure_ascii=False), encoding="utf-8")
        payload = json.dumps(live, ensure_ascii=False)
        file_info = await conn.eval(
            sid,
            f"""
(async () => {{
  const input = document.getElementById('file-map');
  const file = new File([{payload!r}], 't013-reload-fixture.json', {{type: 'application/json'}});
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;
  input.dispatchEvent(new Event('change', {{bubbles: true}}));
  await new Promise((r) => setTimeout(r, 200));
  return {{
    notes: document.getElementById('page-notes').innerText.slice(0, 200),
    hasMarker: document.getElementById('page-notes').innerText.includes('T013-FILE-PICKER-MARKER'),
    banner: document.getElementById('banner').innerText,
    navCount: document.querySelectorAll('.nav-page').length
  }};
}})()
""",
        )

        # restore live
        await conn.eval(sid, "document.querySelector('[data-sample=\"live\"]').click()", await_promise=False)

        OUT.write_text(
            json.dumps(
                {"overflow": overflow, "reload": reload_info, "file_picker": file_info},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(json.dumps({"ok": True, "out": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
