#!/usr/bin/env python3
"""T-010 Chrome 152 CDP 验收。只看 DOM 与 /api，不请求 /src/*.ts。"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

import websockets

BASE = "http://127.0.0.1:5199"
API = "http://127.0.0.1:8099"
REPORT_DIR = Path(__file__).resolve().parent
SHOTS = REPORT_DIR / "t010-shots"
EVIDENCE = REPORT_DIR / "t010-evidence.json"
SHOTS.mkdir(parents=True, exist_ok=True)

KEY_RE = re.compile(r"sk-[A-Za-z0-9_-]{8,}|Bearer\s+\S+|api[_-]?key[=:]\s*\S+", re.I)
HTTP_RE = re.compile(r"https?://|(\b(GET|POST|PUT|PATCH|DELETE)\s+/\S+)|restapi\.amap|dashscope|api\.deepseek", re.I)
DAY_CARD_RE = re.compile(r"(第\s*[1-5一二三四五]\s*天.{0,40}(上午|下午|晚上|景点|入住|午餐|晚餐))|(按天(行程|安排|卡片))")
SENSITIVE_KEYS = ("deepseek_api_key", "qwen_api_key", "amap_web_key", "VITE_AMAP_JS_KEY")


class Cdp:
    def __init__(self, ws: websockets.ClientConnection) -> None:
        self.ws = ws
        self._id = 0
        self.session_id: str | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self.network: list[dict] = []
        self.poll_hits: list[float] = []

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
                        rec = {
                            "url": url.split("?", 1)[0],
                            "status": (params.get("response") or {}).get("status"),
                            "type": params.get("type"),
                        }
                        self.network.append(rec)
                        if re.search(r"/api/conversations/[^/]+$", rec["url"]) and rec["status"] == 200:
                            self.poll_hits.append(time.monotonic())
                if method == "Network.requestWillBeSent":
                    url = (params.get("request") or {}).get("url", "")
                    if "/src/" in url and url.endswith((".ts", ".tsx")):
                        self.network.append({"url": url, "status": "SRC_HIT", "type": "forbidden"})

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
  const coco = [...document.querySelectorAll('.coco-text')].map((n) => n.textContent.trim());
  const users = [...document.querySelectorAll('.user-bubble')].map((n) => n.textContent.trim());
  const specs = [...document.querySelectorAll('.spec-row')].map((n) => n.textContent.trim());
  const steps = [...document.querySelectorAll('.activity-step')].map((n) => ({
    title: n.textContent.trim(),
    clickable: n.classList.contains('is-clickable'),
    disabled: n.disabled,
  }));
  const modal = document.querySelector('.log-detail-modal');
  const heading = document.querySelector('#log-detail-title');
  const body = document.querySelector('.log-detail-body');
  const trip = document.querySelector('a.view-trip');
  return {
    href: location.href,
    path: location.pathname,
    title: document.title,
    hasMock: text.includes('[Mock]'),
    mockCount: (text.match(/\[Mock\]/g) || []).length,
    composer: !!document.querySelector('textarea[aria-label="给 Coco 发消息"]'),
    welcome: !!document.querySelector('.welcome'),
    specs,
    steps,
    stepCount: steps.length,
    clickableCount: steps.filter((s) => s.clickable).length,
    logHead: (document.querySelector('.activity-log-head') || {}).textContent || '',
    logOpen: !!document.querySelector('.activity-log-body'),
    coco,
    cocoLast: coco.length ? coco[coco.length - 1] : '',
    cocoName: [...document.querySelectorAll('.coco-name')].map((n) => n.textContent.trim()),
    users,
    tripLink: !!(trip && (trip.textContent || '').includes('查看行程')),
    tripHref: trip ? trip.getAttribute('href') : '',
    modal: !!modal,
    modalHeading: heading ? heading.textContent.trim() : '',
    modalBody: body ? body.textContent.trim() : '',
    waiting: !!document.querySelector('.coco-dots'),
    sendError: (document.querySelector('.field-hint') || {}).textContent || '',
    conversationId: localStorage.getItem('xtrip_conversation_id'),
    failStripe: !!document.querySelector('.coco-text.is-fail'),
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
    return bool(
        await cdp.eval(
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
    )


async def click_step(cdp: Cdp, pattern: str) -> dict:
    return await cdp.eval(
        f"""
        (() => {{
          const nodes = [...document.querySelectorAll('.activity-step.is-clickable')];
          const re = new RegExp({json.dumps(pattern)});
          const preferred = nodes.find((n) => re.test(n.textContent || ''));
          const el = preferred || nodes[0];
          if (!el) return {{ok:false, title:''}};
          el.scrollIntoView({{block:'center'}});
          el.click();
          return {{ok:true, title:(el.textContent || '').trim()}};
        }})()
        """
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
          const specs = (planning.specialists || []).map((s) => ({{
            role: s.role,
            status: s.status,
            summary: (s.summary || '').slice(0, 80),
          }}));
          const logs = (planning.activity_log || []).map((e) => ({{
            id: e.id,
            kind: e.kind,
            title: (e.title || '').slice(0, 80),
            clickable: !!e.clickable,
            heading: ((e.detail && e.detail.heading) || '').slice(0, 80),
            bodyLen: ((e.detail && e.detail.body) || '').length,
          }}));
          const coco = (data.messages || [])
            .filter((m) => m.role === 'assistant')
            .map((m) => (m.content || '').slice(0, 280));
          return {{
            http: res.status,
            id: data.id,
            ready: intake.ready,
            dest: intake.destination_city,
            origin: intake.origin_city,
            days: intake.duration_days,
            planning: planning.status,
            itinerary_id: planning.itinerary_id,
            error_message: planning.error_message,
            specs,
            logs,
            logCount: logs.length,
            coco,
            msg_count: (data.messages || []).length,
          }};
        }})()
        """
    )


