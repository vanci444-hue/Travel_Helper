# T-002 Tester 报告

- 任务：T-002 前端对话、Coco 运行日志与右栏地图槽 Mock
- 总结果：**PASS（前端阶段 / Mock）**
- 时间：2026-09-13
- 环境：Travel_Helper `frontend`；全部 `VITE_USE_MOCK=true`
- 浏览器：本机 Chrome Headless + CDP，视口 1440×900；实际输入、点选、关弹窗，不只看 type-check
- 预览：隔离端口 `http://127.0.0.1:5402/`（主路径）与快照 `http://127.0.0.1:5403/`（失败路径 / 发送瞬间）。**未停 5199 Xtrip**。5402/5403 为 Tester 自启，验收后未再使用；若仍在监听可由编排器回收
- 本机 `.env` 已有 `VITE_AMAP_JS_KEY`（未读未写密钥值）。隔离进程清空该 Key，以便验收「地图未配置」。无真瓦片不否定本任务
- 业务 AC：本任务 `acceptanceCriteria=[]`。AC-001/002/009/011/013 → T-009；AC-003/004/024 → T-010。**本轮不判这些 AC 通过**
- 未改 `tasks.json` 状态；未改业务代码

## 检查表

| ID | 场景 | 预期 | 方法 | 结果 |
| --- | --- | --- | --- | --- |
| TC-01 | 发送出行消息 | 用户气泡立刻出现；Coco 三点加载；展示名 Coco | 浏览器 + MutationObserver 帧 | PASS |
| TC-02 | 「想出去玩」最小集未齐 | Coco 追问；无运行日志；三专员未执行 | 浏览器点选 | PASS |
| TC-03 | 最小集已齐 | ≥4 条中文逐步动作（含 tool/thought）；点「搜索景点 西湖」有细节、无密钥；关后仍在对话 | 浏览器点选 | PASS |
| TC-04 | 「火星」研究失败 | Coco 含原因；失败步可点；无「查看行程」、无假行程入口 | 浏览器点选 | PASS |
| TC-05 | Mock 成功 | Coco + 白底「查看行程」；日志可收起回看 | 浏览器点选 | PASS |
| TC-06 | 第一条出行消息后 | 右栏由灵感变地图槽；无 Key 居中「地图未配置」 | 浏览器（隔离无 Key） | PASS |
| TC-07 | 规划中再发送 | 「专员还在做」；仍一份日志。SSE：Mock EventSource polyfill，失败每 2s 拉 API-003；API-004 Axios 30s | 浏览器 + 定向读代码 | PASS |
| TC-08 | UI-002 / D-010 / #p-chat | 无密钥、模型品牌、整份按天方案；日志像活动记录 | 浏览器全文扫描 | PASS |
| TC-09 | 后续 AC 归属 | 只核对责任任务，不判业务通过 | 读 tasks.json | PASS（归属核对） |

## 技术检查证据

### TC-01 用户气泡立刻出现、Coco 三点、展示名 Coco — PASS（Mock）

在快照 `5403` 发送「想出去玩」前挂 MutationObserver：

1. `t≈709ms`：用户气泡「想出去玩」已在；`.coco-dots` 为 true；`.coco-name` = `Coco`；尚无 Coco 正文
2. `t≈715ms`：三点消失，Coco 正文出现，展示名仍为 `Coco`

失败路径同样先出现用户气泡 + 三点 + `Coco`，再出正文。页面未见 DeepSeek / Qwen / 千问 / ChatGPT。

### TC-02 最小集未齐 — PASS（Mock）

输入「想出去玩」后：

- Coco：「可以。还差几件事就能开工：……专员还不会上场。」
- `logCount=0`，无逐步步骤
- 过程视图：`目的地研究 · 未执行` / `预算专家 · 未执行` / `行程设计 · 未执行`
- 截图：`.sdd/test-reports/t002-shots/03-ask-done.png`

### TC-03 已齐：日志、细节弹窗 — PASS（Mock）

同会话再发「从上海出发，带老婆去杭州玩 5 天，预算 2 万，不要太赶」。展开日志最终 6 步：

- 查询杭州地理编码（tool）
- 搜索景点 西湖（tool）
- 思考 4s（thought）
- 读取杭州天气（tool）
- 估算分类预算（tool）
- 查询公交 灵隐寺 → 西湖（tool）

