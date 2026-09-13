#!/usr/bin/env python3
"""T-013 Chrome 152 CDP：验收页面功能导航。不调业务 API / 付费模型 / 高德。"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from pathlib import Path

import websockets

BASE = "http://127.0.0.1:8765/project-console.html"
CDP_PORT = 9616
REPORT_DIR = Path(__file__).resolve().parent
SHOTS = REPORT_DIR / "t013-shots"
EVIDENCE = REPORT_DIR / "t013-evidence.json"
FIXTURE = REPORT_DIR / "t013-reload-fixture.json"
SHOTS.mkdir(parents=True, exist_ok=True)


class Conn:
    def __init__(self, ws: websockets.ClientConnection) -> None:
        self.ws = ws
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self.network: list[dict] = []

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
                if "project-map.json" in url:
                    self.network.append({"url": url.split("?", 1)[0], "status": status})

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
        path.write_bytes(base64.b64decode(data["data"]))
        return str(path)


async def wait_eval(conn: Conn, session_id: str, expression: str, pred, timeout: float = 12.0):
    started = time.monotonic()
    last = None
    while time.monotonic() - started < timeout:
        last = await conn.eval(session_id, expression)
        if pred(last):
            return last
        await asyncio.sleep(0.25)
    return last


async def click_sel(conn: Conn, session_id: str, selector: str) -> dict:
    box = await conn.eval(
        session_id,
        f"""
