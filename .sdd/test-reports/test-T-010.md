# T-010 Tester 报告

- 任务：T-010 联调：专员规划、运行日志弹窗与失败原因
- 首轮总结果：**FAIL**（AC-004 停在问诊，见下文「AC-004 FAIL」）
- 第 1 次返工复验总结果：**PASS**
- 时间：2026-09-13
- 类型：integration；真链路 `VITE_USE_MOCK=false` + 本机后端 8099 + 真 DeepSeek + 真千问 Plus + 真高德 Web
- 未改 `tasks.json`、未改业务代码、未写 `experience.md`
- 页面无 `[Mock]`；未用 curl 打 Vite `/src/*.ts`；证据来自浏览器 DOM、页面 `fetch('/api/...')` 与后端访问日志

---

## 环境

- 工作目录：`Projects_Repo/Travel_Helper`
- 后端：Tester 自启 `127.0.0.1:8099`（`cd backend && PYTHONPATH=.. ../.venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8099`）；日志「后端启动完成 | host=127.0.0.1 port=8099」
- 前端：Tester 自启 `http://127.0.0.1:5199/`；`VITE_USE_MOCK=false`；代理 `VITE_BACKEND_PROXY_TARGET=http://localhost:8099`
- Chrome：152.0.7977.84；`--user-data-dir=/tmp/xtrip-t010-chrome`；CDP `127.0.0.1:9611`；开页 `Target.createTarget` + `Target.attachToTarget({flatten:true})`；视口 1440×900
- 外部服务：本机 `.env` 已配置 `deepseek_api_key` / `qwen_api_key` / `amap_web_key`（只记项名，不写值）
- JSON：`.sdd/test-reports/t010-evidence.json`
- 截图：`.sdd/test-reports/t010-shots/01-home.png`～`08-fail-modal.png`
- 复核脚本中途前端进程退出（`5199` 非正常结束）；后端仍可用。定向复核改走 API-003 读会话。

## 检查表

| ID | 场景 / 预期 | 方法 | 结果 |
| --- | --- | --- | --- |
| AC-003 | 上海→杭州 5 天齐集后出方案：三专员可见、日志≥2 条中文动作、Coco 汇总+查看行程、气泡无按天全文、`planning=succeeded` 且有 `itinerary_id` | 新会话浏览器发送 + GET API-003 | **PASS**（63.9s） |
| AC-024 | 点 clickable 步，弹窗 heading+body 有内容、无 Key/原始 HTTP；关闭后仍停在对话 | 浏览器点选 | **PASS** |
| AC-004 | 乱码地名：Coco 说明无法完成及原因；失败步可点开；无假行程；`itinerary_id` 空；`error_message` 与文案一致 | 新会话 + 一次追问复核 | **FAIL** |
| TC-01 | 秒表：开始出方案到终态；超时 180s 失败 | 状态等待 | 成功 63.9s；失败路径未开工，空等 180.7s |
| TC-02 | EventSource 断开后 2s 轮询仍能到终态 | 抽检 | 部分：真链路 hook 连上 SSE 后就会 `startPoll`；Network 可见持续 GET API-003。人为 close 包装未挂上（`__xtripES=0`），未单独证明「只靠掐断」 |
| TC-03 | 缺 Key 则三项 AC BLOCKED | 配置存在 | 不适用 |
| TC-04 | 连续写库无 `database is locked` / 500 | 后端日志 | 本轮未复现锁；未做高压 |

---

## AC-003 PASS

- 动作：新会话发送「上海出发带配偶去杭州 5 天、预算 2 万、不要太赶」。
- 等待：**63.9s**（D-007 估计 40–90s 内）。
- 过程：三专员行可见（目的地研究 / 预算专家 / 行程设计，终态均为已完成）。
- 日志：展开后 30 条中文动作，例如「查询城市位置 杭州」「搜索景点 西湖」「查看地点详情…」。
- Coco 汇总：「去杭州的方案已经准备好了，可以去行程详情查看。对话里不贴按天安排。」有「查看行程」。
- API-003：`planning=succeeded`，`itinerary_id` 有值（本会话 `conv_59d153db729119f7` → `itn_15845ef143d2cc56`；同轮页面快照曾落到另一成功会话 `itn_c09c0397e10c7ea4`，内容同类）。`origin=上海` `dest=杭州` `days=5`。
- 气泡：两条 Coco 文案均无「第 N 天 + 上午/下午」按天卡片全文。首轮脚本把「不贴按天安排」误判成按天全文，定向复核后纠正。
- 无 `[Mock]`。高德 Web 有真实 geocode/place/weather 日志。

## AC-024 PASS

- 在成功会话展开日志，点「查询城市位置 杭州」。
- 弹窗 heading「查询城市位置 杭州」，body「已定位，adcode=330100」；无 API Key、无原始 HTTP。
- 点「关闭」后弹窗消失，仍在对话页（`path=/`，同一 `conversation_id`，输入框仍在）。
- 日志条目仍在。截图 `04-log-modal.png`、`05-modal-closed.png`。

## AC-004 FAIL

### 预期