点「搜索景点 西湖」弹窗：`heading=搜索景点 西湖`，`body=找到：西湖、断桥、苏堤。开放时间与适合情侣轻松节奏已记下。` 无密钥。点「关闭」后 URL 仍 `/`，日志仍在。截图：`07-log-detail.png`。

### TC-04 研究失败 — PASS（Mock）

新会话发送「从上海出发去火星玩 3 天，一个人，预算 5000，轻松」：

- Coco：「这次没法帮你出方案。原因是：在国内地图里找不到这个目的地，没有可用的景点信息。……」
- 失败消息左侧 2px 白条（UI-002 例外）
- 日志：`查询目的地`、`目的地研究未完成`；点前者弹窗「地理编码无结果。国内地图找不到该地名。」
- `viewTrip=[]`，全文无「查看行程」
- 关弹窗后仍停在对话。截图：`14-fail.png`、`15-fail-detail.png`

### TC-05 成功出方案 — PASS（Mock）

- Coco：「方案好了，按天行程在详情页，不贴在对话里。」
- 白底主按钮「查看行程」→ `/itineraries/itn_mock_01`（T-003 详情未完成，不因此 FAIL）
- 点摘要收起：`aria-expanded=false`，步骤不可见；再点开 6 步仍在。截图：`08-success.png`、`09-log-folded.png`

### TC-06 右栏地图槽 — PASS（Mock）

发第一条「想出去玩」后：

- 右栏标题由「灵感」（3 张卡）变为「地图」
- 隔离无 Key：居中「地图未配置」，对话仍可用
- 本机 `.env` 有 Key 时该文案可以不出现，本轮用清空 Key 的隔离进程覆盖该分支

### TC-07 SSE / 超时 / 规划中再发送 — PASS（Mock）

浏览器：规划刚开工时再发「还要加一个博物馆」：

- Coco：「专员还在做，完成后会放到行程里。」
- `logCount=1`（摘要「规划中 · 专员开始工作」），未新开第二份日志
- 截图：`05-busy.png`

代码（抽检，非只靠源码判产品）：

- Mock：`PlanningMockEventSource`（EventSource polyfill）；真接口：`new EventSource(...)`
- `error` 后每 2000ms 拉 API-003，直到 `succeeded`/`failed`
- `sendMessage` 对 API-004 设 `{ timeout: 30000 }`

### TC-08 对照 UI-002 / D-010 / 原型 #p-chat — PASS（Mock）

- 中栏用户右浅灰气泡、Coco 左裸文 + 字母 C 圆、composer 贴底
- 规划日志插在 Coco 消息下，像活动记录不是专员气泡
- 页面与弹窗扫描无密钥、模型品牌、整份按天方案
- `[Mock]` 可见（侧栏 / 中栏 / 右栏）
- 布局与 `#p-chat` 三栏对话工作台一致

### TC-09 后续验收责任 — 仅核对，不判业务 AC

- T-009：AC-001 / AC-002 / AC-009 / AC-011 / AC-013
- T-010：AC-003 / AC-004 / AC-024

## 支持性检查

- `npm run type-check`（frontend）：退出码 0
- JSX `.tsx` + `createRoot`：沿用 T-001 工程，本轮未重验入口文件
- 5199：验收期间仍为 Xtrip（PID 65106），Tester 未占用、未杀死

## 未验项 / 范围外

- 真实模型、真实 SSE、真实高德瓦片、持久化：本任务 Mock，不声称真实服务通过
- AC-001/002/003/004/009/011/013/024：留给 T-009 / T-010
- 行程列表/详情（T-003 进行中）：「查看行程」已跳到 `/itineraries/itn_mock_01`；详情未完成不计入本任务 FAIL
- 验收中 T-003 热更新曾使 5402 的 `ItineraryDetailPage.tsx` 短暂 PARSE_ERROR；失败路径改在源码快照 5403 完成。对话主路径证据取自出错前的 5402 实测

## 判定

全部 technicalChecks 已实测通过，后续业务 AC 已指定责任任务。  
**PASS（前端阶段 / Mock）**。该 PASS 不证明完整业务功能通过。
