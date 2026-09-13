# T-001 Tester 报告（复验）

- 任务：T-001 前端工程、三栏外壳、规划前灵感与新建计划 Mock
- 总结果：**PASS（前端阶段 / Mock）**
- 时间：2026-09-13（复验，retry_count=1）
- 环境：Travel_Helper `frontend`；隔离预览 `http://127.0.0.1:5399/`（上轮 Tester 自启仍在，cwd 为本项目 frontend）；全部 Mock
- 浏览器：本机 Chrome Headless + CDP，视口 1440×900；实际打开工作台、decode/drawImage、截图像素采样、点选，不只看 HTTP 200
- 本轮改动范围：仅 `frontend/public/inspirations/{hangzhou,chengdu,dali}.svg`（去掉非法 aria-label）
- 业务 AC：本任务 `acceptanceCriteria=[]`。AC-012/013/014/020 归 T-009，AC-015 归 T-011，本轮不判这些 AC 通过
- 未改 `tasks.json` 状态；未写 `experience.md`

## 复验摘要

| 项 | 结果 | 说明 |
| --- | --- | --- |
| TC-03 右栏三张卡图 | **PASS** | 原 FAIL 已修复：Chrome 三图均可 decode，像素为渐变色，不是 broken、不是右栏底色 |
| 回归：点灵感卡 | **PASS** | 仍停 `/`，无详情、无弹层 |
| 回归：新建计划模态 | **PASS** | 字段齐全，「开始聊」可用；空提交后欢迎变为「已按表单进入对话，不会立刻出方案。」 |
| 回归：`[Mock]` | **PASS** | 侧栏底、灵感头、中栏欢迎各一处，共 3 处 |
| TC-01 `5199` 子项 | **BLOCKED** | 仍被 Customer_Service 占用；**不因此把整任务判 FAIL** |
| type-check / lint / build | 本轮未重跑 | Developer 只改静态 SVG，无依据怀疑 TS/组件被改 |

## 技术检查

### TC-01 5199 启动 + type-check/build + tsx/createRoot — 端口仍 BLOCKED，其余沿用上轮 PASS

| 子项 | 结果 | 证据 |
| --- | --- | --- |
| `127.0.0.1:5199` 启动 | **BLOCKED** | 复验亲自确认：`node` PID 49701 监听 5199，cwd=`Projects_Repo/Customer_Service/frontend`。`curl` 标题「智能客服系统」，不是 Xtrip。未停该进程。 |
| type-check / lint / build | 本轮未重跑 | 上轮退出码 0。定点修复仅为三份 SVG。 |
| JSX `.tsx` + `createRoot` | 本轮未重跑 | 上轮已核对 `main.tsx`。 |

隔离端口 `5399` 仍为 Travel_Helper（PID 50930，标题 Xtrip），用于本轮界面复验。未另启、未关 5199。

### TC-02 代理、baseURL、组件无直调 axios — 本轮未重跑（上轮 PASS）

改动不涉及 vite / axios。无新证据推翻上轮。

### TC-03 打开 `/` 三栏与灵感卡 — PASS（原 FAIL 已修复）

在 `http://127.0.0.1:5399/` 实测（1440×900）：

- 三张 `<img src="/inspirations/{hangzhou,chengdu,dali}.svg">`：`complete=true`，`naturalWidth=225` / `naturalHeight=150`，`decodeOk=true`，`broken=false`。
- `img.decode()` / `drawImage` 不再报 `HTMLImageElement is in the 'broken' state`。
- 卡图区域截图像素（非右栏底色 `rgb(26,26,26)`）：
  - 杭州：`rgb(123,143,152)` / `rgb(148,163,166)` / `rgb(165,169,162)`（青灰→米）
  - 成都：`rgb(90,118,95)` / `rgb(118,148,115)` / `rgb(155,164,123)`（绿→金）
  - 大理：`rgb(113,125,145)` / `rgb(140,147,161)` / `rgb(167,164,163)`（蓝灰→米）
