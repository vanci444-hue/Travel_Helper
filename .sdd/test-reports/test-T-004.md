# T-004 Tester 报告

- 任务：T-004 前端 Mock 整体收口与用户门禁
- 总结果：**PASS（前端阶段 / Mock）**
- 时间：2026-09-13
- 类型：frontend / Mock；`acceptanceCriteria=[]`，只验 technicalChecks
- 业务 AC：**本轮不判通过**。后续责任：T-009（AC-001/002/009/011/012/013/014/020）、T-010（AC-003/004/024）、T-011（AC-005/006/007/015～023）、T-012（AC-008）
- 未改 `tasks.json` 状态；未改业务代码；未写 `experience.md`；**不宣布 user_gate 通过**

## 环境

- 工作目录：`Projects_Repo/Travel_Helper/frontend`
- 隔离 Vite：`http://127.0.0.1:5604/`，`VITE_USE_MOCK=true`，覆盖空的高德 Key（未读未写密钥）
- **未停 5199**：本机 `127.0.0.1:5199` 仍为 Travel_Helper（pid 65106），可能有用户在看
- Chrome：152.0.7977.84；`--user-data-dir=/tmp/xtrip-t004-chrome`；CDP `127.0.0.1:9604`；开页 `Target.createTarget` + `Target.attachToTarget({flatten:true})`，未用 `/json/new`
- 视口：1440×900、1099×800、767×800（`Emulation.setDeviceMetricsOverride`）
- type-check：`npm run type-check` 退出码 0（抽检，不代替浏览器）
- JSON：`.sdd/test-reports/t004-evidence-followup.json`
- 截图：`.sdd/test-reports/t004-shots/`

## 检查表

| ID | 场景 / 预期 | 方法 | 结果 |
| --- | --- | --- | --- |
| TC-01 | 浏览器按原型走通 #p-home / #p-chat / #p-create / #p-trips / #p-detail，均为 Mock 且可见 [Mock] | 浏览器点选 + 截图 | PASS（Mock） |
| TC-02 | 开聊后右栏地图槽；成功「查看行程」与列表进入同一 Mock id | 浏览器 + href/pathname | PASS（Mock） |
| TC-03 | 失败无「查看行程」；成功气泡/日志无整份按天报告 | 浏览器 | PASS（Mock） |
| TC-04 | 1440 三栏；&lt;1100 右栏覆盖层且有「地图/灵感」；&lt;768 左侧抽屉；composer 始终可见 | 浏览器改视口 | PASS（Mock） |
| TC-05 | 无登录墙、无旅行中/社区、无 PDF、主按钮非彩色；对照 ui-style 五 | 浏览器全文 + 计算色 | PASS（Mock） |
| TC-06 | 复用 T-001～T-003 稳定证据，只补跨页、窄屏与本任务改动 | 读既有报告 + 本轮补测 | PASS |
| TC-07 | 后续业务 AC → T-009～T-012，本轮不判通过 | 读 tasks.json | PASS（仅归属） |

额外必测：刷新 `/` 选中对话、刷新 `/trips` 选中行程；从行程页能回对话并开新建计划。均 PASS。

## 技术检查证据

### TC-01 原型五页 Mock 走通 — PASS（Mock）

| 锚点 | 实际 | 截图 |
| --- | --- | --- |
| #p-home | `/` 三栏：Xtrip、欢迎「和 Coco 规划一趟旅行」、右栏三张灵感图、composer 贴底 | `01-home-1440.png` |
| #p-chat | 用户气泡 + Coco + 专员行 + 可展开日志；右栏地图槽「地图未配置」 | `05-after-send-map.png` `06-success.png` |
| #p-create | 模态：去哪/何时/成人/儿童/预算/节奏/已知计划、「开始聊」 | `03-create-modal.png` |
| #p-trips | 仅一行杭州行程，无规划中 | `10-trips.png` |
| #p-detail | 网页报告：日期 chip、预算、清单、按天卡、侧聊与快捷建议 | `07-detail.png` |

界面多处可见 `[Mock]`（侧栏底、灵感/地图头、欢迎、详情标题）。`/` 上 `tripCount=0`，不叠行程列表。

### TC-02 跨页同一 itinerary id — PASS（Mock）