(() => {{
  const el = document.querySelector({selector!r});
  if (!el) return null;
  el.scrollIntoView({{block: 'center', inline: 'nearest'}});
  const r = el.getBoundingClientRect();
  return {{x: r.x + r.width/2, y: r.y + r.height/2, w: r.width, h: r.height, text: (el.innerText||'').slice(0,80)}};
}})()
""",
    )
    if not box:
        raise RuntimeError(f"missing {selector}")
    x, y = box["x"], box["y"]
    for typ, extra in (("mousePressed", {"clickCount": 1}), ("mouseReleased", {"clickCount": 1})):
        await conn.send(
            "Input.dispatchMouseEvent",
            {"type": typ, "x": x, "y": y, "button": "left", **extra},
            session_id=session_id,
        )
    return box


SNAP_JS = r"""
(() => {
  const wrap = document.querySelector('.wrap');
  const aside = document.querySelector('aside');
  const main = document.querySelector('main');
  const html = document.documentElement;
  const body = document.body;
  const navs = [...document.querySelectorAll('.nav-page')].map((el) => ({
    name: el.childNodes[0]?.textContent?.trim() || el.textContent.trim(),
    route: el.querySelector('small')?.textContent?.trim() || '',
    on: el.classList.contains('is-on'),
  }));
  const cards = [...document.querySelectorAll('article.card')].map((el) => ({
    id: el.id,
    title: el.querySelector('h3')?.textContent?.trim() || '',
    open: !el.querySelector('.details') || !el.querySelector('.details').classList.contains('hidden'),
  }));
  const banner = document.getElementById('banner');
  const content = document.getElementById('content');
  const text = document.body.innerText || '';
  return {
    title: document.title,
    href: location.href,
    viewport: {w: window.innerWidth, h: window.innerHeight},
    overflow: {
      htmlSW: html.scrollWidth, htmlCW: html.clientWidth,
      bodySW: body.scrollWidth, bodyCW: body.clientWidth,
      wrapSW: wrap ? wrap.scrollWidth : null,
      wrapCW: wrap ? wrap.clientWidth : null,
      asideH: aside ? aside.getBoundingClientRect().height : null,
      mainW: main ? main.getBoundingClientRect().width : null,
      xOverflow: html.scrollWidth > html.clientWidth + 1 || body.scrollWidth > body.clientWidth + 1,
    },
    wrapDisplay: wrap ? getComputedStyle(wrap).display : '',
    asidePosition: aside ? getComputedStyle(aside).position : '',
    navs,
    cards,
    banner: (banner?.innerText || '').slice(0, 400),
    bannerClass: banner?.className || '',
    hasSix: /项目概况|启动指南|验收看板|决策看板/.test(text),
    hasCocoAgent: /可自由选工具的 Agent/.test(text) && !/不标可自由选工具/.test(text),
    notesHasCocoPipeline: /固定 JSON 决策流水线/.test(text),
    hasPdfLive: /导出 PDF（未找到实现）/.test(text),
    hasSecretLike: /sk-[A-Za-z0-9]{8,}/.test(text) || /amap_web_key\s*[:=]\s*[A-Za-z0-9]{8,}/.test(text),
    contentLen: (content?.innerText || '').length,
    h2: document.querySelector('h2')?.innerText?.trim() || '',
    staleChips: [...document.querySelectorAll('.chip.stale')].map((el) => el.textContent.trim()),
    missChips: [...document.querySelectorAll('.chip.miss')].map((el) => el.textContent.trim()),
    copyButtons: document.querySelectorAll('[data-copy]').length,
    apiLinks: [...document.querySelectorAll('.api-link')].map((el) => el.textContent.trim()),
  };
})()
"""


async def open_page(conn: Conn, url: str, width: int, height: int) -> tuple[str, str]:
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
                        "left": 40,
                        "top": 40,
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
    return session_id, target_id


async def set_viewport(conn: Conn, session_id: str, width: int, height: int, mobile: bool = False) -> None:
    await conn.send(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": mobile},
        session_id=session_id,
    )


async def run() -> dict:
    import urllib.request

    version = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version").read())
    ws_url = version["webSocketDebuggerUrl"]
    evidence: dict = {
        "chrome": version.get("Browser"),
        "cdp": "Target.createTarget + attachToTarget flatten + newWindow",
        "url": BASE,
        "src_curl": False,
        "paid_calls": False,
        "read_real_env": False,
        "shots": {},
        "checks": {},
    }

    async with websockets.connect(ws_url, max_size=20_000_000) as ws:
        conn = Conn(ws)
        await conn.start()
        session_id, target_id = await open_page(conn, BASE, 1440, 900)
        evidence["targetId"] = target_id
        try:
            await conn.send(
                "Browser.grantPermissions",
                {
                    "origin": "http://127.0.0.1:8765",
                    "permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"],
                },
            )
        except Exception as exc:
            evidence["clipboard_grant"] = str(exc)

        boot = await wait_eval(
            conn,
            session_id,
            SNAP_JS,
            lambda v: isinstance(v, dict) and len(v.get("navs") or []) >= 3,
        )
        evidence["checks"]["desktop_boot"] = boot
        evidence["shots"]["desktop-boot"] = await conn.screenshot(session_id, "desktop-boot.png")

        # Navigate pages by real click
        page_snaps = {}
        for idx, route in enumerate(["/", "/trips", "/itineraries/:id"]):
            await click_sel(conn, session_id, f".nav-page:nth-of-type({idx + 1})")
            snap = await wait_eval(
                conn,
                session_id,
                SNAP_JS,
                lambda v, r=route: isinstance(v, dict) and any(n.get("on") and n.get("route") == r for n in (v.get("navs") or [])),
            )
            page_snaps[route] = {
                "h2": snap.get("h2") if isinstance(snap, dict) else None,
                "navs": snap.get("navs") if isinstance(snap, dict) else None,
                "cards": snap.get("cards") if isinstance(snap, dict) else None,
                "xOverflow": (snap or {}).get("overflow", {}).get("xOverflow") if isinstance(snap, dict) else None,
            }
            evidence["shots"][f"desktop-{idx}"] = await conn.screenshot(session_id, f"desktop-page-{idx}.png")
        evidence["checks"]["page_nav"] = page_snaps

        # Back to workbench, expand first feature
        await click_sel(conn, session_id, ".nav-page:nth-of-type(1)")
        await click_sel(conn, session_id, "article.card button.toggle")
        expanded = await wait_eval(
            conn,
            session_id,
            SNAP_JS,
            lambda v: isinstance(v, dict) and any(c.get("open") for c in (v.get("cards") or []) if c.get("id", "").startswith("feat-")),
        )
        evidence["checks"]["expand"] = {
            "open_feat": [c for c in (expanded or {}).get("cards", []) if c.get("open")],
            "apiLinks": (expanded or {}).get("apiLinks"),
        }
        evidence["shots"]["desktop-expand"] = await conn.screenshot(session_id, "desktop-expand.png")

        feat_detail = await conn.eval(
            session_id,
            """
(() => {
  const open = document.querySelector('article.card .details:not(.hidden)');
  if (!open) return null;
  const card = open.closest('article.card');
  return {
    id: card && card.id,
    hasTrigger: /触发：/.test(card.innerText),
    hasInput: /输入/.test(open.innerText),
    hasOutput: /输出/.test(open.innerText),
    flowItems: open.querySelectorAll('.flow li').length,
    branches: [...open.querySelectorAll('.flow .kv')].map((el) => el.textContent).filter((t) => t.includes('分支')),
    apiTexts: [...open.querySelectorAll('.api-link')].map((el) => el.textContent.trim()),
    hasAlgo: /算法/.test(open.innerText) || /接口/.test(open.innerText),
  };
})()
""",
        )
        evidence["checks"]["feat_detail"] = feat_detail

        # API jump
        before = await conn.eval(session_id, "document.querySelector('.api-link') && document.querySelector('.api-link').getAttribute('data-jump')")
        if before:
            await click_sel(conn, session_id, ".api-link")
            jumped = await conn.eval(
                session_id,
                f"""
