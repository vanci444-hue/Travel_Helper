#!/usr/bin/env python3
"""T-011 AC-021 一次定向复核：点 chip + 按页面观察带滚到第 3 天。"""

from __future__ import annotations

import asyncio
import json

import websockets

from t011_cdp import (
    BASE,
    Cdp,
    DELETE_ID,
    click_day_chip,
    click_trip_by_id,
    open_trips,
    wait_detail,
)

BAND_JS = r"""
(() => {
  const root = document.querySelector('.detail-report-body');
  const chips = [...document.querySelectorAll('.day-chip')].map((n) => ({
    text: (n.textContent || '').trim(),
    selected: n.classList.contains('is-selected') || n.getAttribute('aria-selected') === 'true',
  }));
  if (!root) return { ok:false, chips };
  const sections = [...root.querySelectorAll('[data-day]')];
  const rootRect = root.getBoundingClientRect();
  const bandBottom = rootRect.top + rootRect.height * 0.45;
  const candidates = sections.map((section) => {
    const rect = section.getBoundingClientRect();
    const visible = Math.max(0, Math.min(rect.bottom, bandBottom) - Math.max(rect.top, rootRect.top));
    return { day: Number(section.getAttribute('data-day')), visible, top: rect.top - rootRect.top, height: rect.height };
  });
  const inBand = candidates.filter((item) => item.day && item.visible > 0).sort((a, b) => b.visible - a.visible || a.top - b.top);
  const selected = (chips.find((c) => c.selected) || {}).text || '';
  return {
    ok: true,
    scrollTop: root.scrollTop,
    clientHeight: root.clientHeight,
    selected,
    expected: inBand[0] ? inBand[0].day : null,
    candidates,
    chips,
  };
})()
"""


async def run() -> dict:
    import urllib.request

    version = json.loads(urllib.request.urlopen("http://127.0.0.1:9613/json/version").read())
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
        await click_trip_by_id(cdp, DELETE_ID)
        await wait_detail(cdp, DELETE_ID)
        await click_day_chip(cdp, "第 1 天")
        await asyncio.sleep(0.7)
        start = await cdp.eval(BAND_JS)

        clicked3 = await click_day_chip(cdp, "第 3 天")
        await asyncio.sleep(0.9)
        after_click3 = await cdp.eval(BAND_JS)
        await cdp.screenshot("r3-chip-day3.png")

        await click_day_chip(cdp, "第 1 天")
        await asyncio.sleep(0.7)

        # 逐步下滚，直到观察带期望天为 3
        steps = []
        matched = None
        for i in range(16):
            await cdp.eval(
                """
                (() => {
                  const root = document.querySelector('.detail-report-body');
                  if (!root) return false;
                  root.scrollTop += Math.round(root.clientHeight * 0.28);
                  root.dispatchEvent(new Event('scroll'));
                  return true;
                })()
                """
            )
            await asyncio.sleep(0.45)
            info = await cdp.eval(BAND_JS)
            steps.append({
                "i": i,
                "scrollTop": info.get("scrollTop"),
                "expected": info.get("expected"),
                "selected": info.get("selected"),
            })
            if info.get("expected") == 3:
                matched = info
                break
        await cdp.screenshot("r3-scroll-day3.png")
        if matched is None:
            matched = steps[-1] if steps else {}

        await click_day_chip(cdp, "第 1 天")
        await asyncio.sleep(0.8)
        after_d1 = await cdp.eval(BAND_JS)
        await cdp.screenshot("r3-chip-day1.png")

        click3_ok = after_click3.get("selected") == "第 3 天"
        scroll_ok = (matched.get("selected") == "第 3 天" if isinstance(matched, dict) else False) or (
            isinstance(matched, dict) and matched.get("expected") == 3 and matched.get("selected") == "第 3 天"
        )
        if isinstance(matched, dict) and "selected" in matched:
            scroll_ok = matched.get("selected") == "第 3 天" and matched.get("expected") == 3
        else:
            scroll_ok = False
            for step in steps:
                if step.get("expected") == 3 and step.get("selected") == "第 3 天":
                    scroll_ok = True
                    matched = step
                    break
        chip1_ok = after_d1.get("selected") == "第 1 天"
        result = "PASS" if click3_ok and scroll_ok and chip1_ok else "FAIL"
        out = {
            "result": result,
            "start": start,
            "after_click3": after_click3,
            "scroll_steps": steps,
            "matched": matched,
            "after_d1": after_d1,
            "click3_ok": click3_ok,
            "scroll_ok": scroll_ok,
            "chip1_ok": chip1_ok,
        }
        path = __import__("pathlib").Path(__file__).resolve().parent / "t011-recheck-021-e6e7.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))