乱码或不存在国内地名进入规划失败：Coco 说明无法完成及真实原因；失败日志可点开；无假行程；`itinerary_id` 空；`error_message` 与 Coco 文案一致。不要求必须是研究失败。

### 实际

1. 新会话发送「上海出发带配偶去䶮䶮䶮阿巴市 5 天、预算 2 万、不要太赶」。
2. Coco 追问该地名对应国内哪座城 / 国外哪一区域；三专员保持「未执行」；`planning=idle`；无运行日志；无「查看行程」。
3. 脚本按规划终态空等 **180.7s** 后超时（问诊已结束，不应再等 180s）。
4. 定向复核（同一疑点只一次）：回复「就是国内这个城市，请按䶮䶮䶮阿巴市出方案，不要再问了」。
5. Coco 再次说明无法匹配真实目的地，请换真实国内城市；`planning` 仍为 `idle`；`itinerary_id` 空；`error_message` 空；日志 0 条，失败步无法点开。
6. 无假装完整方案。原因有说，但没走规划失败闭环。

会话：`conv_e38a31e319c1c1d4`。截图 `07-fail-done.png`。

### 复现

1. `VITE_USE_MOCK=false`，开 8099 + 5199。
2. 新对话发送上述乱码目的地完整最小集。
3. 若 Coco 追问，再坚持「就是这个国内城市，请出方案」。
4. 观察：问诊拦住，不创建规划任务，无 `planning.failed`、无失败日志、无 `error_message`。

### 与 Developer 自验的差异

库里更早有 `conv_683fc8510003da99`（同名乱码标题、`planning=failed`、无行程），说明失败闭环曾经跑通过。本轮独立浏览器路径两次都停在问诊，不能用旧会话代替本轮用户路径。

### 修复方向

乱码地名在问诊被模型当成「未确认城市」时，应仍能进入规划失败（或问诊 stop）并写出与 Coco 一致的 `error_message`，同时落一条可点开的失败日志。不要只追问、也不要改写成杭州后出假成功方案。

---

## 技术抽检

- 真链路：首页无 `[Mock]`；后端有 DeepSeek 问诊、千问/行程工具循环、高德 `infocode=10000`。
- EventSource：成功路径终态仍到达；2s 轮询请求存在。人为掐断包装未捕获已有 `EventSource`，不能声称「掐断后仅轮询」已证。
- 同库同时有其他会话在写（海南/杭州），本轮后端日志 **0** 次 `database is locked`、**0** 次 HTTP 500。
- 未看到 `json_object` / `response_format` 400。

---

## 经验候选核对

| 候选 | 本轮核对 |
| --- | --- |
| 不要用 curl 打 Vite 转换后的前端源码核环境变量 | **已遵守**。只看 DOM 与 `/api`。CDP Network 会看到页面自己加载的 Vite `/src` 模块，不是 Tester curl。 |
| SQLite WAL 消不掉规划写库时的 database is locked | **短事务未复现锁**（成功规划 + 失败问诊连续写库，无 500）。**未做高压**，不证明根因已消。 |
| 有 tools 时不要带 json_object | **未对照旧代码**；本轮无同类 400，标**推测/未验证**。功能 PASS 不自动证明该根因。 |

---

## 未验项

- 人为掐断 EventSource 后「仅靠 2s 轮询到达终态」未独立证成。
- 高压并发写库是否再锁：未验证。
- `json_object` 400：未复现、未对照旧代码。
- AC-004 的规划失败弹窗：因规划未开工，无法点失败步。
- 前端 5199 在复核中途退出，复核后半段未再点浏览器，改读 API-003。

---

## 范围外

- 同库出现其他会话把乱码问诊后改口去杭州并成功出方案（`conv_9bf91e553dc1c71d`）。不是本任务 AC，但说明乱码路径不稳定。
- `/api/health` 404，不影响本任务。

---

## 本轮自启资源

结束时停止 Tester 自启的 8099、5199、Chrome 152 CDP（9611）。

---

## 第 1 次返工复验（2026-09-13）

- 总结果：**PASS**
- 未改 `tasks.json`、未改业务代码、未写 `experience.md`
- 真链路：`VITE_USE_MOCK=false`；页面无 `[Mock]`
- 服务：8099/5199 为 Developer 残留且为本项目真链路，Tester 复用（未另起第二套后端，避免双写同一 SQLite）；Chrome 由 Tester 自启
- Chrome：152.0.7977.84；`--user-data-dir=/tmp/xtrip-t010-r1-chrome`；CDP `127.0.0.1:9612`；`Target.createTarget` + `Target.attachToTarget({flatten:true})`；视口 1440×900
- JSON：`.sdd/test-reports/t010-r1-evidence.json`、`.sdd/test-reports/t010-r1-modal.json`
- 截图：`.sdd/test-reports/t010-r1-shots/01-home.png`～`08-fail-modal-closed.png`

### 检查表

