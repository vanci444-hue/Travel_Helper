# T-009 Tester 报告

- 任务：T-009 联调：工作台开聊、新建计划与问诊最小集
- 总结果：**PASS**（第 1 次返工复验；上轮 FAIL 事实保留于下文）
- 时间：2026-09-13
- 类型：integration；真链路 `VITE_USE_MOCK=false` + 本机后端 8099 + 真 DeepSeek
- 未改 `tasks.json`、未改业务代码、未写 `experience.md`
- AC-010：本期不验收

---

# 第 1 次返工复验（2026-09-13）

- 总结果：**PASS**
- 上轮 AC-009 FAIL 已复验通过；回归 AC-001/002/011/014 通过
- 未改 `tasks.json`、未改业务代码、未写 `experience.md`

## 本轮环境

- 工作目录：`Projects_Repo/Travel_Helper`
- 后端：Tester 自启 `127.0.0.1:8099`（`cd backend && PYTHONPATH=.. ../.venv/bin/python -m uvicorn src.main:app`）；日志「后端启动完成 | host=127.0.0.1 port=8099」
- 前端：Tester 自启 `http://127.0.0.1:5199/`，命令行 `VITE_USE_MOCK=false`，代理 `VITE_BACKEND_PROXY_TARGET=http://localhost:8099`
- Chrome：152.0.7977.84；`--user-data-dir=/tmp/xtrip-t009-retest-chrome`；CDP `127.0.0.1:9610`；开页 `Target.createTarget` + `Target.attachToTarget({flatten:true})`
- 视口：1440×900
- DeepSeek：本机 `.env` 已配置（只记项名）；问诊日志见「调用规划经理接口成功」
- 页面无 `[Mock]`
- 未 curl Vite 转换后的 `/src/*.ts`；证据来自页面 `fetch('/api/...')`、DOM 与后端日志
- JSON：`.sdd/test-reports/t009-retest1.json`、`.sdd/test-reports/t009-retest1-regress.json`
- 截图：`.sdd/test-reports/t009-shots/r1-*.png`

## 本轮检查表

| ID | 场景 / 预期 | 方法 | 结果 |
| --- | --- | --- | --- |
| AC-009 | 北京出发带小孩想看海 4 天 8 千别太赶 → 推荐国内城且专员 running | 浏览器新会话 + GET API-003 | **PASS** |
| AC-001 | 上海→杭州开工、不追问出境 | 锁过后定向复核 + GET API-003 | PASS |
| AC-002 | 「想出去玩」追问、专员 not_started | 定向复核 + GET API-003 | PASS |
| AC-011 | 满 2 轮仍缺出发地/天数则说明缺口、无假方案 | 定向复核 + GET API-003 | PASS |
| AC-014 | 预填后只追问出发地 | 定向复核 + GET API-003 | PASS |
| AC-012 | 规划前三栏灵感卡 | 抽检 | PASS |
| AC-020 | 点灵感不进详情 | 抽检 | PASS |
| AC-013 | 开聊后右栏地图 | 抽检 | PASS |
| 刷新 | 同一后端仍见该会话 | 抽检 | PASS |
| AC-010 | 出境 | — | 不验收 |

## 逐条 AC（本轮）

### AC-009 — PASS（上轮 FAIL 已修复）

**复现步骤：** 空工作台发送「从北京出发带小孩想看海 4 天预算 8 千别太赶」。

**Coco（摘要，非模型原文全文）：** 按北京出发、4 天、2 大 1 小学龄儿童、预算 8 千、轻松，推荐去青岛看海并开工。未追问出境/年龄，未要求点选城市。

**GET API-003 `conv_3721cbd075ceb250` 摘要：**

| 字段 | 值 |
| --- | --- |
| http | 200 |
| ready | true |
| missing | [] |
| origin | 北京 |
| dest | 青岛 |
| region | domestic |
| days | 4 |
| pace | relaxed |
| children | ["学龄儿童"] |
| followups | 0 |
| planning | running |
| itinerary_id | null |
| specialists | destination_research=running；其余 not_started |

界面专员行「目的地研究 · 进行中 · 正在查青岛点位与天气」。截图 `r1-03-ac009.png`。

### AC-001 — PASS

首轮紧接 AC-009 规划写库时，连续 `POST /api/conversations` 多次 `database is locked`，页面「新建对话失败」。按「同一疑点一次定向复核」，等锁松开后再测。

复测发送「从上海出发，带配偶去杭州 5 天，预算 2 万，不要太赶」。Coco 判定信息齐、未追问出境。GET API-003 `conv_96b97e167140072c`：`ready=true`，`origin=上海`，`dest=杭州`，`region=domestic`，`days=5`，`pace=relaxed`，`planning=running`，`destination_research=running`。截图 `r1-15-ac001.png`。