- canvas 采样同样为对应渐变，不是整块 `#1a1a1a`。
- 文件 HTTP 200、`Content-Type: image/svg+xml`（与上轮相同，**200 不能单独证明可见**）。
- 磁盘与 5399 响应：三文件均无 `aria-label`，UTF-8 可解码，XML well-formed。
- 标题+描述可见：杭州 / 成都 / 大理；描述各一行（未超过两行）。右栏标题「灵感」，不是地图。
- 截图：`/tmp/xtrip-t001-shots/retest-home.png`（右栏三张渐变卡图清晰可见）。

### TC-04 点灵感卡不进详情、不新建行程 — PASS（回归抽检）

- 卡 `cursor: default`；全文无「查看详情」。
- 真实点击第一张卡图：URL 仍 `http://127.0.0.1:5399/`，无 dialog。

### TC-05 新建计划模态 — PASS（回归抽检）

点「新建计划」后出现模态：

- 去哪、何时、和谁·成人、和谁·儿童、预算、节奏（轻松/适中/紧凑）、目前已知的计划、「开始聊」。
- `startDisabled=false`。
- 全空点「开始聊」：弹层关闭；仍停 `/`；欢迎含「已按表单进入对话，不会立刻出方案。」；无「查看行程」。
- 截图：`/tmp/xtrip-t001-shots/retest-modal.png`、`retest-after-submit.png`。

### TC-06 空发送禁用、composer 贴底、视觉与控件态 — 本轮未重跑（上轮 PASS）

截图可见 composer 贴中栏底、暗色三栏。未重测 hover/focus/disabled 计算样式。

### TC-07 Mock 信封与 [Mock] — PASS（界面抽检）

- 界面可见 `[Mock]` 共 3 处：侧栏底、灵感头、中栏欢迎（提交前后均在）。
- Mock 信封字段本轮未重读源码（改动仅为 SVG）。

### TC-08 后续验收责任 — PASS（仅核对归属，不判业务 AC）

- T-009：AC-012 / AC-013 / AC-014 / AC-020。
- T-011：AC-015。
- 本任务不把这些 AC 标通过。

## 经验候选核对（不落盘）

Developer 候选：SVG 非法字节导致 Chrome 破图，HTTP 仍 200。

| 主张 | 核对 |
| --- | --- |
| 去掉非法 `aria-label` 后 Chrome 可渲染 | **已验证修复**。本轮三文件无该属性、良构；`decode`/`drawImage` 成功；截图与像素为渐变。 |
| HTTP 200 不等于图可见 | **已验证对照**。上轮与本轮文件均 200 + `image/svg+xml`；上轮 Chrome `broken` + 像素 `rgb(26,26,26)`，本轮可见。 |
| 根因就是 `aria-label` 非法字节（而非其他改动） | **强支持、未做旧文件 A/B**。Developer 声明只改这三文件；本 Tester 未重新打开损坏旧字节做对照，不把「唯一根因」写成已闭合实验。 |
| 其他浏览器 / 其他非法属性同样破图 | **推测 / 未验证**。本轮只测 Chrome。 |
| 外层 `img` 已有 `alt` 故可删 SVG aria-label | **未作为通过条件**。当前 `img.alt` 为空，标题在卡文案里；TC-03 看的是图是否可见。 |

建议编排器：可沉淀「SVG 含非良构/非法字节时 Chrome 破图但 HTTP 200」；适用条件限 Chrome + `image/svg+xml` 静态资源。Tester 不写 `experience.md`。

## 未验项

- Travel_Helper 在 **5199** 上的实际监听（客服项目占用，环境阻塞）。
- 本轮未重跑 `tsc` / eslint / build。
- 键盘 Tab 的 `:focus-visible`；`<1100` / `<768` 抽屉（T-004）。
- 对话气泡、运行日志、行程详情内容（允许占位）。
- 真实模型 / 高德 / 后端 8099（本任务 Mock）。

## 范围外

- 5199 被 Customer_Service 开发服务器占用：环境事实，不是本任务代码缺陷，也不单独构成总 FAIL。
- `img` 的 `alt` 为空：不影响本轮「图可见」判定。

## 截图（辅助，判定以 CDP decode + 像素为准）

`/tmp/xtrip-t001-shots/retest-home.png`、`retest-modal.png`、`retest-after-submit.png`
