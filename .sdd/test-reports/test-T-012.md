# T-012 Tester 验收报告

任务：联调亲子轻松与情侣紧凑行程可区分  
日期：2026-09-13  
总结果：**PASS**  
路径：真链路 `VITE_USE_MOCK=false`。页面无 `[Mock]`。未用 Mock 两份杭州模板换标题。未重跑杭州情侣 5 日主路径。未 curl Vite `/src/*.ts`。

## 环境

- 工作目录：`Projects_Repo/Travel_Helper`
- 后端：Tester 自启 `127.0.0.1:8099`（cwd=`.../Travel_Helper/backend`，`PYTHONPATH=.. ../.venv/bin/python -m uvicorn src.main:app`）。结束时已停。
- 前端：复用已在听的 `127.0.0.1:5199`（cwd=`.../Travel_Helper/frontend`，Vite）。Tester **未新拉起、未停止**（非本轮启动）。首页 HTTP 200；详情经 5199 `/api` 代理到 8099。
- Chrome：152.0.7977.84；`--user-data-dir=/tmp/xtrip-t012-chrome`；CDP `127.0.0.1:9615`；开页 `Target.createTarget({newWindow:true})` + `Target.attachToTarget({flatten:true})`；两窗并排（左 0 / 右 900，各 900×900）。**Tester 自启，结束时已停。**
- 核环境：只看 DOM 与 `/api`（5199 代理 8099）。未 curl Vite `/src/*.ts` 核 env/Key。
- 样本：Developer 已落库的成都 3 日真行程（不是杭州情侣 5 日）：
  - 亲子+轻松：`itn_d4d2b9088b2d5460` / `conv_6b51d34a70ee6fe9`
  - 情侣+紧凑：`itn_f173091eb7516ae0` / `conv_1741ca8d3d536ae4`
- 库内两份均 `status=ready`、`destination_city=成都`、`duration_days=3`、出发上海。未再新跑规划（各约 40–90s 的重跑未执行）。

机器证据：`.sdd/test-reports/t012-evidence.json`；截图 `.sdd/test-reports/t012-shots/`；脚本 `.sdd/test-reports/t012_cdp.py`。

## 检查表

| ID | 场景/输入 | 动作 | 预期 | 方法 | 结果 |
| --- | --- | --- | --- | --- | --- |
| AC-008 | 同城同天数，亲子轻松 vs 情侣紧凑 | 浏览器并排打开两份详情 | 疏密或活动类型可区分 | Chrome CDP 两窗 + DOM + `/api` | **PASS** |
| TC-01 | 两份详情 | 读 `itinerary_id` | 两个不同 id | 页面 path + GET `/api/itineraries/{id}` | PASS |
| TC-02 | 同上 | 对照目的地/天数/人群/节奏 | 城与天数相同，仅 companion/pace 不同 | API + 页头副标题 | PASS |
| TC-03 | 每天主要 attraction | 数点；看 intro 类型 | 轻松更疏或紧凑更密，或亲子避坑 vs 情侣节奏可观察 | DOM 卡片数 + API intro 关键词 | PASS |
| TC-04 | 两份 payload | 对照每天标题序列 | 不是同一 payload 只改 title/companion_type | 每天地点名集合比较 | PASS |
| TC-05 | Mock 排除 | 看 badge、id、城市 | 无 `[Mock]`；非 `itn_mock_01` / 杭州 5 日模板 | DOM + 磁盘 mock 对照 | PASS |

## 每天主要点摘要（不贴全文）

**亲子 + 轻松** `itn_d4d2b9088b2d5460`（页题「成都 3 日轻松游」，副标轻松 · 成都 3 天）

| 天 | 主要点数 | 点名（仅标题） | 可观察类型 |
| --- | --- | --- | --- |
| 1 | 2 | 熊猫基地、成都动物园 | 亲子；intro 含「避坑」；`suitable_for_children=true` |
| 2 | 2 | 成都博物馆、成都鸟语林 | 同上 |
| 3 | 2 | 交子公园、桂溪生态公园 | 公园慢游 + 避坑 |

**情侣 + 紧凑** `itn_f173091eb7516ae0`（页题「成都 3 日紧凑游」，副标紧凑 · 成都 3 天）

| 天 | 主要点数 | 点名（仅标题） | 可观察类型 |
| --- | --- | --- | --- |
| 1 | 4 | 交子公园、交子之环、金融城双子塔、双子塔夜景打卡点 | 夜景；intro 含「情侣节奏」；child=false |
| 2 | 4 | 人民公园、成都博物馆、太古里、安顺廊桥 | 散步/夜景 |
| 3 | 4 | 三家咖啡馆 + 南湖公园 | 咖啡馆节奏 |

重叠仅「交子公园」「成都博物馆」两处，其余点不同；每天 2 vs 4，不是换标题。

## 逐条 AC

### AC-008 PASS

前置：同一成都、同一 3 天。操作：Chrome 两窗并排打开  
`http://127.0.0.1:5199/itineraries/itn_d4d2b9088b2d5460` 与  
`http://127.0.0.1:5199/itineraries/itn_f173091eb7516ae0`。

可观察结果：

- 轻松每天 2 个主要 attraction（约 1–2）；紧凑每天 4 个（约 3–4）。未验精确分钟和精确个数。
- 活动类型可区分：熊猫/动物园/公园 + 亲子避坑 vs 夜景/咖啡馆 + 情侣节奏。
- 页头节奏文案不同（轻松 / 紧凑），无 `[Mock]`。
- 详情经 `127.0.0.1:5199/api/itineraries/<id>` 200，不是前端静态模板。

证据：`t012-shots/01-family-relaxed.png`、`02-couple-packed.png`、`03-family-day2.png`、`04-couple-day2.png`；`t012-evidence.json` → `acs.AC-008`、`tech`。

## 技术检查

- 两个不同 `itinerary_id`：PASS。
- 目的地与天数相同，仅 companion/pace 不同：成都 / 3 / `parent_child+relaxed` vs `couple+packed`：PASS。
- 疏密或类型可观察不同：PASS（密度与类型均满足）。
- 不是同一 payload 只改 title/companion_type：PASS。
- 可与 T-011 并行、未改杭州主路径行程：本轮只读这两份成都样本：PASS。

## 经验核对

1. **研究 8 轮若要求 12–16 个候选会用尽轮次不交 JSON**  
   本轮未新跑目的地研究/规划，两份已是 `ready` 成功结果。**未复现该失败，标未验证。**  
   功能 PASS **不**证明该根因。交编排器：勿因本轮 PASS 自动沉淀此条。

2. **不要用 curl 打 Vite `/src` 核环境变量**（已有条目）  
   本轮遵守：核 Mock 只看 DOM `[Mock]` 与 `/api` 200。CDP `Network` 会看到页面自身加载 Vite 模块（dev 正常），Tester 未对其做 curl、未展开 env、未记录 Key。

## 未验项

- 未从工作台重跑两份新规划，故未验证「研究 8 轮用尽不交 JSON」。
- 未验精确分钟、每天精确个数（契约不要求）。
- 未验地图模式、修订、高德 Key 值、费用明细。
- 未打开杭州情侣 5 日对照（任务要求不拿它当唯一样本，本轮未用它）。
- 5199 为验收前已有进程，Tester 未停。

## 收尾

已停：本轮 8099、Chrome 152（CDP 9615）。  
未停：验收前已在听的 5199。
