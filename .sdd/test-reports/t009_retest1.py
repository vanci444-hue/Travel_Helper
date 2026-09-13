#!/usr/bin/env python3
"""T-009 第 1 次返工复验。先验 AC-009，再回归。只看 DOM 与 /api。"""

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
    click_text,
    fetch_trips,
    fill,
    fresh_home,
    looks_like_plan,
    mentions_origin,
    mentions_outbound,
    mentions_pace,
    recommended_city,
    send_chat,
    wait_coco,
    wait_snap,
)

SHOTS = Path(__file__).resolve().parent / "t009-shots"
OUT = Path(__file__).resolve().parent / "t009-retest1.json"
BASE = "http://127.0.0.1:5199"


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
            companions: intake.companion_type,
            children: intake.children_age_bands,
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


def asked_age(texts: list[str]) -> bool:
    blob = " ".join(texts)
    return bool(re.search(r"几岁|年龄|多大", blob))


def asked_outbound_choice(texts: list[str]) -> bool:
    blob = " ".join(texts)
    return bool(re.search(r"出境|出国|国内还是出|国内的海边|还是想出境", blob))


def asked_pick_city(texts: list[str]) -> bool:
    blob = " ".join(texts)
    return bool(re.search(r"选一个|点选|先选.*城|你想去哪座", blob))


def specialist_running(api: dict) -> bool:
    return any(s.get("status") == "running" for s in (api.get("specs") or []))


