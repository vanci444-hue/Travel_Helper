# T-008 Tester 报告

- 任务：T-008 行程报告读写、逐项改与对话修订
- 总结果：**PASS（后端阶段 / fixture + Mock LLM）**
- 时间：2026-09-13
- 环境：Travel_Helper 项目根 `.venv`；`.venv/bin/python` = Python 3.14.2；pytest 9.1.1 + pytest-timeout 2.4.0
- 版本：仓库 HEAD `ec75f8f`。本轮指纹=独立重跑命令与退出码；工作目录 `Projects_Repo/Travel_Helper`
- 门禁：`sdd_dispatch.py --running-task T-008` → `gate_phase=frontend_in_progress`（T-004），`execution_mode=automatic`。本任务 `type=backend`，不是 integration/delivery，已验收
- 依赖：T-005 `passed`
- 业务 AC：本任务 `acceptanceCriteria=[]`。**未**判 AC-005/006/007/015～023 通过；这些归 T-011。**未**宣称页面闭环
- Mock：行程为 fixture 入库；修订 LLM 为 httpx 替身；高德 Web Key 在测试中置空，补腿走 `estimate`。**不是**真实高德路线，也**不是**真实 DeepSeek 修订
- 密钥：测试只 patch 占位字段名；报告不含真实 `.env` 值
- 浏览器：无。pytest + 定向读代码

## 验证动作

1. 读取 T-008 全文、`project.json` specification=`default`、派发脚本、PRD REQ-003/006、tech-spec API-006～009 / 规划经理修订 / §五 API-004 与 API-008/009、D-006，以及 default backend 规范清单。
2. Tester 独立重跑（项目根）：
   - `.venv/bin/python -m pytest backend/tests/test_itineraries.py backend/tests/test_revision.py --timeout=120` → **12 passed / 0.67s**
   - `.venv/bin/python -m pytest backend/tests --timeout=120` → **49 passed / 1.67s**
3. 测试库：`tmp_path` 隔离 SQLite，未清业务库。
4. 定向读：`itineraries.py`、`revision.py`、`manager.py` `_revise`、`manager_revise.md`、`main.py` `include_router(itineraries_router)`。

## 检查表

| ID | 场景/输入 | 动作 | 预期 | 方法 | 结果 |
| --- | --- | --- | --- | --- | --- |
| TC-01 | ready + draft 各一条；未知 id | GET 列表；007/008/009 | 列表仅 ready；404 中文 | pytest + 读 `list_ready` / `get_ready` | PASS |
| TC-02 | 超支 fixture 杭州 5 日 | GET 详情 | 填满 ItineraryPublic；over_cap；国内清单无护照签证 | pytest + `to_public` | PASS（fixture） |
| TC-03 | PATCH start_time；DELETE 第 2 天卡 | 改/删 | 整份报告；点从 cards 与当天坐标消失；planning 仍 succeeded | pytest + `_save`/`to_public` | PASS（fixture；补腿 estimate） |
| TC-04 | Mock LLM revise operations / ask | API-004 | 同一 itinerary_id；无法映射 reply 说明且行程不变 | pytest + `_revise` | PASS（Mock） |
| TC-05 | 换目的地 / 改成 10 天 | API-004 | suggest_new_plan 不改卡片 | pytest + `is_major_replan` | PASS（Mock） |
| TC-06 | 后续 AC | — | 不判 AC-005/006/007/015～023 通过 | 范围核对 | PASS（未宣称） |

## 技术检查

### TC-01 API-006 只含 ready；未知 id 007/008/009 404 中文 — PASS

- `ItineraryService.list_ready`：`where(Itinerary.status == "ready")`，`updated_at` 降序，`page`/`page_size` 走 `paginated_response`。
- `get_ready`：无行或 `status != ready` → `NotFoundError("找不到这份行程")`。
- pytest `test_list_only_ready`：`itn_ready` 在列表，`itn_draft` 不在；列表项含 `id/title/destination_city/duration_days/pace/updated_at/conversation_id`。
- pytest `test_unknown_id_404_chinese`：
  - GET `/api/itineraries/itn_missing` → 404，`error_code=NOT_FOUND`，`error=找不到这份行程`
  - PATCH `/api/itineraries/itn_missing/cards/card_01` → 同上
  - DELETE `/api/itineraries/itn_missing/cards/card_01` → 同上
  - DELETE 已知行程未知卡 → `error=找不到这张卡片`
- 错误信封：`error_json` 用 `success=false` + HTTP 404，中文可读。

### TC-02 API-007 填满 ItineraryPublic；超支 over_cap；国内清单无护照签证 — PASS（fixture）