| ID | 场景 / 预期 | 方法 | 结果 |
| --- | --- | --- | --- |
| AC-004 | 原失败句进入规划并失败；Coco 说明无法完成及真实原因；失败步可点开；无假行程；`itinerary_id` 空；`error_message` 与文案一致；dest 不改杭州 | 新会话浏览器发送 + 状态等待 + 点失败步 | **PASS**（总等待 69.7s，自 `running` 68.1s） |
| AC-003 | 回归抽检：新会话上海→杭州，`planning` 为 running/succeeded 且 dest=杭州 | 新会话浏览器发送 + 状态等待到 running | **PASS**（1.5s 到 running；未等完整方案） |
| AC-024 | 本轮必须点开失败弹窗；成功路径沿用上轮 + 前端未改 | 本轮点「这一步没有完成」 | **PASS**（失败弹窗本轮点开） |
| TC-01 | 秒表：开始出方案到终态；超时 180s | 状态等待 | 失败 69.7s；成功回归只验到 running |
| TC-02 | EventSource 断开后 2s 轮询 | 未重做人为掐断 | 沿用上轮部分证据 |
| TC-03 | 缺 Key 则三项 BLOCKED | 配置存在 | 不适用 |
| TC-04 | 连续写库无 `database is locked` / 500 | 本轮未专扫日志 | 短事务未作为本轮阻断项 |

### AC-004 PASS（原 FAIL 已复验）

上轮事实保留：`conv_e38a31e319c1c1d4` 两次停在问诊 `planning=idle`，无失败日志、无 `error_message`。

本轮动作：新会话发送「上海出发带配偶去䶮䶮䶮阿巴市 5 天、预算 2 万、不要太赶」。未再追问「哪座城」。

- 1.5s：`planning=running`，`dest=䶮䶮䶮阿巴市`
- 69.7s：`planning=failed`（自 running 起 68.1s）
- Coco：「这次没法帮你出方案。原因是：…不存在于中国行政区划及主流旅游数据库…预算估算不可行。」
- API-003：`error_message` 与 Coco 原因段一致；`itinerary_id` 空；无「查看行程」；失败条有白条
- dest 仍为乱码市名，**没有改成杭州**
- 会话：`conv_5903a8247d5a2da1`
- 失败步「这一步没有完成」可点。首次脚本点在视口外（`y=-443`），同一疑点定向复核一次：滚入视口后点开。弹窗 heading「这一步没有完成」，body 与 `error_message` 同因；无 Key / 无原始 HTTP。关后仍在对话（`path=/`，同一 `conversation_id`，输入框仍在）。截图 `07-fail-modal.png`、`08-fail-modal-closed.png`

过程观察（不推翻 AC）：目的地研究记为已完成（3 处点位），行程设计内部把点位归到昌都贡觉一带，**预算专家失败**导致整单失败。用户侧没有假行程。这与「geocode 找不到立刻研究失败」不完全同一条实现路径，见经验核对。

### AC-003 PASS（回归抽检）

- 新会话发送「上海出发带配偶去杭州 5 天、预算 2 万、不要太赶」。
- 1.5s：`planning=running`，`dest=杭州`，`origin=上海`；目的地研究进行中「正在查杭州点位与天气」。
- 无 `[Mock]`。未等到完整 `succeeded`（本轮 AC-004 未破坏开工/目的地，按派发范围不强制再等约 60s）。
- 会话：`conv_4ead9056389b1de7`。截图 `05-ok-running.png`。

### AC-024 PASS

- 本轮在失败会话点「这一步没有完成」：heading+body 有内容、无密钥、关后仍停在对话。
- 成功路径点「查询城市位置 杭州」：上轮已 PASS，前端 `write_scope` 本轮未改，标明抽检范围为失败弹窗。

### 经验候选核对

| 候选 | 本轮核对 |
| --- | --- |
| 不要 curl Vite 转换后的 `/src` | **已遵守 / 已验证用法**。只看 DOM 与页面 `/api`。 |
| SQLite WAL 消不掉锁 | **短事务未复现锁**（失败规划 + 成功开工连续写库）。**未做高压**，不证明根因已消。 |
| 点名国内城（含乱码）且最小集齐须规则层 ready，让研究失败，不要只认城市名单、不要改口杭州 | **已验证**：最小集齐后 1.5s 即 `running`，未追问哪座城；`dest` 未改杭州。**部分未验证**：失败来自预算专家，研究记为 succeeded 且内部点位归到已知片区，不能把功能 PASS 写成「geocode 找不到立刻研究失败」已证实。 |

### 未验项

- 人为掐断 EventSource 后「仅靠 2s 轮询到达终态」仍未独立证成。
- 高压并发写库是否再锁：未验证。
- AC-003 完整 `succeeded` 与成功路径弹窗：本轮未重跑，沿用上轮 + 开工抽检。
- 「研究专员必须因 geocode 空结果立刻失败」：未作为 AC 否决项，实现路径与 Developer 自述不完全同证。

### 范围外

- 失败会话里行程设计摘要提到昌都贡觉一带真实 POI；用户未拿到行程，不计入 AC-004 失败。
- 复用的 8099 上 AC-003 会话在抽检后仍可能继续跑完，Tester 未等其终态。

### 本轮资源

结束时停止 Tester 自启的 Chrome 152 CDP（9612），并按派发要求停掉本轮使用的 8099、5199（含复用的残留进程）。