async def fresh_home(cdp: Cdp) -> dict:
    await cdp.eval("localStorage.removeItem('xtrip_conversation_id'); location.href = '/';")
    return await wait_snap(cdp, lambda s: s and s.get("composer") and s.get("welcome"), timeout=20)


def looks_like_day_cards(texts: list[str]) -> bool:
    blob = "\n".join(texts)
    return bool(DAY_CARD_RE.search(blob))


def leak_in(text: str) -> list[str]:
    hits = []
    if KEY_RE.search(text or ""):
        hits.append("key_pattern")
    if HTTP_RE.search(text or ""):
        hits.append("raw_http")
    for name in SENSITIVE_KEYS:
        if name.lower() in (text or "").lower() and re.search(rf"{name}\s*[=:]", text or "", re.I):
            hits.append(name)
    return hits


def clip(text: str, n: int = 220) -> str:
    text = (text or "").replace("\n", " ")
    return text[:n]


def three_specialists(specs: list[str] | None) -> bool:
    blob = " ".join(specs or [])
    return all(name in blob for name in ("目的地研究", "预算专家", "行程设计"))


def chinese_actions(steps: list[dict] | None) -> list[str]:
    titles = []
    for step in steps or []:
        title = re.sub(r"^[🔧💭👤]\s*", "", step.get("title") or "")
        if re.search(r"[\u4e00-\u9fff]", title):
            titles.append(title)
    return titles


async def wait_planning(cdp: Cdp, timeout: float = 180.0) -> tuple[dict, dict, float]:
    started = time.monotonic()
    last_snap = None
    last_api = {}
    mid = None
    while time.monotonic() - started < timeout:
        last_snap = await cdp.eval(SNAP_JS)
        cid = (last_snap or {}).get("conversationId")
        if cid:
            last_api = await fetch_api003(cdp, cid)
        if mid is None and last_snap and (
            three_specialists(last_snap.get("specs")) or (last_snap.get("stepCount") or 0) >= 2
        ):
            mid = {
                "elapsed": round(time.monotonic() - started, 1),
                "specs": last_snap.get("specs"),
                "steps": [s.get("title") for s in (last_snap.get("steps") or [])][:12],
                "logHead": last_snap.get("logHead"),
                "planning": last_api.get("planning"),
            }
        status = (last_api or {}).get("planning")
        if status in ("succeeded", "failed") and not (last_snap or {}).get("waiting"):
            return last_snap or {}, last_api, time.monotonic() - started
        if (last_snap or {}).get("sendError"):
            return last_snap or {}, last_api, time.monotonic() - started
        await asyncio.sleep(1.0)
    return last_snap or {}, last_api, time.monotonic() - started