### AC-002 — PASS

「想出去玩」。Coco 追问出发地、天数、和谁、预算、节奏。GET API-003 `conv_6707794094d26b94`：`planning=idle`，三专员 `not_started`，`itinerary_id=null`，`ready=false`。截图 `r1-11-ac002.png`。

### AC-011 — PASS

三轮：「想和朋友去海边，预算一万，轻松一点」→「两个人，国内就行」→「你先看着办吧，出发地和玩几天我还没定」。

前两轮 Coco 已说明仍缺出发城市和玩几天。GET API-003 `conv_b97df6fc6714262b`：`followups=2`，`missing=["origin_city","duration_days"]`，`planning=idle`，无 `itinerary_id`，三专员 `not_started`，无按天文案。第三句用户消息已落库，随后 `POST .../messages` 500，界面「Coco 暂时没有回复」；不据此否定「满 2 轮说明缺口且无假方案」。截图 `r1-13-ac011.png`。

### AC-014 — PASS

新建计划预填杭州 / 5 天 / 2 成人 / 预算 20000 / 轻松，「开始聊」后只问出发城市。GET API-003 `conv_037e9bf9d4e08862`：`dest=杭州`，`days=5`，`pace=relaxed`，`missing=["origin_city"]`，未把节奏当缺口。截图 `r1-14-ac014.png`。

### AC-012 / AC-020 / AC-013 / 刷新 — PASS（抽检）

首页三栏、灵感杭州/成都/大理、字不叠图、无 `[Mock]`。点灵感仍停 `/`，行程数 0。开聊后右栏「地图」，`window.AMap` 与 canvas 存在。刷新后同一会话「想出去玩」仍在，GET API-003 200。

## 技术检查

| 项 | 结果 |
| --- | --- |
| 5199 打开且无 `[Mock]` | PASS |
| AC-001 GET API-003 `planning=running` 且 `destination_research=running` | PASS |
| AC-002 三专员 `not_started`、无 `itinerary_id` | PASS |
| AC-009 推荐国内城市且专员启动 | PASS |
| AC-011 满 2 轮仍缺出发地/时长，无按天方案 | PASS |
| AC-013 有 JS Key 时右栏为高德地图 | PASS（抽检） |
| 刷新后同一后端仍见该会话 | PASS |
| 缺 DeepSeek 则问诊 BLOCKED | 不适用 |

## 经验候选核对

### 不要用 curl 打 Vite 转换后的前端源码核环境变量

- **已验证：** 本轮只看 DOM 与 `/api`（页面 `fetch` + 后端日志）。未请求 Vite 转换后的 `/src/*.ts`，报告未写入 Key。
- **适用边界：** Chrome 152 + Vite 开发服。
- Tester 不写 `experience.md`。

### 规则层「看海→国内城 + 默认学龄儿童」挡住模型追问

- **已验证（功能+该条规则）：** 浏览器真链路同一失败句 → `dest=青岛`、`region=domestic`、`children=["学龄儿童"]`、`ready=true`、`missing=[]`、`planning=running`、`destination_research=running`；回复未追问出境/年龄。功能 PASS 与该规则同时被本轮 API-003 对上。
- **推测：** 本轮未单独关掉规则层去对照「仅模型」是否仍会追问；不能证明模型自己已学会不追问。
- **未验证：** 其他模糊画面（非看海）是否同样推荐城并开工。

### SQLite WAL + busy_timeout

- **已验证仍复现：** AC-009 开工后约 30s 内连续新建对话，后端多次 `sqlite3.OperationalError: database is locked`（`INSERT INTO conversations`）。WAL/busy_timeout 代码在 `backend/src/db/session.py` 存在，但未挡住规划写库期间的新建会话。
- **未验证：** 高压并发压测；锁的精确持有者（哪条规划写事务）。
- 功能 AC 不因此推翻；与上轮范围外项同类，本轮证实「WAL 未消掉该锁」。

## 范围外 / 残留

- 规划写库期间再 `POST /api/conversations` 仍会 SQLite locked → 500。演示中连续开新对话仍可能踩到。
- AC-011 第三句 `POST /messages` 曾 500（用户句已落库）；缺口说明已在前两轮完成。
- 部分会话右栏地图为空白网格；AC-013 以首句切换后出图为准。
- AC-010 出境未验。

## 未验项

- AC-010
- 专员跑完、运行日志、行程详情（T-010 / T-011）
- 用户门禁端口 5175 / 8003（本轮用 Agent 端口 5199 / 8099）
- SQLite 锁的高压复现与根因事务定位

---

# 上轮 FAIL（2026-09-13，保留）


## 环境