(() => {{
  const id = {before!r};
  const node = document.getElementById(id);
  if (!node) return {{found:false}};
  const r = node.getBoundingClientRect();
  return {{found:true, id, visible: r.top < window.innerHeight && r.bottom > 0, top: r.top, text: (node.querySelector('h3')||{{}}).textContent}};
}})()
""",
            )
            evidence["checks"]["api_jump"] = jumped
        else:
            evidence["checks"]["api_jump"] = {"found": False}

        # Copy path success
        await conn.eval(
            session_id,
            """
(() => {
  window.__prompts = [];
  const orig = window.prompt;
  window.prompt = function(msg, def) { window.__prompts.push({msg, def}); return def; };
  window.__origPrompt = orig;
})()
""",
            await_promise=False,
        )
        copy_ok = {"clicked": False}
        try:
            await click_sel(conn, session_id, "button.copy")
            copied = await wait_eval(
                conn,
                session_id,
                "navigator.clipboard.readText()",
                lambda v: isinstance(v, str) and len(v) > 0,
                timeout=6,
            )
            copy_ok = {"clicked": True, "clipboard": copied, "prompts": await conn.eval(session_id, "window.__prompts")}
        except Exception as exc:
            copy_ok = {"clicked": True, "error": str(exc), "prompts": await conn.eval(session_id, "window.__prompts")}
        evidence["checks"]["copy_success"] = copy_ok

        # Copy failure fallback
        await conn.eval(
            session_id,
            """
(() => {
  window.__prompts = [];
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    get() { return { writeText() { return Promise.reject(new Error('denied')); } }; }
  });
})()
""",
            await_promise=False,
        )
        await click_sel(conn, session_id, "button.copy")
        fail_prompt = await wait_eval(
            conn,
            session_id,
            "window.__prompts",
            lambda v: isinstance(v, list) and len(v) > 0,
            timeout=6,
        )
        evidence["checks"]["copy_fail_prompt"] = fail_prompt

        # Reload JSON
        conn.network.clear()
        await click_sel(conn, session_id, "#btn-reload")
        reloaded = await wait_eval(
            conn,
            session_id,
            SNAP_JS,
            lambda v: isinstance(v, dict) and len(v.get("navs") or []) >= 3 and not (v.get("banner") or "").startswith("未能重新抓取"),
            timeout=8,
        )
        evidence["checks"]["reload"] = {
            "banner": (reloaded or {}).get("banner"),
            "navs": (reloaded or {}).get("navs"),
            "network": list(conn.network),
        }
        evidence["shots"]["reload"] = await conn.screenshot(session_id, "reload.png")

        # Isolation samples
        samples = {}
        for name, sel, pred_key in [
            ("source_changed", "[data-sample='source_changed']", "stale"),
            ("source_missing", "[data-sample='source_missing']", "missing"),
            ("parse_error", "[data-sample='parse_error']", "parse"),
            ("live", "[data-sample='live']", "live"),
        ]:
            await click_sel(conn, session_id, sel)
            snap = await wait_eval(conn, session_id, SNAP_JS, lambda v: isinstance(v, dict), timeout=6)
            extra = {}
            if name == "source_changed":
                extra["staleOnIntake"] = await conn.eval(
                    session_id,
                    """
(() => {
  const feat = document.getElementById('feat-feat-intake');
  return feat ? feat.innerText.includes('来源已变化待复核') : false;
})()
""",
                )
            if name == "source_missing":
                extra["pdfCard"] = await conn.eval(
                    session_id,
                    """