- `ItineraryPublic` 字段与 tech-spec 示例对齐：`id/conversation_id/title/destination_city/origin_city/duration_days/pace/companion_type/assumptions/days/budget/checklist/map_center/quick_suggestions/status/created_at/updated_at`。
- `days[].cards` 与 `legs`（`mode/duration_min/distance_m/summary/source`）由 `to_public` 规范化。
- pytest `test_detail_fills_public_over_cap_no_passport`：`over_cap is True` 且 `total_amount(16200) > cap_amount(5000)`；checklist 拼接不含「护照」「签证」；有 `quick_suggestions`。
- 读路径 `_domestic_checklist` 会丢掉含「护照」「签证」的项。本轮样例本身无这两项；过滤逻辑已存在。
- **不是**真实规划产出的超支行程。

### TC-03 PATCH/DELETE 整份报告；点消失；planning 仍 succeeded — PASS（fixture）

- PATCH/DELETE 均 `success_response(data=ItineraryPublic)`，不是局部补丁。
- `test_patch_start_time_keeps_planning_succeeded`：`card_d1_01.start_time` 变为 `11:30`；API-003 `planning.status=succeeded`，三专员均为 `succeeded`。
- `test_delete_card_removes_point_keeps_planning`：第 2 天 `card_d2_01` 不在 `cards`；当天剩余卡坐标集合不含 `(120.116, 30.22)`；`planning.status=succeeded` 且 `itinerary_id` 不变。
- `_revise` / 逐项改路径不把 planning 改回 `running`，不新开三专员。
- 无 Key 时删相邻卡：`test_delete_recalculates_legs_as_estimate_without_key` → 剩余腿 `source=estimate`，`summary` 含「约」。**未**验真实高德 `source=amap`。
- 删卡后 `budget.total_amount` 仍为 `16200`（卡片无 `amount`，不按天数常数重算）。

### TC-04 修订 Mock：operations 同一 itinerary_id；无法映射行程不变 — PASS（Mock）

- 已有 ready 行程且非「按表单继续」：`manager.handle_message` 走 `_revise`，提示词 `manager_revise.md`。
- `test_revise_remove_card_same_itinerary`：Mock `remove_card card_d2_01` → 同一 `itinerary_id`，专员仍 `succeeded`，第 2 天无该卡。
- `test_revise_set_day_pace_same_itinerary`：Mock `set_day_pace day_index=3 max_major_points=1` → 第 3 天只剩 `card_d3_01`。
- `test_unmapped_keeps_itinerary`：Mock `action=ask`、空 operations；reply 含「卡片」或「排松」；卡片 id 集合不变；planning 仍 `succeeded`。
- 单元：`apply_operations` / `apply_set_day_pace` 与上同口径。
- LLM 为 `_FakeClient`，`deepseek_api_key` 仅为测试占位。**不是**真实 DeepSeek 修订。

### TC-05 suggest_new_plan 不改卡片 — PASS（Mock）

- 后端硬闸：`is_major_replan` 命中「换目的地|改去|…」或天数差 ≥3 → 即使模型给 `revise`+operations 也不落卡。
- `test_suggest_new_plan_does_not_change_cards`：「换个目的地改去成都」+ 模型企图删卡 → reply 含「新建计划」或「换目的地」，卡片不变。
- `test_suggest_new_plan_action_from_model`：模型 `suggest_new_plan` 且带 `remove_card` → 卡片仍不变。
- `_revise` 在 `forced_new_plan or action == "suggest_new_plan"` 时直接回消息，不调用 `apply_revision`。

### TC-06 后续验收归属 — PASS（未宣称业务 AC）

- 任务原文：`后续验收：AC-005/006/007/015～023→T-011`。
- 本轮只验 API/fixture/Mock。不把列表/详情/改删/修订当作页面闭环。

## 规范抽检（default）

- 路由：`/api/itineraries`，`main.py` 只 `include_router(itineraries_router)`。
- 信封：成功 `success_response` / 分页 `paginated_response`；错误 `error_json` + 中文。
- 分层：路由调 `ItineraryService`，不直接返回 ORM。
- 命名：`ItineraryPublic` / `CardPatch` / `itineraries.py`。

## 经验候选核对（不落盘）

- 候选：「卡片无金额不按天数常数重算预算」。
- 证据：`maybe_recompute_budget` 仅当至少一张卡有 `amount` 才改 `total_amount`；fixture 卡无金额；DELETE 后合计仍 16200。
- 结论：已验证。适用：逐项改/删/对话修订且卡片无金额字段。未验证：卡片带金额时是否按卡汇总。

## 未验项

- 真实高德补腿（`source=amap`）；本轮无 Key 走 estimate。
- 真实 DeepSeek 修订口吻与 operations 质量。
- 页面闭环与 AC-005/006/007/015～023（T-011）。
- 浏览器、用户验收端口、真实 `.env` 密钥是否可用（本轮不读密钥值）。

## 范围外

- 无已证实的本任务缺陷。
- 灵感图 jpg/svg 不一致属 T-009 已知项，不计入 T-008。