- 工作目录：`Projects_Repo/Travel_Helper`
- 后端：Tester 自启 `127.0.0.1:8099`（`cd backend && PYTHONPATH=.. ../.venv/bin/python -m uvicorn src.main:app`）；启动日志 `后端启动完成 | host=127.0.0.1 port=8099`
- 前端：Tester 自启 `http://127.0.0.1:5199/`，`VITE_USE_MOCK=false`，代理 `VITE_BACKEND_PROXY_TARGET=http://localhost:8099`
- Chrome：152.0.7977.84；`--user-data-dir=/tmp/xtrip-t009-chrome`；CDP `127.0.0.1:9610`；开页 `Target.createTarget` + `Target.attachToTarget({flatten:true})`，未用 `/json/new`
- 视口：1440×900
- DeepSeek：本机 `.env` 已配置（只记项名，不记值）；本轮问诊走真实模型，日志见「调用规划经理接口成功」
- 高德 JS Key：已配置；AC-013 右栏出图
- 页面无 `[Mock]`
- 未 curl Vite 转换后的 `/src/*.ts`；接口证据来自页面 `fetch('/api/...')` 与后端日志
- JSON：`.sdd/test-reports/t009-evidence.json`、`.sdd/test-reports/t009-ac009-recheck.json`
- 截图：`.sdd/test-reports/t009-shots/`

## 检查表

| ID | 场景 / 预期 | 方法 | 结果 |
| --- | --- | --- | --- |
| AC-012 | 规划前三栏；右栏灵感图+城市+理由，字不叠照片，不是地图 | 浏览器 + 几何 | PASS |
| AC-020 | 点灵感不进详情、不新建行程 | 点选 + GET `/api/itineraries` | PASS |
| AC-002 | 只说「想出去玩」→ 追问；三专员 `not_started`；无 `itinerary_id` | 浏览器 + GET API-003 | PASS |
| AC-013 | 开聊后右栏变地图；有 JS Key 应出图 | 浏览器点选 + 截图 | PASS |
| 刷新 | 同一后端仍能看到该会话（D-004） | 刷新 + GET API-003 | PASS |
| AC-001 | 上海出发带配偶去杭州 5 天、2 万、不要太赶 → 最小集齐、专员 running、不追问出境 | 浏览器 + GET API-003 | PASS |
| AC-009 | 北京出发带小孩想看海 4 天 8 千别太赶 → 推荐国内城市且专员启动 | 浏览器；失败后定向复测 1 次 | **FAIL** |
| AC-011 | 追问满 2 轮仍缺出发地或时长 → 说明缺口，无假方案 | 浏览器 + GET API-003 | PASS |
| AC-014 | 新建计划预填后只追问仍缺出发地，不重问已填节奏 | 浏览器填表 + GET API-003 | PASS |
| AC-010 | 出境 | — | 不验收 |

## 逐条 AC

### AC-012 — PASS

打开 `http://127.0.0.1:5199/`：左栏「对话 / 行程 / 新建计划」，中栏欢迎「和 Coco 规划一趟旅行」+ composer，右栏「灵感」。三张卡：杭州 / 成都 / 大理；每张有图（naturalWidth=1536）、城市名、推荐理由；caption 在照片下方，DOM 几何 `overlay=false`。右栏不是地图。无 `[Mock]`。截图 `01-home.png`。

### AC-020 — PASS

点第一张灵感卡后仍停 `/`，无「查看行程」，`GET /api/itineraries` 点击前后均为 0 条，未写入 `xtrip_conversation_id`。截图 `02-click-inspiration.png`。

### AC-002 — PASS

输入「想出去玩」并点发送。Coco 一轮追问出发地、国内/出境、天数、和谁、预算、节奏。GET API-003 `conv_436bbc7bcac7b7ed`：`planning=idle`，三专员均为 `not_started`，`itinerary_id=null`，`ready=false`。截图 `03-ac002.png`。

### AC-013 — PASS

同一条首句发出后，右栏标题变为「🗺️ 地图」，灵感卡消失。有 JS Key；`window.AMap` 与 `.amap-container` 存在；截图可见中国范围瓦片与「高德地图」字样。`mapCopy` 为空（非「地图未配置」）。截图 `03-ac002.png` / `04-map.png`。

### 刷新同一会话 — PASS

刷新后仍为 `conv_436bbc7bcac7b7ed`，用户气泡「想出去玩」与 Coco 追问仍在；GET API-003 200。截图 `05-refresh.png`。刷新后右栏地图曾出现空白网格，会话内容仍在；不据此否定 D-004。

### AC-001 — PASS