(() => {
  const feat = document.getElementById('feat-feat-pdf-missing');
  return feat ? feat.innerText.slice(0, 240) : '';
})()
""",
                )
            if name == "parse_error":
                extra["rawEscaped"] = await conn.eval(
                    session_id,
                    "document.querySelector('pre.raw') && document.querySelector('pre.raw').textContent",
                )
                extra["stillHasCheckedAlgo"] = await conn.eval(
                    session_id,
                    "!!document.querySelector('#content .card') || /源码已核对/.test(document.getElementById('content').innerText||'')",
                )
            samples[name] = {
                "banner": (snap or {}).get("banner"),
                "bannerClass": (snap or {}).get("bannerClass"),
                "staleChips": (snap or {}).get("staleChips"),
                "missChips": (snap or {}).get("missChips"),
                "hasPdfLive": (snap or {}).get("hasPdfLive"),
                "contentLen": (snap or {}).get("contentLen"),
                "navCount": len((snap or {}).get("navs") or []),
                **extra,
            }
            evidence["shots"][name] = await conn.screenshot(session_id, f"sample-{name}.png")
        evidence["checks"]["samples"] = samples

        # File picker with fixture
        live = json.loads((Path(__file__).resolve().parents[2] / "docs" / "project-map.json").read_text())
        live["project"]["notes"] = ["T013-FILE-PICKER-MARKER"] + list(live["project"].get("notes") or [])
        FIXTURE.write_text(json.dumps(live, ensure_ascii=False), encoding="utf-8")
        await conn.send("Page.setInterceptFileChooserDialog", {"enabled": True}, session_id=session_id)
        await click_sel(conn, session_id, "label.file-btn")
        await asyncio.sleep(0.3)
        try:
            await conn.send(
                "Page.handleFileChooser",
                {"action": "accept", "files": [str(FIXTURE)]},
                session_id=session_id,
            )
        except Exception as exc:
            evidence["checks"]["file_picker_error"] = str(exc)
        file_snap = await wait_eval(
            conn,
            session_id,
            "document.getElementById('page-notes') && document.getElementById('page-notes').innerText",
            lambda v: isinstance(v, str) and "T013-FILE-PICKER-MARKER" in v,
            timeout=8,
        )
        evidence["checks"]["file_picker"] = {
            "notes": (file_snap or "")[:200],
            "has_marker": isinstance(file_snap, str) and "T013-FILE-PICKER-MARKER" in file_snap,
        }
        evidence["shots"]["file-picker"] = await conn.screenshot(session_id, "file-picker.png")

        # Restore live via reload after file picker
        await click_sel(conn, session_id, "[data-sample='live']")

        # Narrow viewport
        await set_viewport(conn, session_id, 390, 844, mobile=True)
        await click_sel(conn, session_id, ".nav-page:nth-of-type(1)")
        narrow1 = await wait_eval(conn, session_id, SNAP_JS, lambda v: isinstance(v, dict) and (v.get("viewport") or {}).get("w") <= 400)
        evidence["checks"]["narrow_workbench"] = {
            "viewport": (narrow1 or {}).get("viewport"),
            "overflow": (narrow1 or {}).get("overflow"),
            "wrapDisplay": (narrow1 or {}).get("wrapDisplay"),
            "asidePosition": (narrow1 or {}).get("asidePosition"),
            "navs": (narrow1 or {}).get("navs"),
        }
        evidence["shots"]["narrow-workbench"] = await conn.screenshot(session_id, "narrow-workbench.png")

        await click_sel(conn, session_id, "article.card button.toggle")
        await click_sel(conn, session_id, ".nav-page:nth-of-type(3)")
        narrow3 = await wait_eval(
            conn,
            session_id,
            SNAP_JS,
            lambda v: isinstance(v, dict) and any(n.get("route") == "/itineraries/:id" and n.get("on") for n in (v.get("navs") or [])),
        )
        evidence["checks"]["narrow_detail"] = {
            "h2": (narrow3 or {}).get("h2"),
            "overflow": (narrow3 or {}).get("overflow"),
            "cards": (narrow3 or {}).get("cards"),
        }
        evidence["shots"]["narrow-detail"] = await conn.screenshot(session_id, "narrow-detail.png")

        await click_sel(conn, session_id, ".nav-page:nth-of-type(2)")
        narrow2 = await wait_eval(
            conn,
            session_id,
            SNAP_JS,
            lambda v: isinstance(v, dict) and any(n.get("route") == "/trips" and n.get("on") for n in (v.get("navs") or [])),
        )
        evidence["checks"]["narrow_trips"] = {
            "h2": (narrow2 or {}).get("h2"),
            "overflow": (narrow2 or {}).get("overflow"),
        }
        evidence["shots"]["narrow-trips"] = await conn.screenshot(session_id, "narrow-trips.png")

    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "evidence": str(EVIDENCE), "chrome": evidence.get("chrome")}, ensure_ascii=False))
    return evidence


if __name__ == "__main__":
    asyncio.run(run())
