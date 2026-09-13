#!/usr/bin/env python3
"""T-009 返工复验：锁过后定向复核 AC-002/011/014/001 与刷新。"""

from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.request
from pathlib import Path

import websockets

from t009_cdp import (
    Cdp,
    SNAP_JS,
    click_text,
    fill,
    fresh_home,
    looks_like_plan,
    mentions_origin,
    mentions_outbound,
    mentions_pace,
    send_chat,
    wait_coco,
    wait_snap,
)
from t009_retest1 import fetch_api003

OUT = Path(__file__).resolve().parent / "t009-retest1-regress.json"
BASE = "http://127.0.0.1:5199"


async def wait_create_ok(cdp: Cdp, timeout=90.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = await cdp.eval(
            """
            (async () => {
              const res = await fetch('/api/conversations', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
              let body = null;
              try { body = await res.json(); } catch (e) { body = {parseError: String(e)}; }
              return {http: res.status, id: (body.data && body.data.id) || null, message: body.message || body.error || ''};
            })()
            """
        )
        if last and last.get("http") == 201 and last.get("id"):
            return last
        await asyncio.sleep(2.0)
    return last or {"error": "timeout waiting for create"}


async def main() -> dict:
    version = json.loads(urllib.request.urlopen("http://127.0.0.1:9610/json/version").read())
    evidence: dict = {"round": "retest-1-regress", "chrome": version.get("Browser"), "acs": {}}

    async with websockets.connect(version["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
        cdp = Cdp(ws)
        await cdp.start()
        created = await cdp.send("Target.createTarget", {"url": "about:blank"}, session=False)
        attached = await cdp.send(
            "Target.attachToTarget",
            {"targetId": created["targetId"], "flatten": True},
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
        await asyncio.sleep(1.2)
        home = await wait_snap(cdp, lambda s: s and s.get("composer"), timeout=20)

        probe = await wait_create_ok(cdp, timeout=120)
        evidence["createProbe"] = probe
        if probe.get("http") != 201:
            evidence["blocked"] = "POST /api/conversations still locked"
            OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            return evidence

        # AC-002 first (does not start planning)
        await fresh_home(cdp)
        await send_chat(cdp, "想出去玩")
        snap002 = await wait_coco(cdp, timeout=90)
        await cdp.screenshot("r1-11-ac002.png")
        api002 = await fetch_api003(cdp, snap002.get("conversationId") if snap002 else None)
        specs002 = api002.get("specs") or []
        ac002_pass = (
            bool((snap002 or {}).get("coco"))
            and api002.get("http") == 200
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
            "coco": ((snap002.get("coco") or [""])[-1][:240] if snap002 and snap002.get("coco") else ""),
            "api": api002,
            "sendError": (snap002 or {}).get("sendError"),
            "hasMock": (snap002 or {}).get("hasMock"),
        }

        conv_before = (snap002 or {}).get("conversationId")
        await cdp.eval("location.reload()")
        await asyncio.sleep(1.5)
        refreshed = await wait_snap(
            cdp,
            lambda s: s and s.get("conversationId") == conv_before and s.get("users"),
            timeout=20,
        )
        await cdp.screenshot("r1-12-refresh.png")
        api_ref = await fetch_api003(cdp, conv_before)
        refresh_ok = (
            refreshed
            and refreshed.get("conversationId") == conv_before
            and any("想出去玩" in u for u in (refreshed.get("users") or []))
            and api_ref.get("http") == 200
        )
        evidence["refresh"] = {
            "result": "PASS" if refresh_ok else "FAIL",
            "id": conv_before,
            "users": refreshed.get("users") if refreshed else [],
            "api": api_ref,
        }

        # AC-011
        await fresh_home(cdp)
        await send_chat(cdp, "想和朋友去海边，预算一万，轻松一点")
        s1 = await wait_coco(cdp, timeout=90)
        await send_chat(cdp, "两个人，国内就行")
        s2 = await wait_coco(cdp, timeout=90)
        await send_chat(cdp, "你先看着办吧，出发地和玩几天我还没定")
        s3 = await wait_coco(cdp, timeout=90)
        await cdp.screenshot("r1-13-ac011.png")
        api011 = await fetch_api003(cdp, s3.get("conversationId") if s3 else None)
        last = ((s3.get("coco") or [""])[-1] if s3 else "")
        gap_explained = bool(re.search(r"缺|出发|几天|时长|天数", last))
        no_plan = not looks_like_plan([last]) and api011.get("itinerary_id") in (None, "")
        specs_idle = all(s.get("status") == "not_started" for s in (api011.get("specs") or [])) or api011.get("planning") == "idle"
        ac011_pass = gap_explained and no_plan and specs_idle and (api011.get("followups") or 0) >= 2
        evidence["acs"]["AC-011"] = {
            "result": "PASS" if ac011_pass else "FAIL",
            "rounds": [((x.get("coco") or [""])[-1][:180] if x and x.get("coco") else "") for x in (s1, s2, s3)],
            "last": last[:240],
            "api": api011,
            "gapExplained": gap_explained,
            "noPlan": no_plan,
            "sendError": (s1 or {}).get("sendError"),
        }

        # AC-014
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
        await click_text(cdp, ".cta-btn", "开始聊")
        snap014 = await wait_coco(cdp, timeout=90)
        await cdp.screenshot("r1-14-ac014.png")
        api014 = await fetch_api003(cdp, snap014.get("conversationId") if snap014 else None)
        coco014 = snap014.get("coco") or [] if snap014 else []
        asked_origin = mentions_origin(coco014)
        missing = api014.get("missing") or []
        ac014_pass = (
            api014.get("dest") == "杭州"
            and api014.get("days") == 5
            and api014.get("pace") in ("relaxed", "轻松")
            and "pace" not in missing
            and (
                asked_origin
                or (api014.get("ready") and api014.get("planning") == "running")
            )
        )
        evidence["acs"]["AC-014"] = {
            "result": "PASS" if ac014_pass else "FAIL",
            "modalOpened": modal.get("modal") if modal else False,
            "coco": (coco014[-1][:240] if coco014 else ""),
            "askedPace": mentions_pace(coco014),
            "askedOrigin": asked_origin,
            "api": api014,
            "sendError": (snap014 or {}).get("sendError"),
        }

        # AC-001 last (starts planning)
        await fresh_home(cdp)
        await send_chat(cdp, "从上海出发，带配偶去杭州 5 天，预算 2 万，不要太赶")
        snap001 = await wait_coco(cdp, timeout=90)
        await cdp.screenshot("r1-15-ac001.png")
        api001 = await fetch_api003(cdp, snap001.get("conversationId") if snap001 else None)
        dest_running = any(
            s.get("role") == "destination_research" and s.get("status") == "running" for s in (api001.get("specs") or [])
        )
        ac001_pass = (
            api001.get("http") == 200
            and api001.get("planning") == "running"
            and dest_running
            and not mentions_outbound(snap001.get("coco") or [] if snap001 else [])
            and api001.get("ready") is True
        )
        evidence["acs"]["AC-001"] = {
            "result": "PASS" if ac001_pass else "FAIL",
            "coco": ((snap001.get("coco") or [""])[-1][:240] if snap001 and snap001.get("coco") else ""),
            "api": api001,
            "askedOutbound": mentions_outbound(snap001.get("coco") or [] if snap001 else []),
            "uiSpecs": snap001.get("specs") if snap001 else [],
            "sendError": (snap001 or {}).get("sendError"),
        }

        evidence["homeMock"] = home.get("hasMock") if home else None

    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence


if __name__ == "__main__":
    out = asyncio.run(main())
    print(json.dumps({k: v.get("result") for k, v in out.get("acs", {}).items()}, ensure_ascii=False))
    print("refresh", out.get("refresh", {}).get("result"))
    print("probe", out.get("createProbe"))
    print("evidence", OUT)
