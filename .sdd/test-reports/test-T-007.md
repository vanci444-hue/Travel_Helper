# T-007 Tester 报告

- 任务：T-007 三专员规划任务、运行日志与 SSE
- 总结果：**PASS（后端阶段 / Mock LLM+Plugin）**
- 时间：2026-09-13
- 环境：Travel_Helper 项目根 `.venv`；Python 3.14.2；pytest 9.1.1 + pytest-timeout
- 版本：仓库尚无 commit（`main` 无 HEAD）。本轮指纹=独立重跑命令与退出码，工作目录 `Projects_Repo/Travel_Helper`
- 门禁：`sdd_dispatch.py --running-task T-007` → `gate_phase=frontend_in_progress`（T-004），`execution_mode=automatic`。本任务 `type=backend`，不是 integration/delivery，已验收
- 依赖：T-005 / T-006 均为 `passed`
- 业务 AC：本任务 `acceptanceCriteria=[]`。**未**判 AC-001/009（T-009）、AC-003/004/024（T-010）、AC-007（T-011）、AC-008（T-012）通过
- Mock：专员 LLM 与高德 Plugin 均为脚本替身。**不是**上海→杭州真方案，不得当作 T-010/T-011 通过
- 密钥：测试只 patch 占位字段名；报告不含真实 `.env` 值
- 未起 8099：ASGI + 定向读代码足够覆盖本任务 technicalChecks

## 验证动作

1. 读取 T-007 全文、`project.json` specification=`default`、派发脚本、PRD REQ-002/004、tech-spec API-005/EXT-001/002/§四专员/§五 API-005/§六专员与高德、D-007/008/010，以及 default backend 规范清单。
2. Tester 独立重跑（项目根）：
   - `.venv/bin/python -m pytest backend/tests/test_planning.py backend/tests/test_sse.py --timeout=120` → **14 passed / 1.36s**
   - `.venv/bin/python -m pytest backend/tests --timeout=120` → **37 passed / 1.84s**
3. 测试库：`tmp_path` 隔离 SQLite，未清业务库。验收后业务库 `backend/data/Travel_Helper.db` 仍有表 `conversations/messages/planning_jobs/itineraries`，行数 4/0/0/0（与抽检前一致）。
4. 独立抽检（隔离库 + `_event_stream`，不用 httpx 长连）：截断「已截断」、断开 SSE 后 job 仍 `running`、规划中推 `planning.log`、终态 `itinerary.ready`、日志 id 顺序与 API-003 `activity_log` 一致。

## 技术检查

### TC-01 thinking 默认开关与模型名、无 dashscope — PASS

- `AppSettings` 默认：`manager_thinking_enabled=False`，`itinerary_thinking_enabled=True`，`deepseek_model=deepseek-flash`，`qwen_model=qwen-plus`（`backend/src/config/settings.py`；`.env.example` 同值）。
- 研究/预算 `thinking_enabled=False`；行程 `thinking_enabled=settings.itinerary_thinking_enabled` 且 `reasoning_effort=high`。
- 专员真实路径：千问 `enable_thinking=False` + `qwen_model`；DeepSeek `thinking.enabled/disabled` + `deepseek_model`；`httpx.AsyncClient(trust_env=False)`。
- `backend/src` 无 `import dashscope` / `from dashscope`；`pyproject.toml` 无 dashscope 依赖。`qwen_base_url` 默认含 dashscope 域名是兼容 HTTP 地址，不是 SDK。
- pytest：`test_settings_defaults_and_no_dashscope`。

### TC-02 Mock 研究成功后预算与行程并行，ready + itinerary_id — PASS（Mock）

- `execute_planning`：研究 `ok` 后 `asyncio.gather` 并行预算与行程。
- `test_mock_success_simple`：`ScriptedLLM.seen_parallel is True`；API-003 `planning.status=succeeded` 且有 `itinerary_id`；库中 `Itinerary.status=ready`；三专员均为 `succeeded`；Coco 只说去行程详情、不含「第 1 天」。
- 独立抽检同样 `succeeded` + 有 `itinerary_id`。
- **不是**真实上海→杭州方案。

### TC-03 SSE Accept / 逐步 log / 终态关闭 / heartbeat≈15s / 断开不取消 job — PASS（Mock）

- 路由 `GET /api/conversations/{id}/events`；`Accept: text/event-stream` 时 `Content-Type` 含 `text/event-stream`；未知会话 404 `NOT_FOUND`。
- `HEARTBEAT_SECONDS == 15`。心跳测试直调 `_event_stream`（间隔改为 0.05s）能收到 `heartbeat`；未用秒表测生产 15s 墙钟。
- `test_sse_streams_logs_then_ready`：有 `planning.updated` / `planning.log`，末事件 `itinerary.ready`。
- `test_sse_failed_then_closes`：末事件 `planning.failed`，`failure_reason` 非空且非「失败」。
- 独立抽检：规划中断开后 `planning.status` 仍为 `running`；再订阅后逐步出现 `planning.log`，末事件 `itinerary.ready`。实现上断开只 `unsubscribe`，后台 `_schedule` 任务继续。
- 用 httpx `client.stream` 等首个 SSE chunk 会卡住（见经验核对），故实时路径不靠 httpx 缓冲。

### TC-04 activity_log 顺序、80 条、clickable detail — PASS

