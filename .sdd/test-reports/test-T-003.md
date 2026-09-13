# T-003 Tester 复验报告

- 任务：T-003 前端行程列表与网页行程详情 Mock
- 总结果：**PASS（前端阶段 / Mock）**
- 类型：frontend / Mock；`acceptanceCriteria=[]`，只验 technicalChecks
- 时间：2026-09-13（定点修复复验，retry_count=1）
- 预览（本轮隔离）：`http://127.0.0.1:5511`（验收后由 Tester 关闭）
- 未占用、未杀死：`127.0.0.1:5199` 上原有 Xtrip（pid 65106）

## 环境

- 工作目录：`Projects_Repo/Travel_Helper/frontend`
- 新起隔离 Vite：`VITE_USE_MOCK=true`，覆盖空的 `VITE_AMAP_JS_KEY` / `VITE_AMAP_SECURITY_JS_CODE`，`--port 5511 --strictPort`
- 未复用上次 5499（避免删点模块内存残留）
- Chrome：152.0.7977.84；独立 `--user-data-dir=/tmp/xtrip-t003-retest-chrome`，CDP `127.0.0.1:9566`，`--remote-allow-origins=*`
- 开页：CDP `Target.createTarget` + `Target.attachToTarget({flatten:true})`，未使用 `/json/new`
- 点选：`Input.dispatchMouseEvent` 真实按下/抬起
- 滚动：Chrome 152 无 `Input.dispatchMouseWheel`；在实开页面上改 `.detail-report-body.scrollTop` 并 `dispatchEvent('scroll')`，chip 随观察带变化。不是只读 CSS。
- type-check：`npm run type-check` 退出码 0
- 未读取、未写出密钥

## 检查表

| ID | 预期 | 结果 | 证据 |
| --- | --- | --- | --- |
| TC-01a | 列表仅 ready；有杭州行程；无规划中 | PASS | `/trips` 一行：`杭州 5 日轻松游` / `杭州 · 5 天 · 轻松 · 今天`；`bodyHasPlanning=false`。`t003-retest-list.png` |
| TC-01b | 空态文案 | 本轮未重跑 | 派发要求回归抽检列表仅 ready；空态页与本次滚动修复无关 |
| TC-02 | 网页报告无 PDF | PASS | 5 个日期 chip；按钮/正文无 PDF/导出。`t003-retest2-chip3.png` |
| TC-03 | 点第 3 天高亮；从顶滚到第 3 天区域第 3 天高亮；滚到最大第 5 天高亮，不停第 2 天 | **PASS** | 见下节 |
| TC-04 | 卡间交通条仍在 | PASS | `公交约 25 分钟`、`步行约 12 分钟（估算）`、`公交约 40 分钟` |
| TC-05 | 微详情 | 本轮未重跑 | 改动未触及开/关微详情 |
| TC-06 | 删点 | 本轮未重跑 | 按派发不重跑删点；未怀疑被改 |
| TC-07 | 快捷建议 | 本轮未重跑点击 | 详情截图仍见 4 条建议 chip；未再点发出 |
| TC-08 | composer 不被中栏滚动挤掉 | PASS（抽检） | 滚到第 3 天/最大后右栏 composer 仍在底部。`t003-retest2-scroll-max.png` |
| TC-09 | 不把后续 AC 判过 | PASS | 本轮仍不判定 AC-015～023、AC-005/006/007、AC-008 |

本轮 **不** 判定 AC-005～008、AC-015～023 通过。后续责任仍是 AC-015～023 与 AC-005/006/007 → T-011；AC-008 → T-012。

## TC-03 复验（原 FAIL）

**上次失败：** 中栏 `maxScroll` 仅 548.5，第 3/5 天无法进入上 45% 观察带，chip 停在第 2 天。

**本轮预期：** 点「第 3 天」高亮；从顶部滚到第 3 天区域时第 3 天高亮；滚到最大时最后一天（第 5 天）高亮，不能再停在第 2 天。

**实际（干净重开 `/itineraries/itn_01`，不先点回第 1 天）：**

1. 点「第 3 天」：`selected=第 3 天`，`scrollTop=807`，第 3 天 `rel≈0`、观察带可见面积 220.8（大于第 4 天 57）。`t003-retest2-chip3.png`
2. 重新打开详情，从 `scrollTop=0` 逐步下滚（每次 +220）：

| 步 | scrollTop | 观察带最大可见 | chip |
| --- | ---: | --- | --- |
| top | 0 | （预算/清单，天卡片还在带下） | 第 1 天 |
| 1 | 220 | 第 1 天 205 | 第 1 天 |
| 2 | 440 | 第 2 天 180 > 第 1 天 98 | 第 2 天 |
| 3 | 660 | 第 3 天 155 > 第 2 天 123 | **第 3 天** |
| 4 | 880 | 第 3 天 148 > 第 4 天 108 | 第 3 天 |
| 5 | 1100 | 第 5 天 108 > 第 4 天 60 | 第 5 天 |
| 6 最大 | 1315.5 | 五天都在带上方 | **第 5 天**（不是第 2 天） |

3. 再滚到第 3 天附近：chip 回到第 3 天。`t003-retest2-around-day3.png`
4. 底部 spacer：`endSpace=672 === clientHeight`；`maxScroll=1315`（上次失败时 548.5）。

**复现（现已通过）：** 新起 Vite → 打开 `/itineraries/itn_01` → 点第 3 天；再重开同一页从顶滚到第 3 天区域、再滚到最大。

JSON：`.sdd/test-reports/t003-retest2.json` 的 `scrollPath` / `afterChip3` / `atMax`。截图：`t003-retest2-chip3.png`、`t003-retest2-scroll-day3.png`、`t003-retest2-scroll-max.png`。

首轮脚本曾在点第 3 天后立刻点第 1 天复位，smooth `scrollIntoView` 未结束就下滚，chip 被点选锁在第 1 天。该路径作废，以重开后的滚动路径为准。

## 经验候选核对

Tester 不写 `experience.md`。交编排器去重落盘。

1. **短尾卡片 + 负 rootMargin 需要一屏底部空间，并按观察带可见面积选节** — **已验证（本页）**。`endSpace` 等于一屏 672px；滚到最大后第 5 天仍高亮。step 3 时第 3 天带内可见 155 > 第 2 天 123，chip 切到第 3 天。适用：中栏独立滚动 + `rootMargin: 0 0 -55% 0` + 末几天卡片短于观察带。未验证推广到其他页或其他 margin。
2. **删点模块内存残留** — 本轮未再删点。上次已验证；本轮用新端口 5511 规避。
3. **独立端口降并行冲突** — **已验证（本轮边界）**。5511 + 独立 Chrome 用户目录；5199 上原 Xtrip 一直在听。

功能 PASS 不自动等于全部根因推断；上表第 1 条有滚动数字与选中 chip 对应，可沉淀。第 2 条本轮未复测。

## 未验 / 范围外

- 真实高德 JS、真实行程接口、真实模型
- AC-005～008、AC-015～023（T-011 / T-012）
- 空态、微详情开关、删点、建议点击（按派发不重跑）
- 窄屏抽屉、1440 以外视口
- hover/focus 五态未逐态指针悬停

## 产物

- 本文件
- `t003-retest.json`（含列表/交通/无 PDF 抽检；其中 TC-03 滚动段作废）
- `t003-retest2.json`（TC-03 有效滚动路径）
- 截图：`t003-retest-list.png`，`t003-retest2-*.png`
