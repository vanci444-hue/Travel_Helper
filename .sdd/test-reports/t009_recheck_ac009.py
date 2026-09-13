#!/usr/bin/env python3
"""AC-009 定向复核一次：北京出发带小孩想看海。"""

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
    click,
    fetch_api003,
    fill,
    recommended_city,
    send_chat,
    wait_coco,
    wait_snap,
)

SHOTS = Path(__file__).resolve().parent / "t009-shots"
OUT = Path(__file__).resolve().parent / "t009-ac009-recheck.json"


async def main() -> dict:
    version = json.loads(urllib.request.urlopen("http://127.0.0.1:9610/json/version").read())
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
        await cdp.send("Page.navigate", {"url": "http://127.0.0.1:5199/"})
        await asyncio.sleep(1.2)
        await cdp.eval("localStorage.removeItem('xtrip_conversation_id'); location.href='/';")
        await asyncio.sleep(1.0)
        home = await wait_snap(cdp, lambda s: s and s.get("composer"), timeout=20)
        await send_chat(cdp, "从北京出发带小孩想看海 4 天预算 8 千别太赶")
        snap = await wait_coco(cdp, timeout=80)
        data = await cdp.screenshot("11-ac009-recheck.png")
        api = await fetch_api003(cdp, snap.get("conversationId") if snap else None)
        coco = snap.get("coco") or [] if snap else []
        city = recommended_city(coco, api.get("dest"))
        dest_started = api.get("planning") == "running" or any(
            s.get("status") in ("running", "succeeded") for s in (api.get("specs") or [])
        )
        asked_pick = bool(re.search(r"选一个|点选|先选.*城", " ".join(coco)))
        ok = bool(city) and dest_started and not asked_pick and api.get("http") == 200
        result = {
            "result": "PASS" if ok else "FAIL",
            "homeMock": home.get("hasMock") if home else None,
            "city": city,
            "coco": (coco[-1][:280] if coco else ""),
            "allCoco": [c[:200] for c in coco],
            "api": api,
            "askedPickCity": asked_pick,
            "uiSpecs": snap.get("specs") if snap else [],
            "sendError": snap.get("sendError") if snap else "",
            "shot": data,
        }
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result


if __name__ == "__main__":
    out = asyncio.run(main())
    print(json.dumps(out, ensure_ascii=False, indent=2))