- `MAX_ENTRIES=80`，溢出优先丢最早 `kind=thought`。`test_activity_log_keeps_eighty_and_clickable_detail`：70 thought + 15 tool → 80 条，「思考 0」已丢，tool 仍在。
- `clickable=true` 必有 `detail.heading` + `detail.body`；`truncate_body` 超 4000 截断并标「已截断」。独立抽检：5000 字 → 长度 3999 且以「已截断」结尾。
- 独立抽检：SSE `planning.log` id 去重后与 API-003 `activity_log` 顺序一致（4=4，`ORDER_MATCH True`）。
- 脱敏：去掉 polyline/key/url/http；标题禁模型品牌。

### TC-05 Mock 研究失败：Coco 含原因、无假行程 — PASS（Mock）

- 参数化 `destination_not_found` / `poi_empty` / `amap_unavailable`：
  - Coco 文案含对应 `reason`，且含「没法帮你出方案」
  - 不是只写「失败」
  - `planning.error_message` = 该 reason
  - `itinerary_id is None`，该会话无 `itineraries` 行
- 失败消息由 `assemble_coco_failure(reason)` 组装，不再调问诊模型。

### TC-06 预算超上限 Mock — PASS（Mock）

- `test_budget_over_cap`：`over_cap=true` 且 `total_amount > cap_amount`（Mock 合计 26000，上限来自问诊 2 万）。
- `budget.parse_result` 在 `total > cap_amount` 时强制 `over_cap=True`。

### TC-07 行程提示词密度 / 亲子 / 国内无护照签证 — PASS

- `itinerary_design.md` 含：轻松 1–2、适中 2–3、紧凑 3–4；亲子避坑；未交代交通按公交+步行并标明假设；「不要建议护照签证」。
- 后端 `_build_checklist` 为身份证/季节衣物/预约/公交步行，不含护照签证。成功用例 checklist 文本不含「护照」「签证」。
- 三份提示词均含 `json`。`test_itinerary_prompt_density`。

### TC-08 规划中再 POST 不开第二个 job — PASS

- `ManagerService.send_message`：`planning.status==running` 时直接 200，回复「专员还在做，完成后会放到行程里。」，不调经理、不 `start_planning_stub`。
- `start_planning_stub` 另有 `get_running` 防重入。
- `test_running_does_not_start_second_job`：第二次 POST 200 等待文案，`PlanningJob` 仍 1 条。

### TC-09 后续业务 AC 责任划分 — 记录（本任务不判通过）

| AC | 责任任务 | 本轮 |
| --- | --- | --- |
| AC-001 / AC-009 | T-009 | 未验、不通过 |
| AC-003 / AC-004 / AC-024 | T-010 | 未验、不通过 |
| AC-007 | T-011 | 未验、不通过 |
| AC-008 | T-012 | 未验、不通过 |

上海→杭州真方案、真实运行日志弹窗、真实超支 UI、亲子 vs 情侣对照均未跑。

## 经验候选核对

Tester 不写 `experience.md`。Developer 自验中已修好的两处：

1. **卡片无金额勿按天数常数重算预算**
   - 现象证据：开发中曾用 `len(days) * 2500` 触发重算，覆盖 `test_budget_over_cap`。
   - 已验证修复：当前 `planning.py` 仅当卡片存在 `amount`（`has_card_amount`）才按总额差 > 0.2 再跑一次预算；源码已无天数常数。Mock 成功行程卡片无金额；`test_budget_over_cap` 本轮通过。
   - 适用：并行后行程草稿无卡片金额时，不得用天数估算覆盖专员 JSON。
   - 根因（常数重算）有历史改动证据；本轮未再植入旧逻辑复现失败。

2. **SSE 不要靠 httpx 缓冲测实时 heartbeat**
   - 现象证据：现测 `test_sse_heartbeat_and_disconnect_keeps_job` 直调 `_event_stream`，短间隔能收到 `heartbeat`。Tester 另用 httpx `client.stream` 等首个 chunk，约 30s 无输出（与 Developer 所述缓冲超时一致）。
   - 已验证测试策略：心跳与增量推送用 `_event_stream` / FakeRequest，不把 httpx 缓冲当实时证明。
   - 适用：ASGI + httpx 测 SSE 心跳/逐步推送。
   - 根因「httpx 缓冲」已复现卡住，未拆 httpx 内部缓冲层；推广到其他客户端属未验证。

建议编排器按上述边界去重落盘。功能 PASS 不自动证明全部根因推断。

## 未验项

- 真实 DeepSeek / 千问 / 高德：未授权当成本任务必验；无 Key 调用。
- 上海→杭州真方案质量与等待秒数（D-007 40–90s）→ T-010。
- 浏览器 EventSource、运行日志弹窗、行程详情 UI → T-010/T-011。
- 本轮未短时启动 8099（ASGI 已覆盖 API-005）。
- 生产间隔 15s 的墙钟心跳（常量与短间隔注入已验）。
- 卡片带真实 `amount` 后的预算重算路径（仅验证「无金额不重算」）。

## 范围外

- `main.py` 仅注册 conversations / events / inspirations，无行程 CRUD，符合 T-008 未开工边界。
- 前端门禁仍 pending；Mock 页面与后端 API 配置仍待用户确认，不把本 Tester PASS 当用户放行。
