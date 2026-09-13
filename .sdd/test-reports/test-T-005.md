# T-005 Tester 报告

- 任务：T-005 后端工程、会话持久化、灵感接口与 Coco 问诊
- 总结果：**PASS（后端阶段 / Mock HTTP）**
- 时间：2026-09-13
- 环境：Travel_Helper 项目根 `.venv`；`.venv/bin/python` = Python 3.14.2
- 门禁：`frontend_in_progress`（T-004）；本任务不是 integration/delivery，已验收
- 业务 AC：本任务 `acceptanceCriteria=[]`。AC-001/002/009/011/014 归 T-009，本轮不判这些 AC 通过
- 问诊：pytest 用 mock httpx；**不是**真实 DeepSeek。未对 8099 发真实模型请求
- 高德：本任务不测真实高德。报告不含任何 Key 值

## 验证动作

1. `sdd_dispatch.py`：`gate_phase=frontend_in_progress`，`tester_ready` 含 T-005。
2. Tester 重跑：
   - `.venv/bin/python -m pytest backend/tests/test_intake.py backend/tests/test_inspirations.py --timeout=120` → **12 passed**（0.58s）
   - `.venv/bin/python -m pytest backend/tests --timeout=120` → **23 passed**（0.68s，含 T-006）
3. Tester 自启 `127.0.0.1:8099`（`cd backend && PYTHONPATH=.. uvicorn src.main:app`），HTTP 验收后已停止。
4. 启动日志：`后端启动完成 | host=127.0.0.1 port=8099`；SQLite `backend/data/Travel_Helper.db` 表 `conversations` / `messages` / `planning_jobs` / `itineraries`。

## 技术检查

### TC-01 8099 启动 + CORS 5199/5175/8099/8003 + pytest 问诊 — PASS

- 8099：Uvicorn `Application startup complete`。
- OPTIONS `/api/conversations`：下列 Origin 均 200，且 `Access-Control-Allow-Origin` 回显同一 Origin：
  - `http://localhost:5199` / `http://127.0.0.1:5199`
  - `http://localhost:5175` / `http://127.0.0.1:5175`
  - `http://localhost:8099` / `http://127.0.0.1:8099`
  - `http://localhost:8003` / `http://127.0.0.1:8003`
- 带 `Origin: http://localhost:5199` 的空 POST 201，响应头 `Access-Control-Allow-Origin=http://localhost:5199`。
- pytest 问诊/灵感 12 passed。

### TC-02 API-001 空体 / 预填 / 非法 pace — PASS

8099 实测：

| 请求 | 实际 |
| --- | --- |
| POST `/api/conversations` 无 body | 201；`planning.status=idle`；三专员 `not_started`；`messages=[]` |
| 预填杭州 5 天 / couple / 2 万 / relaxed | 201；`missing_fields=["origin_city"]`；已填项不在 missing；`planning.status=idle` |
| `{"pace":"crazy"}` | 400；`VALIDATION_ERROR`；`error=节奏只能是轻松、适中或紧凑` |

同场景 pytest：`test_create_empty_body_idle`、`test_create_prefill_hangzhou_missing_only_unfilled`、`test_create_invalid_pace`。

### TC-03 API-010 国内灵感 + 前端静态路径 — PASS

GET `http://127.0.0.1:8099/api/inspirations`：200，3 条国内（杭州/成都/厦门），`image_url` 均为 `/inspirations/*.jpg`。

范围外残留：前端 `public/inspirations/` 当前是 `hangzhou.svg` / `chengdu.svg` / `dali.svg`，与后端 `.jpg` 文件名不完全对齐。属 T-009 AC-012 真实验收，不构成本任务 FAIL。

### TC-04 Mock 经理 ask — PASS

`test_mock_manager_ask_increments_followup`：API-004 200；`display_name=Coco`；三专员 `not_started`；`followup_rounds_used=1`。Mock httpx，`trust_env=False`。

### TC-05 Mock 经理 ready（上海→杭州）— PASS

`test_mock_manager_ready_starts_research`：回复不含「出境」；`intake.ready=true`；`origin_city=上海`；`destination_city=杭州`；`planning.status=running`；`destination_research=running`；`budget_expert=not_started`。

### TC-06 2 轮追问后强制 stop — PASS

`test_two_followups_force_stop`：两轮 ask 后模型仍假 ready；`intake.ready=false`；`planning.status=idle`；`itinerary_id=null`；GET API-003 仍无行程。

### TC-07 国内无城市有画面可推荐并 ready — PASS

`test_recommended_destination_can_ready`：mock `recommended_destination=青岛`；`destination_city=青岛`；`ready=true`；`planning.status=running`。

### TC-08 缺 deepseek_api_key — PASS

`test_missing_key_saves_user_message`：隔离库 + 清空 settings key；API-004 500；`error=未配置模型密钥`；用户消息已落库。未在真实 `.env` 上改密钥，也未打印密钥。

### TC-09 ConfigManager + .env.example — PASS

- `settings.py`：`manager.load(AppSettings, ENV_PATH, use_env=False)`。
- `test_config_manager_rejects_use_env`：`use_env=True` 抛 `ConfigurationError`；`use_env=False` 可加载。
- `backend/.env.example`：配置表字段均有占位；`deepseek_api_key` / `qwen_api_key` / `amap_web_key` 为空；无 `sk-` / Bearer 片段。
- `backend/.gitignore` 含 `.env`。
- `backend/src` 无 `os.getenv` / `dashscope` SDK（仅注释与百炼兼容 URL 默认值）。

### TC-10 后续 AC 归属 — 确认，不判通过

T-009 `acceptanceCriteria` 含 AC-001/002/009/011/014。本任务不把这些 AC 标为通过。Mock 问诊不是真实口吻验收。

### TC-11 stub 不跑三专员 — PASS

`backend/src/services/planning.py` 只写 `planning_jobs` 且 `destination_research=running`，`budget_expert` / `itinerary_design` 为 `not_started`，日志「stub，不跑三专员」。ready 测试与源码一致。三专员编排属 T-007。

## 未验项

- 真实 DeepSeek 口吻与 AC-001/002/009/011/014 → T-009
- 真实高德、三专员、SSE → T-006 已过 Mock；编排/日志 → T-007；真方案 → T-010/T-011
- 8099 上故意清空真实 Key 再打 API-004（用隔离 pytest 代替，避免改本机 `.env`）
- 灵感图文件是否真能在浏览器显示 → T-009 AC-012

## 范围外发现

后端灵感 `image_url` 为 `/inspirations/{hangzhou,chengdu,xiamen}.jpg`，前端静态目录现为 svg 且城市集合不同。交编排器决定是否记到 T-009。