1. 点灵感卡后仍停 `/`，无详情路由、无弹层（随后在同一页发失败消息可证未跳走）。
2. 「新建计划」填杭州 5 天 / 2 成人 / 2 万 / 轻松 →「开始聊」回 `/`，欢迎含「已按表单进入对话，不会立刻出方案。」右栏仍是灵感。`04-after-create.png`
3. 发上海→杭州最小集：右栏标题变为「🗺️ 地图」。`05-after-send-map.png`
4. 成功后「查看行程」`href=/itineraries/itn_mock_01`。`06-success.png` / followup `viewTripHref`
5. `/trips` 点唯一一行，pathname=`/itineraries/itn_mock_01`。`11-detail-from-list.png`
6. 直开 `/itineraries/itn_01` 仍是同一份杭州 5 日报告（别名）。列表与对话入口统一 `itn_mock_01`。

### TC-03 失败 / 成功演示切换 — PASS（Mock）

- 失败：「从上海出发去火星玩 3 天…」→ Coco 说明国内地图找不到目的地；日志有失败步；**无「查看行程」**。`02-fail.png`
- 成功：Coco「方案好了，按天行程在详情页，不贴在对话里。」日志是工具步标题（地理编码/西湖/天气/公交），气泡内无按天卡片、无 `.itinerary-card`。`06-success.png`

### TC-04 视口 — PASS（Mock）

- 1440：侧栏 260 + 中栏 + 右栏 400 同时可见。
- 1099：右栏 `display:none`；右上角「灵感」；点开覆盖层见三张卡。开聊后按钮改为「地图」，点开为地图槽。composer `inView=true`。`14-1099-insp.png` `15-1099-insp-open.png` `16-1099-map-toggle.png` `17-1099-map-open.png`
- 767：侧栏隐藏，左上汉堡；点开 260px 抽屉。composer 仍在底部。`18-767-home.png` `19-767-drawer.png`

### TC-05 ui-style 五 / 禁项 — PASS（Mock）

- 导航只有「对话 / 行程 / 新建计划」，无旅行中、社区、探索。
- 正文扫描 `forbiddenHit=[]`（无 PDF/导出/旅行中/社区）。
- 「查看行程」计算色 `background: rgb(255, 255, 255)` / `color: rgb(14, 14, 14)`，不是绿/彩品牌键。
- 页脚「Demo · 无登录」，无登录表单。脚本曾因「无登录」子串误标 `hasLogin=true`，以截图为准，不记缺陷。
- 可见 `[Mock]`。

### 刷新与「困在行程页」

- 刷新 `/`：选中「对话」。`12-refresh-home.png`
- 刷新 `/trips`：选中「行程」。`13-refresh-trips.png`
- 详情点「对话」回 `/`；再点「新建计划」模态打开。`08-back-chat.png` `09-newplan-from-after-detail.png`
- 767 从 `/itineraries/itn_mock_01` 汉堡 → 对话 → 新建计划，`createOpen=true` 且 path=`/`。`20-767-detail.png` `21-767-newplan.png`

### TC-06 复用范围

沿用 T-001（灵感图/点卡不进详情/新建计划字段）、T-002（问诊/日志/失败原因/地图槽）、T-003（列表仅 ready、按天滚动、交通条、微详情/删点）。本轮只补跨页 id、窄屏抽屉、NavSync、`/` 不叠列表。

### TC-07 后续责任 — PASS（归属核对，不判业务 AC）

本任务 `acceptanceCriteria=[]`。全部业务 AC 留 T-009～T-012。**本轮不得、也未判这些 AC 通过。**

## 经验候选核对（不写 experience.md）

1. **跨页必须对齐同一 itinerary id** — **已验证（本页）**。对话入口与列表入口均为 `itn_mock_01`。适用：Mock 成功行程 + 别名 `itn_01`。未验证真实 API。
2. **`/` 不要叠行程列表** — **已验证（本页）**。Workbench 仅对话；`tripCount=0`。适用：当前三路由。未验证其他入口。

## 未验 / 范围外

- 真实模型、真实高德瓦片、5175/8003 用户门禁端口
- 控件五态伪类未逐项重扫（沿用 T-001）
- 删点未抽检（按 TC-06 复用 T-003；未为此重启隔离 Vite）
- 从详情回 `/` 后 Mock 对话线程不回放（hook 本地态）；刷新保会话由 T-009 真实验
- 未读取、未写出任何密钥

## 用户门禁（未通过）

Tester PASS ≠ 用户放行。`user_gate.status` 仍应由编排器保持 pending。

需交用户：验收 Mock，并在本地填写 DeepSeek / 百炼千问 / 高德 Web / 高德 JS 配置。

- 用户可能已在看：`http://127.0.0.1:5199/`
- 门禁约定端口：前端 5175 / 后端 8003（`VITE_BACKEND_PROXY_TARGET=http://localhost:8003`）
- Tester 隔离预览（验收后可关）：`http://127.0.0.1:5604/`
