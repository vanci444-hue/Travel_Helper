#!/usr/bin/env python3
"""T-011 定向复核：AC-021 滚动带、AC-006/017 删卡、AC-019 未动过行程点建议。"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import websockets

from t011_cdp import (
    BASE,
    Cdp,
    DELETE_CONV,
    DELETE_ID,
    DELETE_TITLE_HINT,
    DISPLAY_ID,
    SHOTS,
    SNAP_JS,
    click_day_chip,
    click_trip_by_id,
    fetch_itinerary,
    fetch_planning,
    open_trips,
    snap,
    wait_detail,
    wait_revision,
    wait_snap,
)

EVIDENCE = Path(__file__).resolve().parent / "t011-recheck.json"
HAINAN_ID = "itn_63f6c180617024d5"
HAINAN_CONV = "conv_d4db2cfd218d672d"
SUGGEST_TEXT = "换一家更安静的推荐住宿"


async def wait_detail_or_suggest(cdp, itinerary_id: str) -> dict:
    return await wait_snap(
        cdp,
        lambda s: s and itinerary_id in (s.get("path") or "") and s.get("hasBudget") and (s.get("suggest") or s.get("days")),
        timeout=25,
    )


async def scroll_day_into_band(cdp, day: int) -> dict:
    return await cdp.eval(
        f"""
        (() => {{
          const root = document.querySelector('.detail-report-body');
          const target = document.querySelector('[data-day="{day}"]');
          if (!root || !target) return {{ok:false}};
          const rootRect = root.getBoundingClientRect();
          const targetRect = target.getBoundingClientRect();
          root.scrollTop += (targetRect.top - rootRect.top - 12);
          root.dispatchEvent(new Event('scroll'));
          return {{ok:true, scrollTop: root.scrollTop}};
        }})()
        """
    )


async def delete_card(cdp, day: int, hint: str) -> dict:
    opened = await cdp.eval(
        f"""
        (() => {{
          const section = document.querySelector('[data-day="{day}"]');
          if (!section) return {{ok:false, reason:'no-day'}};
          const cards = [...section.querySelectorAll('.itinerary-card')];
          const card = cards.find((n) => (n.textContent || '').includes({json.dumps(hint)}));
          if (!card) return {{ok:false, reason:'no-card', n: cards.length}};
          const more = card.querySelector('[aria-label="更多操作"]');
          if (!more) return {{ok:false, reason:'no-more'}};
          more.scrollIntoView({{block:'center'}});
          more.click();
          return {{ok:true, title: ((card.querySelector('strong') || {{}}).textContent || '').slice(0, 16)}};
        }})()
        """
    )
    await asyncio.sleep(0.35)
    deleted = await cdp.eval(
        f"""
        (() => {{
          const section = document.querySelector('[data-day="{day}"]');
          const menus = [...document.querySelectorAll('.itinerary-card-menu button')];
          const delBtn = menus.find((n) => (n.textContent || '').trim() === '删除');
          if (!delBtn) return {{ok:false, reason:'no-delete', menu_n: menus.length}};
          delBtn.click();
          return {{ok:true}};
        }})()
        """
    )
    return {"opened": opened, "deleted": deleted}


async def run() -> dict:
    import urllib.request

    version = json.loads(urllib.request.urlopen("http://127.0.0.1:9613/json/version").read())
    out = {"chrome": version.get("Browser"), "acs": {}, "tech": {}}
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

        await cdp.send("Page.navigate", {"url": BASE + "/trips"})
        await open_trips(cdp)
        await click_trip_by_id(cdp, DISPLAY_ID)
        page = await wait_detail(cdp, DISPLAY_ID)
        await click_day_chip(cdp, "第 1 天")
        await asyncio.sleep(0.6)
        await scroll_day_into_band(cdp, 3)
        await asyncio.sleep(0.7)
        after_scroll = await snap(cdp)
        selected_scroll = next((c.get("text") for c in after_scroll.get("chips") or [] if c.get("selected")), "")
        # 若一次滚过头，按观察带再微调一次
        if selected_scroll != "第 3 天":
            await cdp.eval(
                """
                (() => {
                  const root = document.querySelector('.detail-report-body');
                  if (!root) return false;
                  root.scrollTop = Math.max(0, root.scrollTop - Math.round(root.clientHeight * 0.25));
                  root.dispatchEvent(new Event('scroll'));
                  return true;
                })()
                """
            )
            await asyncio.sleep(0.6)
            after_scroll = await snap(cdp)
            selected_scroll = next((c.get("text") for c in after_scroll.get("chips") or [] if c.get("selected")), "")
        await cdp.screenshot("r1-scroll-day3.png")
        clicked = await click_day_chip(cdp, "第 1 天")
        await asyncio.sleep(0.8)
        after_chip = await snap(cdp)
        selected_chip = next((c.get("text") for c in after_chip.get("chips") or [] if c.get("selected")), "")
        await cdp.screenshot("r1-chip-day1.png")
        out["acs"]["AC-021"] = {
            "result": "PASS" if selected_scroll == "第 3 天" and selected_chip == "第 1 天" and clicked else "FAIL",
            "after_scroll": selected_scroll,
            "after_chip": selected_chip,
            "scrollTop": after_scroll.get("scrollTop"),
            "chipScrollTop": after_chip.get("scrollTop"),
        }

        await open_trips(cdp)
        await click_trip_by_id(cdp, DELETE_ID)
        await wait_detail(cdp, DELETE_ID)
        before = await fetch_itinerary(cdp, DELETE_ID)
        before_plan = await fetch_planning(cdp, DELETE_CONV)
        before_d2 = next((r for r in before.get("dayRows") or [] if r.get("day") == 2), {})
        deleted = await delete_card(cdp, 2, DELETE_TITLE_HINT)
        await asyncio.sleep(1.0)
        after_ui = await snap(cdp)
        after = await fetch_itinerary(cdp, DELETE_ID)
        after_plan = await fetch_planning(cdp, DELETE_CONV)
        after_d2 = next((r for r in after.get("dayRows") or [] if r.get("day") == 2), {})
        await cdp.screenshot("r1-after-delete.png")
        await cdp.eval(
            """
            (() => {
              const btn = [...document.querySelectorAll('.ghost-btn')].find((n) => (n.textContent || '').includes('地图模式'));
              if (btn) btn.click();
              return true;
            })()
            """
        )
        await asyncio.sleep(0.8)
        await click_day_chip(cdp, "第 2 天")
        await asyncio.sleep(0.6)
        del_map = await snap(cdp)
        await cdp.screenshot("r1-map-after-delete.png")
        gone = DELETE_TITLE_HINT not in " ".join(after_d2.get("titles") or [])
        map_has = any(DELETE_TITLE_HINT in t for t in (del_map.get("mapChips") or []))
        specs_ok = after_plan.get("allSucceeded") and not after_plan.get("running")
        out["acs"]["AC-006"] = {
            "result": "PASS" if deleted.get("deleted", {}).get("ok") and gone and specs_ok else "FAIL",
            "deleted": deleted,
            "before_n": before_d2.get("n"),
            "after_n": after_d2.get("n"),
            "after_titles": [t[:12] for t in (after_d2.get("titles") or [])],
            "planning": after_plan,
            "before_planning": before_plan.get("planning"),
        }
        out["acs"]["AC-017"] = {
            "result": "PASS" if gone and not map_has else "FAIL",
            "after_titles": [t[:12] for t in (after_d2.get("titles") or [])],
            "mapChips": del_map.get("mapChips"),
            "map_has_deleted": map_has,
        }

        await open_trips(cdp)
        await click_trip_by_id(cdp, HAINAN_ID)
        sug = await wait_detail_or_suggest(cdp, HAINAN_ID)
        before_019 = await fetch_itinerary(cdp, HAINAN_ID)
        clicked_sug = await cdp.eval(
            f"""
            (() => {{
              const el = [...document.querySelectorAll('.suggest-chip')].find((n) => (n.textContent || '').includes({json.dumps(SUGGEST_TEXT)}));
              const fallback = document.querySelector('.suggest-chip');
              const target = el || fallback;
              if (!target) return {{ok:false, chips: []}};
              const text = (target.textContent || '').trim();
              target.click();
              return {{ok:true, text: text.slice(0, 20)}};
            }})()
            """
        )
        immediately = await wait_snap(
            cdp,
            lambda s: s and ((s.get("users") and len(s.get("suggest") or []) == 0) or s.get("revising") or "暂时没有回复" in (s.get("cocoLast") or "")),
            timeout=8,
        )
        snap_019, api_019, wait_019 = await wait_revision(cdp, HAINAN_ID, before_019.get("updated") or "", timeout=180)
        after_plan = await fetch_planning(cdp, HAINAN_CONV)
        await cdp.screenshot("r1-after-suggest.png")
        user_ok = bool((immediately.get("users") or snap_019.get("users")))
        chips_gone = len(immediately.get("suggest") or []) == 0 and len(snap_019.get("suggest") or []) == 0
        same = api_019.get("id") == HAINAN_ID == after_plan.get("itinerary_id")
        changed = api_019.get("updated") != before_019.get("updated")
        coco_err = "暂时没有回复" in (snap_019.get("cocoLast") or "")
        out["acs"]["AC-019"] = {
            "result": "PASS" if clicked_sug.get("ok") and user_ok and chips_gone and same and changed and not coco_err else "FAIL",
            "clicked": clicked_sug,
            "wait_seconds": round(wait_019, 1),
            "chips_gone": chips_gone,
            "same_id": same,
            "updated_changed": changed,
            "cocoLast": (snap_019.get("cocoLast") or "")[:80],
            "users": [(u or "")[:20] for u in (snap_019.get("users") or [])[-2:]],
            "before_days": [(r.get("day"), r.get("n")) for r in (before_019.get("dayRows") or [])],
            "after_days": [(r.get("day"), r.get("n")) for r in (api_019.get("dayRows") or [])],
            "planning": after_plan,
            "suggest_before": sug.get("suggest"),
        }
        out["tech"]["src_hits"] = cdp.src_hits

    EVIDENCE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    result = asyncio.run(run())
    print(json.dumps(result.get("acs"), ensure_ascii=False, indent=2))