新开对话发送「从上海出发，带配偶去杭州 5 天，预算 2 万，不要太赶」。Coco：「信息齐了…我这就按这个方向给你排一版行程。」未追问国内还是出境。GET API-003 `conv_8d2ec6721f0734f0`：`ready=true`，`origin=上海`，`dest=杭州`，`region=domestic`，`days=5`，`pace=relaxed`，`planning=running`，`destination_research=running`，其余专员 `not_started`。界面专员行「目的地研究 · 进行中」。截图 `06-ac001.png`。

### AC-009 — FAIL

**预期：** 北京出发、带小孩、想看海、4 天、8 千、别太赶 → 经理推荐一个国内目的地并进入出计划（专员启动），不要求先点选城市。

**首次：** 紧接 AC-001 规划写库时 `POST /api/conversations` 500，页面「服务器内部错误」。后端：`sqlite3.OperationalError: database is locked`。按「同一疑点一次定向复核」再测。

**复测（独立新会话 `conv_f36856387d07db67`）：** 接口 201/200，DeepSeek 有回复。Coco：「请问孩子大概几岁？另外这趟想看海是想去国内的海边（比如青岛、厦门、三亚），还是想出境去某个国家？」GET API-003：`ready=false`，`dest=null`，`region=null`，`missing=["region","children_age_bands"]`，`planning=idle`，三专员均为 `not_started`。只举例城市，未选定并开工。截图 `11-ac009-recheck.png`。

**复现：** 空工作台发送「从北京出发带小孩想看海 4 天预算 8 千别太赶」→ 看 Coco 与专员行。  
**修复方向：** 国内模糊「看海」应按 D-001 推荐一座城并 `ready` 后开工；儿童年龄可写入假设或一轮内带过，不应挡住专员启动，也不应再追问出境。

### AC-011 — PASS

三轮用户：「想和朋友去海边，预算一万，轻松一点」→「两个人，国内就行」→「你先看着办吧，出发地和玩几天我还没定」。Coco 两轮追问后停住，说明仍缺出发城市和旅行天数。GET API-003 `conv_4251463d77bfde8c`：`followups=2`，`missing=["origin_city","duration_days"]`，`planning=idle`，无 `itinerary_id`，无按天文案。截图 `08-ac011.png`。

### AC-014 — PASS

点「新建计划」，预填去哪=杭州、何时=5 天、成人=2、儿童=0、预算=20000、节奏=轻松，点「开始聊」。前端自动发「请根据已填写的计划继续，不要重复已给的字段。」Coco：「还差一个出发城市…我就能把杭州 5 天轻松行程定下来啦。」GET API-003 `conv_67c9c78ab269efef`：`dest=杭州`，`days=5`，`pace=relaxed`，`missing=["origin_city"]`，未把节奏当缺口再问。脚本曾因回复里出现「轻松」误标 `askedPace`；以对话语义与 `missing_fields` 为准。截图 `09-new-plan.png` / `10-ac014.png`。

## 技术检查

| 项 | 结果 |
| --- | --- |
| 5199 打开且无 `[Mock]` | PASS |
| AC-001 GET API-003 `planning=running` 且 `destination_research=running` | PASS |
| AC-002 三专员 `not_started`、无 `itinerary_id` | PASS |
| AC-009 推荐国内城市且专员启动 | FAIL |
| AC-011 满 2 轮仍缺出发地/时长，无按天方案 | PASS |
| AC-013 有 JS Key 时右栏为高德地图 | PASS（首句后出瓦片） |
| 刷新后同一后端仍见该会话 | PASS |
| 缺 DeepSeek 则问诊 BLOCKED | 不适用（已配置且已调用） |

## 经验候选核对

编排器提醒：不要 curl 转换后的前端源码。

- **已验证：** 本轮只看 DOM 与 `/api`（页面 `fetch` + 后端日志）。未请求 Vite 转换后的 `/src/*.ts`，报告未写入 Key。
- **适用边界：** Chrome 152 + Vite 开发服；用 `/json` 或 curl 打模块 URL 会展开 `import.meta.env`。
- Tester 不写 `experience.md`，交编排器去重落盘。

## 范围外

- AC-001 开工后后台规划仍在跑（属 T-010）；本任务只验问诊就绪与专员 `running`。
- 规划写库期间再 `POST /api/conversations` 会 SQLite `database is locked` → 500。复测 AC-009 时锁已过，该项不作为 AC-009 失败原因，但演示中连续开新对话可能踩到。
- 部分后续会话右栏地图为空白网格（AC-001 / 刷新后）；AC-013 以首句切换后的出图为准，不因此否定切换。
- AC-010 出境未验。

## 未验项

- AC-010
- 专员跑完、运行日志、行程详情（T-010 / T-011）
- 用户门禁端口 5175 / 8003（本轮用 Agent 端口 5199 / 8099）