async def main() -> dict:
    version = json.loads(urllib.request.urlopen("http://127.0.0.1:9610/json/version").read())
    evidence: dict = {
        "round": "retest-1",
        "chrome": version.get("Browser"),
        "cdp": "Target.createTarget + attachToTarget flatten",
        "frontend": BASE,
        "backend": "http://127.0.0.1:8099",
        "vite_use_mock": False,
        "acs": {},
        "experience": {},
    }

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
        await asyncio.sleep(1.5)
        home = await wait_snap(cdp, lambda s: s and s.get("composer"), timeout=20)
        await cdp.screenshot("r1-01-home.png")

        # --- AC-012 spot ---
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
        evidence["acs"]["AC-012"] = {
            "result": "PASS" if ac012_pass else "FAIL",
            "spot": True,
            "hasMock": home.get("hasMock") if home else None,
            "leftNav": home.get("leftNav") if home else [],
            "inspirationHead": home.get("inspirationHead") if home else "",
            "mapSlot": home.get("mapSlot") if home else None,
            "cards": home.get("cards") if home else [],
        }

        # --- AC-020 spot ---
        trips_before = await fetch_trips(cdp)
        await click(cdp, ".inspiration-card")
        await asyncio.sleep(0.8)
        after_click = await cdp.eval(SNAP_JS)
        trips_after = await fetch_trips(cdp)
        await cdp.screenshot("r1-02-inspiration.png")
        ac020_pass = (
            after_click.get("path") == "/"
            and not after_click.get("tripLink")
            and trips_after.get("count") == trips_before.get("count")
            and not after_click.get("hasMock")
        )
        evidence["acs"]["AC-020"] = {
            "result": "PASS" if ac020_pass else "FAIL",
            "spot": True,
            "path": after_click.get("path"),
            "tripsBefore": trips_before,
            "tripsAfter": trips_after,
            "tripLink": after_click.get("tripLink"),
            "conversationId": after_click.get("conversationId"),
        }

        # --- AC-009 main retest ---
        await fresh_home(cdp)
        await send_chat(cdp, "从北京出发带小孩想看海 4 天预算 8 千别太赶")
        snap009 = await wait_coco(cdp, timeout=90)
        await cdp.screenshot("r1-03-ac009.png")
        api009 = await fetch_api003(cdp, snap009.get("conversationId") if snap009 else None)
        coco009 = snap009.get("coco") or [] if snap009 else []
        city = recommended_city(coco009, api009.get("dest"))
        dest_started = api009.get("planning") == "running" and specialist_running(api009)
        still_blocking_ask = (
            api009.get("planning") in (None, "idle")
            and (asked_outbound_choice(coco009) or asked_age(coco009) or asked_pick_city(coco009))
        )
        ac009_pass = (
            bool(city)
            and dest_started
            and api009.get("http") == 200
            and not asked_pick_city(coco009)
            and not still_blocking_ask
            and not (snap009 or {}).get("hasMock")
        )
        evidence["acs"]["AC-009"] = {
            "result": "PASS" if ac009_pass else "FAIL",
            "city": city,
            "coco": (coco009[-1][:240] if coco009 else ""),
            "allCoco": [c[:200] for c in coco009],
            "api": api009,
            "askedOutbound": asked_outbound_choice(coco009),
            "askedAge": asked_age(coco009),
            "askedPickCity": asked_pick_city(coco009),
            "uiSpecs": snap009.get("specs") if snap009 else [],
            "sendError": snap009.get("sendError") if snap009 else "",
            "hasMock": (snap009 or {}).get("hasMock"),
        }
        evidence["experience"]["sea_rule"] = {
            "dest": api009.get("dest"),
            "region": api009.get("region"),
            "children": api009.get("children"),
            "ready": api009.get("ready"),
            "missing": api009.get("missing"),
            "planning": api009.get("planning"),
            "specs": api009.get("specs"),
            "model_ask_blocked_ready": still_blocking_ask,
        }

        # --- AC-001 regression ---
        await fresh_home(cdp)
        await send_chat(cdp, "从上海出发，带配偶去杭州 5 天，预算 2 万，不要太赶")
        snap001 = await wait_coco(cdp, timeout=90)
        await cdp.screenshot("r1-04-ac001.png")
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
            and not (snap001 or {}).get("hasMock")
        )
        evidence["acs"]["AC-001"] = {
            "result": "PASS" if ac001_pass else "FAIL",
            "coco": ((snap001.get("coco") or [""])[-1][:240] if snap001 and snap001.get("coco") else ""),
            "api": api001,
            "askedOutbound": mentions_outbound(snap001.get("coco") or [] if snap001 else []),
            "uiSpecs": snap001.get("specs") if snap001 else [],
        }

        # --- AC-002 + AC-013 + refresh ---
        await fresh_home(cdp)
        await send_chat(cdp, "想出去玩")
        snap002 = await wait_coco(cdp, timeout=90)
        await cdp.screenshot("r1-05-ac002.png")
        api002 = await fetch_api003(cdp, snap002.get("conversationId") if snap002 else None)
        specs002 = api002.get("specs") or []
        ac002_pass = (
            bool((snap002 or {}).get("coco"))
            and not (snap002 or {}).get("hasMock")
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
            "mapHead": (snap002 or {}).get("mapHead"),
            "hasMock": (snap002 or {}).get("hasMock"),
        }

        ac013_switched = bool((snap002 or {}).get("mapSlot") and (snap002 or {}).get("mapHead") and not (snap002 or {}).get("cards"))
        tiles_ok = bool((snap002 or {}).get("amap") or (snap002 or {}).get("canvasCount") or (snap002 or {}).get("hasAMap"))
        evidence["acs"]["AC-013"] = {
            "result": "PASS" if ac013_switched else "FAIL",
            "spot": True,
            "switched": ac013_switched,
            "mapCopy": (snap002 or {}).get("mapCopy"),
            "amap": (snap002 or {}).get("amap"),
            "canvasCount": (snap002 or {}).get("canvasCount"),
            "hasAMap": (snap002 or {}).get("hasAMap"),
            "tiles": "ok" if tiles_ok else "unverified",
        }
        await cdp.screenshot("r1-06-map.png")

        conv_before = (snap002 or {}).get("conversationId")
        users_before = (snap002 or {}).get("users")
        await cdp.eval("location.reload()")
        await asyncio.sleep(1.5)
        refreshed = await wait_snap(
            cdp,
            lambda s: s and s.get("conversationId") == conv_before and s.get("users"),
            timeout=20,
        )
        await cdp.screenshot("r1-07-refresh.png")
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

        # --- AC-011 ---
        await fresh_home(cdp)
        await send_chat(cdp, "想和朋友去海边，预算一万，轻松一点")
        s1 = await wait_coco(cdp, timeout=90)
        await send_chat(cdp, "两个人，国内就行")
        s2 = await wait_coco(cdp, timeout=90)
        await send_chat(cdp, "你先看着办吧，出发地和玩几天我还没定")
        s3 = await wait_coco(cdp, timeout=90)
        await cdp.screenshot("r1-08-ac011.png")
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
        }

        # --- AC-014 ---
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
        await cdp.screenshot("r1-09-new-plan.png")
        await click_text(cdp, ".cta-btn", "开始聊")
        snap014 = await wait_coco(cdp, timeout=90)
        await cdp.screenshot("r1-10-ac014.png")
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
        }

        evidence["network_api"] = [
            {"url": n["url"], "status": n["status"]}
            for n in cdp.network
            if "/api/" in n["url"] and "/src/" not in n["url"]
        ][-50:]
        evidence["hasMockAny"] = any(
            (evidence["acs"].get(k) or {}).get("hasMock") for k in evidence["acs"]
        )

    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence


if __name__ == "__main__":
    out = asyncio.run(main())
    print(json.dumps({k: v.get("result") for k, v in out.get("acs", {}).items()}, ensure_ascii=False))
    print("refresh", out.get("refresh", {}).get("result"))
    print("ac009", json.dumps(out.get("acs", {}).get("AC-009"), ensure_ascii=False)[:800])
    print("evidence", OUT)
