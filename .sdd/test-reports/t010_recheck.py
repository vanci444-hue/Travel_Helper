#!/usr/bin/env python3
"""T-010 定向复核：AC-003 气泡是否真有按天全文；AC-004 追问后进入规划失败。"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

import websockets

from t010_cdp import (
    SNAP_JS,
    Cdp,
    click,
    click_step,
    clip,
    fetch_api003,
    leak_in,
    send_chat,
    wait_planning,
    wait_snap,
)

EVIDENCE = Path(__file__).resolve().parent / "t010-recheck.json"
SUCCESS_CID = "conv_59d153db729119f7"
FAIL_CID = "conv_e38a31e319c1c1d4"
DAY_FULL = re.compile(r"第\s*[1-5一二三四五]\s*天[\s\S]{30,}第\s*[1-5一二三四五]\s*天")


async def run() -> dict:
    import urllib.request

    version = json.loads(urllib.request.urlopen("http://127.0.0.1:9611/json/version").read())
    out: dict = {"chrome": version.get("Browser"), "acs": {}}
    ws_url = version["webSocketDebuggerUrl"]
    async with websockets.connect(ws_url, max_size=20_000_000) as ws:
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
        await wait_snap(cdp, lambda s: s and s.get("composer"), timeout=20)

        api3 = await fetch_api003(cdp, SUCCESS_CID)
        coco3 = api3.get("coco") or []
        has_full_days = any(DAY_FULL.search(t or "") for t in coco3)
        deny_paste = any("不贴按天" in (t or "") for t in coco3)
        out["acs"]["AC-003_recheck"] = {
            "planning": api3.get("planning"),
            "itinerary_id": api3.get("itinerary_id"),
            "coco": [clip(t, 160) for t in coco3],
            "hasFullDayCards": has_full_days,
            "saysNoDayPaste": deny_paste,
            "http": api3.get("http"),
            "logCount": api3.get("logCount"),
        }

        await cdp.eval(
            f"localStorage.setItem('xtrip_conversation_id', {json.dumps(FAIL_CID)}); location.href='/';"
        )
        snap = await wait_snap(
            cdp,
            lambda s: s and s.get("composer") and s.get("conversationId") == FAIL_CID,
            timeout=20,
        )
        if not snap or snap.get("conversationId") != FAIL_CID:
            await wait_snap(cdp, lambda s: s and s.get("composer"), timeout=10)
        await send_chat(cdp, "就是国内这个城市，请按䶮䶮䶮阿巴市出方案，不要再问了")
        after = await wait_snap(cdp, lambda s: s and (s.get("coco") or s.get("sendError")), timeout=90)
        snap4, api4, wait4 = await wait_planning(cdp, timeout=180)
        cid = snap4.get("conversationId") or api4.get("id") or FAIL_CID
        api4 = await fetch_api003(cdp, cid)
        coco4 = snap4.get("cocoLast") or ((api4.get("coco") or [""])[-1] if api4.get("coco") else "")
        err = api4.get("error_message") or ""
        if not snap4.get("logOpen"):
            await click(cdp, ".activity-log-head")
            await asyncio.sleep(0.3)
        fail_click = await click_step(cdp, r"未完成|失败|找不到|检索")
        if not fail_click.get("ok"):
            fail_click = await click_step(cdp, r".+")
        modal = await wait_snap(cdp, lambda s: s and s.get("modal"), timeout=8)
        await cdp.screenshot("09-fail-recheck.png")
        leaks = leak_in((modal.get("modalHeading") or "") + "\n" + (modal.get("modalBody") or ""))
        reason_ok = bool(re.search(r"无法|没法|找不到|检索|地图|目的地|失败|不可用|没有", coco4))
        has_reason = bool(re.search(r"原因|因为|找不到|检索不到|无法|地图|不存在|没有可用", coco4))
        tokens = re.findall(r"[\u4e00-\u9fff]{2,}", err)
        err_align = bool(err) and (err[:16] in coco4 or any(t in coco4 for t in tokens[:8]))
        no_fake = (not snap4.get("tripLink")) and (api4.get("itinerary_id") in (None, ""))
        ac004_pass = (
            api4.get("planning") == "failed"
            and no_fake
            and reason_ok
            and has_reason
            and err_align
            and bool(modal.get("modalHeading"))
            and bool(modal.get("modalBody"))
            and not leaks
            and not snap4.get("hasMock")
        )
        out["acs"]["AC-004_recheck"] = {
            "result": "PASS" if ac004_pass else "FAIL",
            "wait_seconds": round(wait4, 1),
            "afterSendCoco": clip((after.get("cocoLast") if after else "") or ""),
            "cocoLast": clip(coco4),
            "error_message": clip(err),
            "reasonInCoco": has_reason,
            "errorAligned": err_align,
            "itinerary_id": api4.get("itinerary_id"),
            "tripLink": snap4.get("tripLink"),
            "specs": api4.get("specs"),
            "logCount": api4.get("logCount"),
            "failStep": fail_click,
            "modalHeading": clip(modal.get("modalHeading") or "", 80),
            "modalBody": clip(modal.get("modalBody") or "", 160),
            "modalLeaks": leaks,
            "planning": api4.get("planning"),
            "http": api4.get("http"),
            "conversationId": cid,
            "ready": api4.get("ready"),
            "dest": api4.get("dest"),
            "sendError": snap4.get("sendError"),
        }
    EVIDENCE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    data = asyncio.run(run())
    print(json.dumps(data.get("acs"), ensure_ascii=False, indent=2))