async def run() -> dict:
    import urllib.request

    version = json.loads(urllib.request.urlopen("http://127.0.0.1:9611/json/version").read())
    ws_url = version["webSocketDebuggerUrl"]
    evidence: dict = {
        "chrome": version.get("Browser"),
        "cdp": "Target.createTarget + attachToTarget flatten",
        "frontend": BASE,
        "backend": API,
        "vite_use_mock": False,
        "acs": {},
        "tech": {},
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
        await cdp.send("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
            (() => {
              const Orig = window.EventSource;
              if (!Orig || Orig.__xtripWrapped) return;
              function Wrapped(url, cfg) {
                const es = new Orig(url, cfg);
                window.__xtripES = window.__xtripES || [];
                window.__xtripES.push(es);
                return es;
              }
              Wrapped.prototype = Orig.prototype;
              Wrapped.CONNECTING = Orig.CONNECTING;
              Wrapped.OPEN = Orig.OPEN;
              Wrapped.CLOSED = Orig.CLOSED;
              Wrapped.__xtripWrapped = true;
              window.EventSource = Wrapped;
            })();
            """
        })
        await cdp.send("Page.navigate", {"url": BASE + "/"})
        home = await wait_snap(cdp, lambda s: s and s.get("composer"), timeout=20)
        await cdp.screenshot("01-home.png")
        evidence["home"] = {
            "hasMock": home.get("hasMock"),
            "composer": home.get("composer"),
            "path": home.get("path"),
            "welcome": home.get("welcome"),
        }
        if home.get("hasMock") or not home.get("composer"):
            evidence["acs"]["AC-003"] = {"result": "FAIL", "reason": "首页有 [Mock] 或无输入框", "home": evidence["home"]}
            evidence["acs"]["AC-024"] = {"result": "BLOCKED", "reason": "首页未进入真链路"}
            evidence["acs"]["AC-004"] = {"result": "BLOCKED", "reason": "首页未进入真链路"}
            EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            return evidence

        # --- AC-003 success path ---
        await send_chat(cdp, "上海出发带配偶去杭州 5 天、预算 2 万、不要太赶")
        after_send = await wait_snap(
            cdp,
            lambda s: s and (s.get("coco") or s.get("sendError") or s.get("logHead") or (s.get("stepCount") or 0) >= 1),
            timeout=90,
        )
        await cdp.screenshot("02-sent-success.png")
        await wait_snap(
            cdp,
            lambda s: s and ((s.get("stepCount") or 0) >= 1 or three_specialists(s.get("specs"))),
            timeout=40,
        )
        es_cut = await cdp.eval(
            """
            (() => {
              const list = window.__xtripES || [];
              let closed = 0;
              for (const es of list) {
                try { es.close(); closed += 1; } catch (e) {}
              }
              return { count: list.length, closed };
            })()
            """
        )
        poll_before = len(cdp.poll_hits)
        snap3, api3, wait3 = await wait_planning(cdp, timeout=180)
        await cdp.screenshot("03-planning-done.png")

        cid3 = snap3.get("conversationId") or api3.get("id")
        api3 = await fetch_api003(cdp, cid3)
        coco_texts = snap3.get("coco") or []
        actions = chinese_actions(snap3.get("steps"))
        process_specs = three_specialists(snap3.get("specs"))
        trip_ok = bool(snap3.get("tripLink"))
        no_cards = not looks_like_day_cards(coco_texts)
        planning_ok = api3.get("planning") == "succeeded" and bool(api3.get("itinerary_id"))
        no_mock = not snap3.get("hasMock")
        coco_done = bool(snap3.get("cocoLast"))
        ac003_pass = (
            process_specs
            and len(actions) >= 2
            and coco_done
            and trip_ok
            and no_cards
            and planning_ok
            and no_mock
            and wait3 <= 180
            and api3.get("http") == 200
        )
        evidence["acs"]["AC-003"] = {
            "result": "PASS" if ac003_pass else "FAIL",
            "wait_seconds": round(wait3, 1),
            "hasMock": snap3.get("hasMock"),
            "specs": snap3.get("specs"),
            "logHead": snap3.get("logHead"),
            "actionCount": len(actions),
            "actions": actions[:12],
            "tripLink": snap3.get("tripLink"),
            "tripHref": snap3.get("tripHref"),
            "cocoLast": clip(snap3.get("cocoLast") or ""),
            "dayCardsInBubble": not no_cards,
            "api": {
                "http": api3.get("http"),
                "planning": api3.get("planning"),
                "itinerary_id": api3.get("itinerary_id"),
                "dest": api3.get("dest"),
                "origin": api3.get("origin"),
                "days": api3.get("days"),
                "logCount": api3.get("logCount"),
                "specs": api3.get("specs"),
            },
            "sendError": snap3.get("sendError"),
        }

        # EventSource 抽检：关掉页面 EventSource 后看 2s 轮询是否仍在
        poll_after = [t for t in cdp.poll_hits]
        poll_gaps = []
        if len(poll_after) >= 2:
            recent = poll_after[-8:]
            poll_gaps = [round(recent[i] - recent[i - 1], 2) for i in range(1, len(recent))]
        evidence["tech"]["eventsource_poll"] = {
            "closed": es_cut,
            "poll_hits_after_cut": len(cdp.poll_hits) - poll_before,
            "recent_gaps_s": poll_gaps,
            "reached_terminal": api3.get("planning") in ("succeeded", "failed"),
        }

        # --- AC-024 click log modal ---
        if not snap3.get("logOpen"):
            await click(cdp, ".activity-log-head")
            await asyncio.sleep(0.4)
        clicked = await click_step(cdp, r"搜索景点|查询公交|搜索|公交|地理编码|查询")
        modal_snap = await wait_snap(cdp, lambda s: s and s.get("modal"), timeout=8)
        await cdp.screenshot("04-log-modal.png")
        heading = modal_snap.get("modalHeading") or ""
        body = modal_snap.get("modalBody") or ""
        leaks = leak_in(heading + "\n" + body)
        path_before = modal_snap.get("path")
        cid_before = modal_snap.get("conversationId")
        closed = False
        still_chat = False
        still_composer = False
        after_close = modal_snap
        if modal_snap.get("modal"):
            await click(cdp, ".log-detail-modal .cta-btn")
            after_close = await wait_snap(cdp, lambda s: s and not s.get("modal"), timeout=8)
            closed = not after_close.get("modal")
            still_chat = after_close.get("conversationId") == cid_before and after_close.get("path") in (path_before, "/")
            still_composer = bool(after_close.get("composer"))
        await cdp.screenshot("05-modal-closed.png")
        ac024_pass = (
            bool(clicked.get("ok"))
            and bool(heading.strip())
            and bool(body.strip())
            and not leaks
            and closed
            and still_chat
            and still_composer
            and not after_close.get("hasMock")
        )
        evidence["acs"]["AC-024"] = {
            "result": "PASS" if ac024_pass else "FAIL",
            "clicked": clicked,
            "heading": clip(heading, 80),
            "body": clip(body, 180),
            "bodyLen": len(body),
            "leaks": leaks,
            "closed": closed,
            "stillConversation": still_chat,
            "pathAfter": after_close.get("path"),
            "conversationIdSame": after_close.get("conversationId") == cid_before,
        }

        # --- AC-004 fail path ---
        await fresh_home(cdp)
        await cdp.screenshot("06-fail-home.png")
        await send_chat(cdp, "上海出发带配偶去䶮䶮䶮阿巴市 5 天、预算 2 万、不要太赶")
        await wait_snap(cdp, lambda s: s and (s.get("coco") or s.get("sendError")), timeout=90)
        snap4, api4, wait4 = await wait_planning(cdp, timeout=180)
        await cdp.screenshot("07-fail-done.png")
        cid4 = snap4.get("conversationId") or api4.get("id")
        api4 = await fetch_api003(cdp, cid4)
        coco4 = snap4.get("cocoLast") or ((api4.get("coco") or [""])[-1] if api4.get("coco") else "")
        err = api4.get("error_message") or ""
        reason_ok = bool(re.search(r"无法|没法|找不到|检索|地图|目的地|失败|不可用|没有", coco4))
        has_reason = bool(re.search(r"原因|因为|找不到|检索不到|无法|地图|不存在|没有可用", coco4))
        no_fake = (
            not snap4.get("tripLink")
            and not api4.get("itinerary_id")
            and not looks_like_day_cards(snap4.get("coco") or [])
        )
        id_empty = api4.get("itinerary_id") in (None, "")
        err_align = bool(err) and (
            err[:20] in coco4 or coco4[:20] in err or any(token in coco4 for token in re.findall(r"[\u4e00-\u9fff]{2,}", err)[:8])
        )
        if not snap4.get("logOpen"):
            await click(cdp, ".activity-log-head")
            await asyncio.sleep(0.3)
        fail_click = await click_step(cdp, r"未完成|失败|找不到|检索")
        if not fail_click.get("ok"):
            fail_click = await click_step(cdp, r".+")
        fail_modal = await wait_snap(cdp, lambda s: s and s.get("modal"), timeout=8)
        await cdp.screenshot("08-fail-modal.png")
        fail_leaks = leak_in((fail_modal.get("modalHeading") or "") + "\n" + (fail_modal.get("modalBody") or ""))
        fail_modal_ok = bool(fail_modal.get("modalHeading")) and bool(fail_modal.get("modalBody")) and not fail_leaks
        if fail_modal.get("modal"):
            await click(cdp, ".log-detail-modal .cta-btn")
        ac004_pass = (
            api4.get("planning") == "failed"
            and id_empty
            and no_fake
            and reason_ok
            and has_reason
            and err_align
            and fail_modal_ok
            and not snap4.get("hasMock")
            and wait4 <= 180
            and bool(coco4)
        )
        evidence["acs"]["AC-004"] = {
            "result": "PASS" if ac004_pass else "FAIL",
            "wait_seconds": round(wait4, 1),
            "cocoLast": clip(coco4),
            "error_message": clip(err),
            "reasonInCoco": has_reason,
            "errorAligned": err_align,
            "itinerary_id": api4.get("itinerary_id"),
            "tripLink": snap4.get("tripLink"),
            "failStripe": snap4.get("failStripe"),
            "specs": api4.get("specs"),
            "logCount": api4.get("logCount"),
            "failStep": fail_click,
            "modalHeading": clip(fail_modal.get("modalHeading") or "", 80),
            "modalBody": clip(fail_modal.get("modalBody") or "", 160),
            "modalLeaks": fail_leaks,
            "http": api4.get("http"),
            "planning": api4.get("planning"),
            "sendError": snap4.get("sendError"),
        }

        src_hits = [n for n in cdp.network if n.get("status") == "SRC_HIT"]
        api_net = [
            {"url": n["url"].replace(API, "").replace(BASE, ""), "status": n["status"]}
            for n in cdp.network
            if "/api/" in n.get("url", "")
        ][-60:]
        evidence["tech"]["no_src_curl"] = {"src_module_hits": len(src_hits), "checked": "DOM + /api only"}
        evidence["network_api"] = api_net
        evidence["hasMockAny"] = any(
            (evidence["acs"].get(k) or {}).get("hasMock") for k in evidence["acs"]
        )

    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence


if __name__ == "__main__":
    out = asyncio.run(run())
    print(json.dumps({k: v.get("result") for k, v in out.get("acs", {}).items()}, ensure_ascii=False))
    for key, val in out.get("acs", {}).items():
        print(key, val.get("result"), "wait", val.get("wait_seconds"), "planning", (val.get("api") or {}).get("planning") or val.get("planning"))
    print("evidence", EVIDENCE)
