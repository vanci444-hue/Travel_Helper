# Xtrip 七层技术方案

- 项目：Travel_Helper（产品显示名 **Xtrip**）
- status: Confirmed
- specification: default
- 关联：已确认 `docs/PRD.md`（REQ-001～REQ-006、AC-001～AC-024；AC-010 本期不验收）、`docs/decisions.md` D-001～D-010
- 技术取舍：D-007 已确认选 A。D-008、D-009、D-010 已确认。

---

## 一、用户要完成什么

客户打开无登录工作台，只对接规划经理 **Coco**（对话气泡固定显示此名）：多轮对话收齐开工最小集后，Coco 分派目的地研究、预算专家、行程设计，汇总成一份可改的旅行前报告（按天卡片、预算、地图、行前清单）。刷新后本机这份 Demo 数据仍在。本期必验与演示均为国内（例：上海出发去杭州 5 天）。研究或任一专员失败时，Coco 必须说明无法完成的**具体原因**，不交假方案（D-008）。

| 需求 | 用户结果（PRD） | 本方案入口 |
| --- | --- | --- |
| REQ-001 / AC-001,002,009,011 | Coco 收敛最小集；未齐则追问且专员不上场；国内模糊描述可推荐目的地；2 轮后仍缺则不出假计划 | 工作台 `/` 中栏；API-001、API-004 |
| REQ-002 / AC-003,004,024 | 齐了才分派三名专员；过程为可展开运行日志，步骤可点开细节；失败则 **Coco 说明无法完成的原因** 且不交假方案 | 对话区日志；API-003、API-004、API-005 |
| REQ-003 / AC-005,006,007 | 同一份报告含按天行程、预算、地图、行前清单；逐项改不重跑专员；超预算能看出 | 行程详情 `/itineraries/:id`；API-007～009 |
| REQ-004 / AC-008 | 人群/节奏不同则排法可区分（轻松约 1–2 点、适中 2–3、紧凑 3–4） | 专员提示词与行程生成；API-004 规划任务 |
| REQ-005 / AC-012,013,014,015,020 | 三栏：规划前右灵感（不可点进）、开聊后右地图；新建计划预填；行程列表 | `/`；API-001、API-006、API-010；前端高德 JS（EXT-004） |
| REQ-006 / AC-016～019,021～023 | 日期点选与滚动同步；卡片间交通；微详情；逐项改 + 侧边对话改 + 快捷建议 | `/itineraries/:id`；API-007～009、API-004 |

完整数据链路：

```text
打开工作台 → API-010 灵感（右栏）
新建计划或直接聊 → API-001 建会话（可带预填）
发消息 → API-004 Coco / 规划经理（同步 JSON 决策）
  ├ 未齐：追问入库，专员保持 not_started
  ├ 2 轮仍缺：说明缺口，不建规划任务
  └ 已齐：回复「开始出方案」，后台跑规划任务
      1) 目的地研究（工具循环 + 高德）
      2) 研究成功后并行：预算专家、行程设计（行程再调高德路线）
      3) API-005 SSE 推专员状态与 `planning.log` 运行日志；失败则插入 Coco 消息（含原因）且不写行程
      4) 成功：写入 itineraries；Coco 在对话里告知可查看；左侧可进网页详情（非 PDF）
详情逐项改 → API-008/009（不重跑专员；邻接交通可补一次高德）
详情对话改/快捷建议 → API-004（修订模式，改同一份报告）
```

风格文档 `docs/ui-style.md` 已确认（2026-09-13）。可交互演示见 `docs/prototypes/index.html`。界面以 PRD「界面约定」+ 风格文档为准。本层不重写业务规则（最小集、节奏、国内默认交通假设见 PRD 与 D-001、D-006）。

本期不做：登录、出境必验、旅行中/后、订票、账单、相册、强制跳转导航 App、单独「数据分析与计算」专员、导出 PDF、把整份报告只作为对话长文。报告主体在行程详情页 `/itineraries/:id`。

---

## 二、前后端怎么分工，接口怎么拆

### 分工与栈

| 侧 | 职责 | 选型（default 规范） |
| --- | --- | --- |
| 前端 | 三栏工作台、对话、灵感/地图切换、新建计划表单、行程列表与详情（日期滚动、卡片、微详情、快捷建议） | React + TypeScript + Vite + React Router；状态用 Hooks/Context；Axios 经 `services/` |
| 后端 | 会话/行程持久化、规划经理编排、三名专员、高德工具、SSE | Python 3.11+ FastAPI + PyCore；SQLAlchemy asyncio + aiosqlite |
| 外部 | 大模型、国内地点/天气/路线、地图展示 | DeepSeek Chat Completions；百炼千问 OpenAI 兼容 HTTP（禁止 `dashscope` SDK）；高德 Web 服务 + JS API 2.0 |

- 这是 **AI Agent 应用**：Router → Service → PluginRegistry → Plugin（高德工具）→ 再回模型。规划经理用结构化 JSON 决策，不把「分派专员」交给模型自由工具，避免未齐最小集时误开工。
- 后端基础 URL：开发经 Vite 代理，前端只请求 `/api`。Agent 后端 `8099`、前端 `5199`；用户验收后端 `8003`、前端 `5175`。CORS 同时允许这四个 origin。
- 无登录、无鉴权依赖。演示环境接口公开，不得部署到公网不经保护。
- 变更与问诊走 REST；规划长任务 **202 语义落在会话状态上**：API-004 同步返回经理回复（最小集已齐时 `planning.status=running`），专员进度用 API-005 SSE（失败则每 2s GET API-003 兜底）。
- 问诊回复非流式，等完整 JSON 再展示。规划过程用 SSE 事件，不把 60s+ 的专员工作堵在一次 HTTP 里。
- Axios：默认 15s；API-004 30s（只等规划经理，不等三名专员）。SSE 用 `EventSource`，不走 Axios。
- 资源词从 PRD 名词实体推导：对话 → `conversations`；行程 → `itineraries`；灵感 → `inspirations`。发消息、进度流是会话上的动作，不另造资源。

统一 JSON 信封见第三层 `ApiEnvelope`。以下成功示例省略重复的 `timestamp` / `request_id` / `metadata`，联调时必须带齐。SSE 与高德/模型原始协议不走该信封。

### 接口索引

| ID | Method / URL | 作用 | 需求 |
| --- | --- | --- | --- |
| API-001 | POST /api/conversations | 新建对话；可带新建计划预填 | REQ-001,005 AC-001,014 |
| API-002 | GET /api/conversations | 左侧对话列表 | REQ-005 |
| API-003 | GET /api/conversations/{conversation_id} | 消息、问诊槽、专员状态、运行日志 | REQ-001,002 AC-002,003,011,024 |
| API-004 | POST /api/conversations/{conversation_id}/messages | 发给 Coco（问诊或修订） | REQ-001,002,006 AC-001,002,009,011,018,019 |
| API-005 | GET /api/conversations/{conversation_id}/events | SSE：专员进度、运行日志、完成/失败 | REQ-002 AC-003,004,024 |
| API-006 | GET /api/itineraries | 左侧行程列表 | REQ-005 AC-015 |
| API-007 | GET /api/itineraries/{itinerary_id} | 报告全文（天、卡片、交通、预算、清单、地图点、快捷建议） | REQ-003,006 AC-005,007,016,021,022,023 |
| API-008 | PATCH /api/itineraries/{itinerary_id}/cards/{card_id} | 逐项改一张卡片 | REQ-003,006 AC-006,017 |
| API-009 | DELETE /api/itineraries/{itinerary_id}/cards/{card_id} | 删除一张卡片 | REQ-003,006 AC-006,017 |
| API-010 | GET /api/inspirations | 规划前右栏国内灵感 | REQ-005 AC-012,020 |
| EXT-001 | POST {deepseek_base_url}/chat/completions | DeepSeek | 规划经理、行程设计（D-007 选 A） |
| EXT-002 | POST {qwen_base_url}/chat/completions | 百炼千问 | 目的地研究、预算专家（D-007 选 A） |
| EXT-003 | GET restapi.amap.com 多路径 | 高德 Web 服务 | 地理编码、POI、天气、步行/公交 |
| EXT-004 | 浏览器加载 JS API 2.0 | 高德地图展示 | 右栏/详情地图；不经本后端转发瓦片 |

---

### API-001 新建对话

| 项目 | 内容 |
| --- | --- |
| 关联需求 | REQ-001、REQ-005；AC-001,014 |
| Method / URL | POST /api/conversations |
| 请求 | `Content-Type: application/json`。`ConversationCreate`：见第三层。全部可空；空体即「直接开聊」。预填写入问诊槽，不立刻开专员。 |
| 成功响应 | **201** `data: ConversationPublic`。`intake` 反映已填项；`planning.status=idle`；`map_hint` 可空；`messages=[]`（若有预填，后端可插入一条系统摘要消息，见第五层）。 |
| 失败响应 | 400 `VALIDATION_ERROR`；500 `INTERNAL_ERROR`。 |

成功示例：

```json
{
  "success": true,
  "data": {
    "id": "conv_01",
    "title": "杭州 5 天",
    "intake": {
      "origin_city": null,
      "region": "domestic",
      "destination_text": "杭州",
      "destination_city": "杭州",
      "duration_days": 5,
      "date_start": null,
      "date_end": null,
      "date_month": null,
      "companion_type": "couple",
      "adults": 2,
      "children": 0,
      "children_age_bands": [],
      "budget_amount_cny": 20000,
      "budget_tier": null,
      "budget_includes": "domestic_transport_and_local",
      "pace": "relaxed",
      "wish_text": "目前已知的计划：轻松吃吃走走",
      "missing_fields": ["origin_city"],
      "followup_rounds_used": 0,
      "ready": false
    },
    "map_hint": null,
    "planning": {
      "status": "idle",
      "specialists": [
        {"role": "destination_research", "status": "not_started", "summary": null},
        {"role": "budget_expert", "status": "not_started", "summary": null},
        {"role": "itinerary_design", "status": "not_started", "summary": null}
      ],
      "activity_log": [],
      "error_message": null,
      "itinerary_id": null
    },
    "messages": [],
    "created_at": "2026-09-13T05:20:00Z",
    "updated_at": "2026-09-13T05:20:00Z"
  },
  "error": null,
  "error_code": null,
  "message": "ok"
}
```

失败示例：`pace` 不是三档之一 → 400 `VALIDATION_ERROR`，`error` 为中文「节奏只能是轻松、适中或紧凑」。

---

### API-002 对话列表

| 项目 | 内容 |
| --- | --- |
| 关联需求 | REQ-005 |
| Method / URL | GET /api/conversations |
| 请求 | 无请求体。Query：`page` int 默认 1；`page_size` int 默认 20，最大 50。 |
| 成功响应 | **200** `paginated_response`，`data: ConversationListItem[]`（无消息正文）。 |
| 失败响应 | 400 `VALIDATION_ERROR`；500 `INTERNAL_ERROR`。 |

`ConversationListItem`：`id`、`title`、`updated_at`、`planning.status`、`itinerary_id`（可空）。

---

### API-003 对话详情

| 项目 | 内容 |
| --- | --- |
| 关联需求 | REQ-001、REQ-002；AC-002,003,011 |
| Method / URL | GET /api/conversations/{conversation_id} |
| 请求 | 路径参数 `conversation_id` string。无请求体。 |
| 成功响应 | **200** `data: ConversationPublic`（含 `messages`、`intake`、`planning`）。 |
| 失败响应 | 404 `NOT_FOUND`；500 `INTERNAL_ERROR`。 |

失败示例：未知 id → 404，`error`「找不到这场对话」。

---

### API-004 发送消息给规划经理

| 项目 | 内容 |
| --- | --- |
| 关联需求 | REQ-001,002,006；AC-001,002,009,011,018,019 |
| Method / URL | POST /api/conversations/{conversation_id}/messages |
| 请求 | `MessageCreate`：`content` string 必填，1–2000 字。快捷建议把建议原文放进 `content`，不另开字段。 |
| 成功响应 | **200** `data: MessageTurnPublic`：`user_message`、`assistant_message`、`intake`、`planning`。**`planning.status=running` 只表示已开工，不表示方案已完成。** |
| 失败响应 | 400 `VALIDATION_ERROR`；404 `NOT_FOUND`；409 `CONFLICT`（规划任务进行中又发一条会触发开工的消息时，见第五层：本接口仍 200 并回固定说明，不 409 打断聊天；仅当会话已失败且客户端误当作可重派时用 409 无此路径）；500 `INTERNAL_ERROR`（经理模型同步失败，用户消息已落库，可重试）。 |

成功示例（最小集已齐，专员启动）：

```json
{
  "success": true,
  "data": {
    "user_message": {
      "id": "msg_02",
      "role": "user",
      "content": "从上海出发，带老婆去杭州玩 5 天，预算 2 万，不要太赶",
      "created_at": "2026-09-13T05:21:00Z"
    },
    "assistant_message": {
      "id": "msg_03",
      "role": "assistant",
      "display_name": "Coco",
      "content": "信息齐了：上海出发、杭州 5 天、情侣、2 万、轻松节奏。我这边让专员出一版，你可以在过程里看到进度。",
      "created_at": "2026-09-13T05:21:04Z"
    },
    "intake": {
      "origin_city": "上海",
      "region": "domestic",
      "destination_city": "杭州",
      "duration_days": 5,
      "companion_type": "couple",
      "adults": 2,
      "children": 0,
      "budget_amount_cny": 20000,
      "pace": "relaxed",
      "wish_text": "不要太赶",
      "missing_fields": [],
      "followup_rounds_used": 0,
      "ready": true
    },
    "planning": {
      "status": "running",
      "specialists": [
        {"role": "destination_research", "status": "running", "summary": "正在查杭州点位与天气"},
        {"role": "budget_expert", "status": "not_started", "summary": null},
        {"role": "itinerary_design", "status": "not_started", "summary": null}
      ],
      "activity_log": [],
      "error_message": null,
      "itinerary_id": null
    }
  },
  "error": null,
  "error_code": null,
  "message": "ok"
}
```

关键失败示例：经理模型超时 → 500 `INTERNAL_ERROR`，`error`「Coco 暂时没有回复，请再试一次」；用户那条已保存，重试不会丢原文（第五、六层）。

---

### API-005 规划进度 SSE

| 项目 | 内容 |
| --- | --- |
| 关联需求 | REQ-002；AC-003,004 |
| Method / URL | GET /api/conversations/{conversation_id}/events |
| 请求 | 无请求体。`Accept: text/event-stream`。 |
| 成功响应 | **200** `Content-Type: text/event-stream`。事件名：`planning.updated`、`planning.log`、`itinerary.ready`、`planning.failed`、`heartbeat`。`data` 为 JSON 对象（不是 `ApiEnvelope`）。连接在 `itinerary.ready` 或 `planning.failed` 后由服务端关闭。 |
| 失败响应 | 404 普通 JSON 信封 `NOT_FOUND`；无法升级为 SSE 时 500。 |

事件示例：

```
event: planning.updated
data: {"status":"running","specialists":[{"role":"destination_research","status":"succeeded","summary":"已收集西湖、灵隐等点位"},{"role":"budget_expert","status":"running","summary":null},{"role":"itinerary_design","status":"running","summary":null}],"itinerary_id":null}

event: planning.log
data: {"entry":{"id":"log_03","kind":"tool","specialist":"destination_research","title":"搜索景点 西湖","clickable":true,"detail":{"heading":"搜索景点 西湖","body":"找到：西湖、断桥、苏堤。开放时间与适合情侣轻松节奏已记下。"},"created_at":"2026-09-13T05:21:20Z"}}

event: itinerary.ready
data: {"status":"succeeded","itinerary_id":"itn_01","specialists":[{"role":"destination_research","status":"succeeded","summary":"点位与天气可用"},{"role":"budget_expert","status":"succeeded","summary":"合计约 1.6 万，未超 2 万"},{"role":"itinerary_design","status":"succeeded","summary":"5 天轻松行程"}]}

event: planning.failed
data: {"status":"failed","itinerary_id":null,"failure_reason":"在国内地图里找不到这个目的地，没有可用的景点信息","coco_message_id":"msg_04","specialists":[{"role":"destination_research","status":"failed","summary":"地理编码无结果"},{"role":"budget_expert","status":"not_started","summary":null},{"role":"itinerary_design","status":"not_started","summary":null}]}
```

`planning.log` 每完成一步推一条（工具调用结束、一段思考结束、专员得出结论）。`title` 用中文业务句，不用文件路径或模型品牌当主文案。`clickable=true` 时必须带 `detail.heading` + `detail.body`（中文摘要，最长 4000 字，截断并标明「已截断」）。禁止写入 API Key、完整 polyline、原始 HTTP。思考步骤 `kind=thought`，`title` 如「思考 4s」，`detail.body` 为对该步的短中文说明（可来自模型思考的摘录，须去掉内部提示词）。刷新后 API-003 的 `planning.activity_log` 含全部条目（顺序与 SSE 一致）。

`planning.failed` 的 `failure_reason` 必须是给客户看的中文原因（与入库的 Coco 消息一致），禁止只写「失败」或空字符串。前端在中栏以 **Coco** 气泡展示该条消息；刷新后从 API-003 的 `messages` 仍能读到同一内容。运行日志仍保留，失败那一步 `clickable=true` 且细节与原因一致。

前端：`EventSource` 失败则每 2s 调 API-003，直到 `planning.status` 为 `succeeded` 或 `failed`。失败时以对话里 Coco 的说明为准，不只看 SSE 状态。

---

### API-006 行程列表

| 项目 | 内容 |
| --- | --- |
| 关联需求 | REQ-005；AC-015 |
| Method / URL | GET /api/itineraries |
| 请求 | Query：`page`、`page_size`，规则同 API-002。只返回 `status=ready` 的行程。 |
| 成功响应 | **200** 分页，`data: ItineraryListItem[]`：`id`、`title`、`destination_city`、`duration_days`、`pace`、`updated_at`、`conversation_id`。 |
| 失败响应 | 400；500。 |

---

### API-007 行程详情

| 项目 | 内容 |
| --- | --- |
| 关联需求 | REQ-003、REQ-006；AC-005,007,016,021,022,023 |
| Method / URL | GET /api/itineraries/{itinerary_id} |
| 请求 | 路径参数 `itinerary_id`。无请求体。 |
| 成功响应 | **200** `data: ItineraryPublic`。 |
| 失败响应 | 404；500。 |

成功示例（字段齐全，天数缩短便于联调）：

```json
{
  "success": true,
  "data": {
    "id": "itn_01",
    "conversation_id": "conv_01",
    "title": "杭州 5 日轻松游",
    "destination_city": "杭州",
    "origin_city": "上海",
    "duration_days": 5,
    "pace": "relaxed",
    "companion_type": "couple",
    "assumptions": ["市内交通按公交+适量步行", "住宿为推荐档，不代订"],
    "days": [
      {
        "day_index": 1,
        "label": "第 1 天",
        "date": null,
        "cards": [
          {
            "id": "card_01",
            "type": "attraction",
            "title": "西湖",
            "poi_id": "B0FFFAB6J2",
            "lng": 120.148,
            "lat": 30.242,
            "address": "杭州市西湖区",
            "intro": "杭州核心湖区，适合轻松散步。",
            "photo_url": "https://example.amap.photo/xxx.jpg",
            "start_time": "10:00",
            "suitable_for_children": true
          }
        ],
        "legs": []
      }
    ],
    "budget": {
      "currency": "CNY",
      "cap_amount": 20000,
      "total_amount": 16200,
      "over_cap": false,
      "includes_note": "含上海—杭州往返与当地食住行门票的估算，非实时报价",
      "categories": [
        {"key": "transport", "label": "交通", "amount": 4000},
        {"key": "lodging", "label": "住宿", "amount": 6000},
        {"key": "food", "label": "餐饮", "amount": 3500},
        {"key": "tickets", "label": "门票活动", "amount": 2200},
        {"key": "other", "label": "其他", "amount": 500}
      ]
    },
    "checklist": [
      {"id": "chk_01", "text": "携带身份证", "relevant": true},
      {"id": "chk_02", "text": "查看是否需要提前预约西湖周边热门园", "relevant": true}
    ],
    "map_center": {"lng": 120.15, "lat": 30.25},
    "quick_suggestions": [
      {"id": "qs_01", "text": "第三天不要排那么满"},
      {"id": "qs_02", "text": "白天少走路，多坐公交"},
      {"id": "qs_03", "text": "换一家更安静的推荐住宿"}
    ],
    "status": "ready",
    "created_at": "2026-09-13T05:24:00Z",
    "updated_at": "2026-09-13T05:24:00Z"
  },
  "error": null,
  "error_code": null,
  "message": "ok"
}
```

`days[].legs`：相邻两张卡片之间一条。`mode` 为 `transit` | `walking` | `mixed`；`duration_min`、`distance_m` 可空；`summary` 如「公交约 25 分钟」；`source` 为 `amap` | `estimate`。`photo_url` 可空，空则前端用本地占位图，不编造高德地址。国内清单不含护照签证。

超支时 `over_cap=true` 且 `total_amount > cap_amount`（AC-007）。

---

### API-008 逐项改卡片

| 项目 | 内容 |
| --- | --- |
| 关联需求 | REQ-003、REQ-006；AC-006,017 |
| Method / URL | PATCH /api/itineraries/{itinerary_id}/cards/{card_id} |
| 请求 | `CardPatch`：可空字段 `title`、`start_time`（`HH:MM` 或 null）、`day_index`、`sort_order`。至少改一项。不重跑专员。 |
| 成功响应 | **200** `data: ItineraryPublic`（整份报告，含重算后的 `legs`）。 |
| 失败响应 | 400；404；500。 |

---

### API-009 删除卡片

| 项目 | 内容 |
| --- | --- |
| 关联需求 | REQ-003、REQ-006；AC-006,017 |
| Method / URL | DELETE /api/itineraries/{itinerary_id}/cards/{card_id} |
| 请求 | 无请求体。 |
| 成功响应 | **200** `data: ItineraryPublic`。该点从当天卡片和当天地图点移除。 |
| 失败响应 | 404；500。 |

---

### API-010 目的地灵感

| 项目 | 内容 |
| --- | --- |
| 关联需求 | REQ-005；AC-012,020 |
| Method / URL | GET /api/inspirations |
| 请求 | 无。 |
| 成功响应 | **200** `data: InspirationPublic[]`。至少 1 条。`image_url` 指向前端静态资源（如 `/inspirations/hangzhou.jpg`）。点击不调用任何「生成行程」接口；前端不导航详情。 |
| 失败响应 | 500。 |

```json
{
  "success": true,
  "data": [
    {
      "id": "insp_hangzhou",
      "city": "杭州",
      "title": "西湖边慢慢走",
      "description": "湖景、茶、短途高铁都合适，适合轻松几天。",
      "image_url": "/inspirations/hangzhou.jpg"
    }
  ],
  "error": null,
  "error_code": null,
  "message": "ok"
}
```

---

### EXT-001 DeepSeek Chat Completions

来源：[Your First API Call](https://api-docs.deepseek.com/)、[Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing)、[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)（2026-09-13）。

- URL：`POST {deepseek_base_url}/chat/completions`，默认 `https://api.deepseek.com/chat/completions`（OpenAI 兼容；`/v1` 为别名）。
- Header：`Authorization: Bearer {deepseek_api_key}`，`Content-Type: application/json`。
- 推荐模型字段：`deepseek_model=deepseek-flash`（V4.1-Flash）。旧名 `deepseek-chat` / `deepseek-v4-flash` 不作为本项目写入值。
- 能力：JSON 输出、Tool Calls。思考模式默认开；本项目用 `thinking: { "type": "enabled"|"disabled" }` 与 `reasoning_effort`。思考模式下降 `temperature` 等无效。
- 调用方式：`httpx.AsyncClient(trust_env=False)`，不使用会继承进程环境的客户端默认配置。密钥只进 `backend/.env`。
- 价格（官方表，美元 / 1M tokens，会变）：Flash 非高峰输入 cache miss $0.15、输出 $0.6；高峰约为 2 倍。思考会增加输出 token 与等待。本项目未实测单次出方案费用；等待与费用按 D-007 方案 A 的估计验收。

成功响应认 `choices[0].message.content` 与 `choices[0].message.tool_calls`；失败认 HTTP 4xx/5xx 与 body 中的 `error`。

---

### EXT-002 百炼千问 OpenAI 兼容

来源：[OpenAI 兼容-Chat](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)、[兼容说明](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)、[qwen-plus](https://help.aliyun.com/zh/model-studio/qwen-plus)、规范 `shared/security.md`（2026-09-13）。

- URL：`POST {qwen_base_url}/chat/completions`。国内 Demo 默认 `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`（北京）。Key 与地域必须匹配。
- Header：`Authorization: Bearer {qwen_api_key}`。
- 模型：`qwen_model=qwen-plus`。
- JSON 模式：`response_format: { "type": "json_object" }`，且 messages 中必须出现 `json`（大小写不敏感），否则接口 400。
- 工具：`tools` 仅 `function` 类型。
- **禁止 `dashscope` SDK**；`httpx.AsyncClient(trust_env=False)`。
- `enable_thinking` 默认关（商业版）。本项目专员 JSON 输出时保持关闭，避免与 json_object 冲突。

---

### EXT-003 高德 Web 服务

来源：[地理/逆地理编码](https://lbs.amap.com/api/webservice/guide/api/georegeo)、[地点搜索 2.0](https://lbs.amap.com/api/webservice/guide/api/newpoisearch)、[天气查询](https://lbs.amap.com/api/webservice/guide/api/weatherinfo)、[路径规划 2.0](https://developer.amap.com/api/webservice/guide/api/newroute)（文档页标注更新至 2026-06）。Key 类型：**Web 服务 API**。统一 `output=json`。`status=="1"` 且 `infocode=="10000"` 为成功。部分空字段可能是 `[]` 而非 `""`。

| 工具名 | Method / URL | 必填查询参数 | 本项目取用字段 |
| --- | --- | --- | --- |
| `geocode_city` | GET `https://restapi.amap.com/v3/geocode/geo` | `key`,`address`；可选 `city` | `geocodes[0].location`、`adcode`、`citycode` |
| `search_poi` | GET `https://restapi.amap.com/v5/place/text` | `key`；`keywords` 或 `types` | `pois[].id,name,location,address,type`；`show_fields=business,photos` 时营业时间、评分、人均、`photos[].url` |
| `get_poi_detail` | GET `https://restapi.amap.com/v5/place/detail` | `key`,`id`（POI ID） | 同 POI 字段；微详情 intro 优先用 business/tag，不足由研究专员写短介绍 |
| `get_weather` | GET `https://restapi.amap.com/v3/weather/weatherInfo` | `key`,`city`（adcode） | `extensions=all` 时 `forecast.casts`（日期、昼夜天气与气温） |
| `route_walking` | GET `https://restapi.amap.com/v5/direction/walking` | `key`,`origin`,`destination` | `show_fields=cost`；`paths[0].distance`（米）、`cost.duration`（秒） |
| `route_transit` | GET `https://restapi.amap.com/v5/direction/transit/integrated` | `key`,`origin`,`destination`,`city1`,`city2`（citycode） | `show_fields=cost`；首条 `transits[0]` 的 `distance`、`cost.duration`、`cost.transit_fee` |

`origin`/`destination`：`经度,纬度`，小数点后最多 6 位。公交 `city1`/`city2` 同时必填。地点搜索 2.0 文档标明面向企业试用、有配额；配额不足时按第六层降级，不得假装查到点。

本期不用驾车/骑行作为默认市内方式（PRD 假设公交+步行）。大交通（上海—杭州）由模型按常识估算写入预算与首尾天说明，不调用高德跨城火车/机票接口（本期无此外部能力）。

---

### EXT-004 高德 JS API 2.0（前端）

来源：[展示地图](https://developer.amap.com/api/javascript-api-v2/tutorails/display-a-map)、[安全密钥](https://developer.amap.com/api/javascript-api-v2/guide/abc/jscode)（2026-09-13）。

- 加载：`AMapLoader`，`key=VITE_AMAP_JS_KEY`（**Web 端 JSAPI** Key，与 Web 服务 Key 分开申请），`version=2.0`。
- 本地 Demo：在加载脚本前设置 `window._AMapSecurityConfig = { securityJsCode: VITE_AMAP_SECURITY_JS_CODE }`（官方允许的明文便捷方式）。该值会出现在浏览器，仅适用于本机 Demo；公网部署应改为 `serviceHost` 代理，不在本期范围。
- 用途：对话开始后右栏地图、行程详情地图模式。点位来自 `ItineraryPublic` 的 `lng/lat`，不在浏览器直调 Web 服务 Key。
- 不做：唤起外部导航 App、路线导航 SDK。

---

## 三、接口请求数据的类型选型

- 自有接口：JSON，`application/json`；UTF-8；字段 **snake_case**，前后端同名不转驼峰。
- SSE：`text/event-stream`，`data` 行内 JSON。
- 高德/模型：按官方 query/JSON；后端 Plugin 把结果收成内部 dict 再给模型，不把官方超大 polyline 原样塞进前端。

### 共享信封与枚举

`ApiEnvelope`：`success` bool、`data`、`error`、`error_code`、`message`、`timestamp`、`request_id`、`metadata`。分页另含 `pagination`（PyCore：`page`、`page_size`、`total_items`、`total_pages`、`has_next`、`has_prev`）。

| 名 | 取值 |
| --- | --- |
| `pace` | `relaxed` \| `moderate` \| `packed`（展示：轻松/适中/紧凑） |
| `region` | `domestic` \| `outbound` |
| `companion_type` | `solo` \| `couple` \| `family` \| `friends` \| `parent_child` \| `unknown` |
| `card.type` | `attraction` \| `lodging` \| `meal` \| `other` |
| `planning.status` | `idle` \| `running` \| `succeeded` \| `failed` |
| `specialist.status` | `not_started` \| `running` \| `succeeded` \| `failed` |
| `message.role` | `user` \| `assistant` \| `system` |
| `message.display_name` | `assistant` 固定 `"Coco"`；`user` 可省略或 `"我"`；`system` 不在中栏当对话气泡展示 |
| `log.kind` | `tool` \| `thought` \| `specialist` |

口语映射在规划经理（Coco）提示词中实现（不要太赶→`relaxed` 等），不另做接口。中栏所有 `role=assistant` 的气泡展示名固定为 **Coco**，不随底层模型品牌变化。

`ActivityLogEntry`：`id`、`kind`、`specialist`（`destination_research`\|`budget_expert`\|`itinerary_design`）、`title`、`clickable`、`detail`（可空对象，`heading`+`body`）、`created_at`。单次规划最多保留 80 条，超出丢最早的 `thought`（工具结果优先留）。

### 校验

- `content` 1–2000；空格不算有效消息。
- `duration_days` 1–14（第一期单城；超过仍只生成该上限并在假设里说明截断——若用户说 5 天则必须 5 天，AC-005）。
- `budget_amount_cny` ≥ 0；与 `budget_tier`（`economy`\|`comfort`\|`premium`）可只填其一。
- `adults` ≥ 1 或与儿童合计 ≥ 1；亲子时 `children_age_bands` 未齐则 `ready=false`（PRD）。
- 坐标：经度 -180～180，纬度 -90～90。
- 无文件上传。

### 跨请求传递与存储

- 无登录。所有会话与行程存在本机后端 SQLite `backend/data/Travel_Helper.db`（D-004：刷新不丢本机 Demo；不按账号隔离、不承诺换浏览器同步——换浏览器仍打同一本地后端则能看到同一库）。
- 前端不把行程正文只放 `localStorage`；刷新后 GET 列表/详情恢复。`localStorage` 仅可记当前打开的 `conversation_id` 以便回到中栏，丢失不影响数据。
- `conversation_id` / `itinerary_id` / `card_id` 为服务端生成的稳定字符串。一份会话第一期最多一份 `ready` 行程；修订改同一 `itinerary_id`。
- 规划任务进行中的中间专员产物存在任务行/JSON 列，成功后写入 `itineraries`；失败保留对话、`planning.error_message`（与 Coco 消息中的原因一致），不写假行程。

### 实体（ORM 要点）

| 表 | 关键字段 | 关系 |
| --- | --- | --- |
| `conversations` | id, title, intake_json, planning_json, created_at, updated_at | 1—N messages；0—1 itinerary |
| `messages` | id, conversation_id, role, content, created_at | 属会话；`assistant` 对客户展示名为 Coco |
| `planning_jobs` | id, conversation_id, status, specialists_json, activity_json, error_message, started_at, finished_at | 属会话；running 时同会话不得再开第二个；`activity_json` 为运行日志 |
| `itineraries` | id, conversation_id, payload_json, status, title, destination_city, duration_days, pace, created_at, updated_at | payload 含 days/budget/checklist |
| `inspirations` | 可用静态 JSON 文件代替表：`backend/src/data/inspirations.json` | 只读 |

不建用户表。不存护照号。

---

## 四、模型选型与提示词设计

无模型则无法做问诊与专员。角色用哪家、是否开思考见 **D-007 已确认选 A**。本节为确认后的配置与提示词/工具契约，不改接口编号。

### 已确认配置（D-007 方案 A）

| 角色 | 服务 | 模型配置键 | 思考 | 理由 |
| --- | --- | --- | --- | --- |
| 规划经理 Coco（问诊/修订） | DeepSeek | `deepseek_model` | **关** | 多轮要快；结构化 JSON + 后端硬校验最小集 |
| 目的地研究 | 千问 | `qwen_model` | 关 | 国内景点/季节/人群更熟；工具循环 + JSON |
| 预算专家 | 千问 | `qwen_model` | 关 | 分类金额 JSON，无工具 |
| 行程设计 | DeepSeek | `deepseek_model` | **开** `reasoning_effort=high` | 天数、疏密、路线能否排下，工具观察后再决策 |

接入：均 `httpx` + OpenAI 兼容 `chat/completions`。超时 `llm_timeout_seconds`（默认 60）。重试最多 1 次，仅超时/429，不对 400 重试。

提示词文件（用户话术不写死杭州，杭州只作验收数据）：

- `backend/src/prompts/manager_intake.md`
- `backend/src/prompts/manager_revise.md`
- `backend/src/prompts/destination_research.md`
- `backend/src/prompts/budget_expert.md`
- `backend/src/prompts/itinerary_design.md`

### 规划经理 Coco（问诊）

系统职责：旅行公司规划经理 **Coco**；只对客户说话，回复以 Coco 第一人称；专员未齐最小集不得开工。动态输入：`intake` 当前槽、`followup_rounds_used`、`messages`（最近 N 条，`manager_history_limit` 默认 20）、是否已有行程。

输出必须是 JSON（DeepSeek 用 json 约束；prompt 含「json」）：

```json
{
  "action": "ask | ready | stop | revise | suggest_new_plan",
  "reply": "给客户看的中文",
  "intake_patch": {},
  "recommended_destination": null
}
```

- `ask`：一轮问完当前 `missing_fields`，专员不上场。
- `ready`：最小集齐（含国内推荐目的地已写入 `destination_city`）。
- `stop`：已用满 2 轮追问仍缺出发地或时长等（AC-011）。
- `revise`：已有行程时的局部改（REQ-006）。
- `suggest_new_plan`：换目的地或大幅改天，提示去新建计划。
- 后端用规则引擎合并 `intake_patch` 后 **再** 判断 `ready`，模型说 ready 但槽不齐则改回 `ask`/`stop`，不开工。
- 国内无城市有画面：允许 `recommended_destination` 填一个城市并 `ready`（AC-009）。
- 出境规则留在提示词（D-001），本期不演示；误走出境且无国家则 `ask`，不出按天计划。
- 不收集护照号。

修订模式输入另含当前 `ItineraryPublic` 摘要。`revise` 时附加：

```json
"operations": [
  {"op": "remove_card", "card_id": "card_03"},
  {"op": "set_day_pace", "day_index": 3, "max_major_points": 1}
]
```

后端执行 operations，必要时只重算受影响 `legs`，不重跑三名专员（AC-006,018）。无法映射的句子：`reply` 说明能改什么，行程不变。

### 目的地研究（工具循环）

系统：根据 intake 查国内目的地是否适合该人群；必须先工具后结论。禁止在零工具结果时编造开放时间。

工具（Plugin，见下）：`geocode_city`、`search_poi`、`get_poi_detail`、`get_weather`。最多 `max_tool_iterations_research`（默认 8）轮：模型发 tool_calls → Plugin 真实执行 → 观察回传 → 再决定继续或结束。结束输出 JSON：

```json
{
  "ok": true,
  "destination_city": "杭州",
  "weather_summary": "...",
  "pois": [{"poi_id": "", "name": "", "type": "attraction", "reason": "", "suitable_for_children": true, "open_time": "", "photo_url": null}],
  "warnings": []
}
```

`ok=false` 时必须带具体原因，禁止只写失败：

```json
{
  "ok": false,
  "reason_code": "destination_not_found",
  "reason": "在国内地图里找不到这个目的地，没有可用的景点信息"
}
```

`reason_code`：`destination_not_found` | `poi_empty` | `amap_unavailable` | `iteration_limit` | `model_error`。`reason` 为给客户看的中文，须对应真实工具/检索结果，禁止编造（例如不得写「可能天气不好」）。`ok=false` → 规划失败（AC-004），不进入预算与行程。预算专家、行程设计失败时同样输出 `ok=false` + `reason_code` + `reason`。

### 预算专家

无工具。输入：intake + 研究成果 + 行程草稿若已有（并行时可能尚无行程：先按研究成果与天数估一版，行程完成后若总额差超过 `budget_recompute_ratio` 默认 0.2 则用行程卡片再跑 **一次** JSON，仍不新增专员角色）。输出：

```json
{
  "ok": true,
  "currency": "CNY",
  "total_amount": 0,
  "categories": [{"key": "transport", "amount": 0}],
  "includes_note": "",
  "over_cap": false
}
```

超上限必须 `over_cap=true`（AC-007）。金额为估算，文案写明非实时库存价。

### 行程设计（工具循环）

系统：按 `pace` 排每天主要点（轻松 1–2、适中 2–3、紧凑 3–4，不验分钟）；亲子避开明显不适合儿童的点或在卡片说明；默认公交+步行；点之间必须问路线工具，失败才允许 `source=estimate` 并在 `summary` 标明「约」。首尾天可含出发/返回说明。可含 1 张/晚的推荐住宿卡片，不代订、不写支出。

工具：`search_poi`、`get_poi_detail`、`route_walking`、`route_transit`。最多 `max_tool_iterations_itinerary`（默认 12）。相邻点直线距离（后端用坐标估算）低于 `walk_threshold_m`（默认 1200）先步行，否则公交；公交缺 `citycode` 则先 `geocode_city`。结束 JSON 必须能填进 `ItineraryPublic.days`（缺坐标的点丢弃或补一次 detail）。`ok=false` 时同样必须带 `reason_code` + `reason` → 规划失败，由 Coco 转述原因。

同一目的地、同一天数，亲子+轻松 vs 情侣+紧凑须在点量或活动类型上可区分（AC-008）——提示词写明对照约束，不是换标题。

### 工具权限边界

| Plugin | 允许 | 禁止 |
| --- | --- | --- |
| 高德六工具 | 国内检索、天气、步行/公交耗时 | 订票、支付、境外地图、把 Key 回传模型可见日志 |
| 无 | — | 文件系统、任意 URL、执行代码 |

模型看不到完整 Key。日志只记 URL 路径、infocode、poi 数量，不 dump 全文。

---

## 五、接口逻辑算法设计

### 共用：问诊槽与就绪

1. 用规则从用户句与 `intake_patch` 合并槽位（城市名、天数、数字预算、节奏口语、人数）。
2. `region`：有明确国内城市则 `domestic`；仅「出国」则 `outbound` 且目的地未到国家/区域则未就绪。
3. `ready` 当且仅当：出发城市、region、时长、和谁、预算（数字或档位）、节奏、模糊描述或目的地均有；亲子还需儿童年龄段；国内无城市时须已推荐 `destination_city`。
4. `followup_rounds_used`：仅经理 `action=ask` 且本轮确实发了追问时 +1；客户首句不算追问。满 2 且仍未 ready → 强制 `stop`。

### API-001

读校验 → 插入 `conversations` → 若有预填，`missing_fields` 只含仍空项 → 201。不调模型、不开专员。可选插入一条 `system`/`assistant` 内部备注不展示；对客户的第一句仍等 API-004 或前端引导「继续和经理说出发地」——为满足 AC-014，创建后前端自动发一条 `content` 为「已按表单创建，请根据已填项继续」的 API-004，经理不得重问已填节奏等。**推荐：API-001 成功后由前端立刻调一次 API-004，`content` 使用固定模板「请根据已填写的计划继续，不要重复已给的字段。」** 这样经理第一轮只问缺口。

### API-002 / API-006 / API-010 / API-003 / API-007

只读。API-010 读静态 JSON。列表按 `updated_at` 降序。

### API-004

```text
校验会话存在 → 写入 user 消息
若 planning.status==running：
  不新开任务；调轻量回复（可规则，不强制再打模型）「专员还在做，完成后会放到行程里」
  返回 200，专员状态不变
若已有 ready 行程且非「请按表单继续」类开场：
  走修订提示词 → action revise/suggest_new_plan/ask
  revise：应用 operations，更新 itineraries.updated_at，专员状态保持上次 succeeded（AC-006）
否则：
  调规划经理问诊模型（同步）
  解析 JSON，失败则按第六层修一次格式，再失败 500
  规则合并 intake，覆盖虚假 ready
  写 assistant 消息
  若 ready：创建 planning_job running，destination_research→running，后台 asyncio 任务
  返回 200
```

后台规划（同一 job）：

```text
专员 destination_research：工具循环直到 JSON ok 或失败或达迭代上限
失败 → 三专员相应 failed，job failed，按专员 `reason`（缺省则用该失败类型的固定中文模板）组装 **Coco** 消息入库（必须含无法完成的原因，禁止只说「失败了」），不为此再调问诊模型以免编造原因；SSE `planning.failed`（含 `failure_reason` 与 `coco_message_id`），不写 itinerary
成功 → 并行启动 budget_expert 与 itinerary_design
  任一路失败 → job failed，插入 Coco 消息（含该专员无法完成的原因），不写假方案（已成功的专员摘要仍可见）
  都成功 → 经理规则拼接 assumptions、checklist（国内无护照）、quick_suggestions
        → 插入 itineraries status=ready
        → 插入 Coco 消息：告知方案已好、可去行程详情查看（不把按天卡片贴进对话）
        → 更新会话 title、planning.succeeded、itinerary_id
        → SSE itinerary.ready
```

工具循环（研究/行程）：

```text
for i in 1..max_iter:
  LLM(messages, tools)
  若无 tool_calls：校验 JSON schema → 返回
  对每个 call：PluginRegistry.execute(name, **args) → 真实 HTTP 观察 → 写入一条 `planning.log`（title 中文、detail 为脱敏摘要）
  messages += assistant tool_calls + tool 结果
超过 max_iter 且无合法 JSON → 该专员失败
```

不是「一次计划然后固定执行」。

### API-005

校验会话 → 将请求挂到该 `conversation_id` 的订阅队列 → 推送当前快照（含已有 `activity_log`）→ 之后每次 specialists 变更推 `planning.updated` → 每步结束推 `planning.log` → 终态推 ready/failed 后关闭。heartbeat 每 15s。客户端断开不取消后台 job（第六层）。

### API-008 / API-009

改/删卡片 → 重排 `sort_order` → 对受影响相邻对调用 `route_*`（超时则该 leg `source=estimate`）→ 返回整份行程。`planning` 不改回 running。

### 日期滚动

无接口。前端用 `days[].day_index` 与卡片 DOM 交叉观察：顶部点选 `scrollIntoView`；滚动更新高亮。AC-021 纯前端，数据来自 API-007。

### 地图

对话前：右栏渲染 API-010，不加载地图也可以（推荐：未开聊不加载 JS API，减少 Key 请求）。第一条出行消息发送成功后加载 EXT-004，中心用问诊城市 geocode（若尚无行程，后端可在 ConversationPublic 增加 `map_hint: {lng,lat}|null`——问诊 ready 前用出发城市，之后用目的地；由 API-003/004 附带，避免前端持 Web 服务 Key）。有行程则用各 card 坐标。

为少一个接口：`ConversationPublic` 增加可选 `map_hint`。问诊未到城市时 `map_hint=null`，右栏仍切到地图空白中国级视野（前端写死国内中心 104.2,35.2 缩放 4），不报错。此为 Agent 决定，不改需求。

### 逐接口体验影响

#### API-001 / API-002 / API-006 / API-010 / API-003 / API-007

| 技术选择与触发场景 | 用户可见结果或代价 | 当前处理与依据 | 验收或验证 |
| --- | --- | --- | --- |
| 无登录 + SQLite | 刷新还在；换电脑不同步 | 沿用 D-004 | 刷新后列表与详情仍在 |
| 灵感静态图 | 右栏有图有文，点不进详情 | PRD AC-012,020；不调用模型 | 点击后仍停在工作台 |

无新增待确认项。

#### API-004 / API-005

| 技术选择与触发场景 | 用户可见结果或代价 | 当前处理与依据 | 验收或验证 |
| --- | --- | --- | --- |
| 问诊同步、专员异步 | 经理几秒内回复；齐了之后还要等专员，但能看过程 | Agent 决定，满足 AC-003 | 齐了之后专员变为进行中 |
| 规划中再发消息 | 不另开一轮专员，避免双倍费用和乱序 | Agent 决定 | 过程中再聊，最终仍一份方案 |
| 角色模型与思考模式 | 问诊约数秒；出一版 5 天方案估计再等约 40–90 秒（未实测） | **D-007 已确认 A** | AC-001～005 质量；用秒表估等待 |
| 客户端关页 | 后台仍跑完并写入 SQLite | 刷新可从列表进入 | 规划中刷新，回来能看到完成或失败 |

#### API-008 / API-009

| 技术选择与触发场景 | 用户可见结果或代价 | 当前处理与依据 | 验收或验证 |
| --- | --- | --- | --- |
| 只改库、不重跑专员 | 卡片马上变；预算可能暂时略旧 | PRD AC-006 | 删点后专员仍为已完成 |
| 邻接腿再查高德 | 多等最多数秒；失败则「约」 | Agent 决定 | AC-022 间隔仍有交通文案 |

#### EXT-001～004

| 技术选择与触发场景 | 用户可见结果或代价 | 当前处理与依据 | 验收或验证 |
| --- | --- | --- | --- |
| 缺 Key | 问诊/地图/出方案不能真跑 | 不阻塞页面与静态灵感；对话返回明确缺配置 | 有/无 Key 分层验收 |
| JS 安全密钥明文 | 本机 Demo 能出图；密钥在浏览器 | 官方便捷方式；仅 Demo | 开聊后右栏为地图 |
| 高德配额/试用限制 | 点位或交通可能降级 | 失败不交假完整方案；单腿可 estimate | AC-004；AC-022 允许「约」仅当 amap 失败 |

---

## 六、接口失败异常设计

共享：面向用户的 `error` 用中文；日志用中文一行一条记动作与结果，不含 Key、不含用户全文可关（消息可记 id 与长度）。分类：校验 / 业务 / 外部依赖 / 内部。禁止裸 `except Exception: pass`。

| error_code | HTTP | 何时 |
| --- | --- | --- |
| VALIDATION_ERROR | 400 | 字段、枚举、空消息 |
| NOT_FOUND | 404 | 会话/行程/卡片不存在 |
| CONFLICT | 409 | 同会话已有 running job 时，**管理接口**误触发第二次开工（正常发消息走 200 说明） |
| INTERNAL_ERROR | 500 | 未分类、经理同步失败已重试仍失败 |

### API-001～003、006、007、010

- 校验失败 → 400，表单可改后重提。
- 找不到 → 404，前端留在工作台并提示。
- DB 错误 → 500，数据不写半条会话（事务回滚）。

### API-004

| 触发 | 处理 | 用户看到 | 是否可恢复 |
| --- | --- | --- | --- |
| 经理超时/5xx | 重试 1 次；仍失败 500；user 消息保留 | 「Coco 暂时没有回复，请再试一次」 | 同一句可再 POST |
| 经理 JSON 非法 | 追加一条「只输出 json」再调 1 次；仍失败 500 | 同上 | 可重试 |
| 未齐 / stop | 200 + 追问或缺口说明 | 对话里说明；专员 not_started | 继续聊 |
| 专员后台失败 | 200 早已返回；之后按 `reason` 插入 **Coco** 说明并 SSE `planning.failed` | Coco 说出无法完成的原因；无按天方案（AC-004） | 可再发「请再试一次」开 **新** job（仅当 status=failed） |
| 规划中再发 | 200 说明等待 | 过程视图仍 running | 无需操作 |
| 客户端断开 | job 继续 | 刷新 GET 恢复 | 不重复扣两次开工 |

付费调用：每专员主循环不因失败自动整段重跑超过 1 次。工具单次 HTTP：超时/5xx 重试 1 次。

### API-005

连不上：前端 2s 轮询 API-003。服务端不因 SSE 断开而 kill job。

### API-008 / API-009

卡片不存在 404。高德补腿失败：保存卡片变更，leg 用 estimate，不回滚删除。不出现「改了但界面还是旧点」。

### 专员与高德

| 触发 | 专员 | 用户 |
| --- | --- | --- |
| 地理编码不到城市 | 研究失败 | **Coco** 说明：找不到该目的地，请换一个国内城市或把地名说清楚；无假方案 |
| POI 全空 | 研究失败 | **Coco** 说明：检索不到可用景点信息；无假方案 |
| 天气失败 | 研究可继续，warnings 记录 | 方案可出，清单/介绍弱化天气 |
| 单段公交失败 | 行程仍可 ok | 该间隔「约 xx 分钟（估算）」 |
| 模型达迭代上限无 JSON | 该专员失败 | **Coco** 说明研究/排程超时或无法形成结论，不交假方案 |
| 千问/DeepSeek 余额不足 | 同步问诊 500；后台专员 failed | 问诊：「Coco 暂时没有回复」；后台失败时 Coco 说明「模型服务不可用」 |

AC-004 用无法研究的目的地（如乱码地名）走失败路径：对话里必须出现 Coco 说出的**原因**，不能只有过程状态变成失败。Coco 失败消息由后端用专员 `reason` 组装，口吻示例：「这次没法帮你出方案。原因是：{reason}。你可以换一个目的地，或者说得更具体一点再试。」不为此再调问诊模型。

### 配置缺失

启动不硬崩页面：后端可起。API-004 发现缺 `deepseek_api_key`/`qwen_api_key` 返回 500，错误「未配置模型密钥」。缺 `amap_web_key`：问诊可 ready，研究第一工具失败 → 按研究失败处理，Coco 说明地图服务不可用。缺 JS Key：右栏地图占位文案「地图未配置」，不影响对话与列表。

---

## 七、项目本地层级设计

```
Travel_Helper/
├── pycore/                          # PYTHONPATH 引入，不 pip 安装
├── docs/                            # PRD、tech-spec、decisions、后续 ui-style/原型
├── backend/
│   ├── .env / .env.example
│   ├── requirements.txt
│   ├── src/
│   │   ├── main.py                  # APIServer，host/port 来自 config
│   │   ├── config/settings.py       # AppSettings + ConfigManager.load(..., use_env=False)
│   │   ├── api/deps.py              # get_db；无 get_current_user
│   │   ├── api/routes/
│   │   │   ├── conversations.py     # API-001～005
│   │   │   ├── itineraries.py       # API-006～009
│   │   │   └── inspirations.py      # API-010
│   │   ├── models/                  # Pydantic DTO
│   │   ├── db/models.py, session.py
│   │   ├── repositories/
│   │   ├── services/                # manager, planning, revision
│   │   ├── plugins/                 # 高德六工具 BasePlugin
│   │   ├── prompts/
│   │   └── data/inspirations.json
│   ├── tests/
│   └── data/                        # Travel_Helper.db；gitignore
└── frontend/
    ├── .env / .env.example
    ├── public/inspirations/         # 国内城市图片
    └── src/
        ├── main.tsx, App.tsx
        ├── pages/WorkbenchPage.tsx, ItineraryDetailPage.tsx
        ├── components/              # 三栏、卡片、过程视图、微详情
        ├── services/                # axios 封装，禁止组件内直调
        ├── stores/                  # 当前会话 Context
        ├── hooks/
        ├── router/index.tsx         # / 与 /itineraries/:id；无登录路由
        ├── types/
        ├── mocks/                   # 仅未接后端的页面，须带可见 Mock 标识
        └── utils/
```

运行（开发 Agent 端口）：

- 后端：`cd backend && PYTHONPATH=.. <python3.11+> -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8099`
- 前端：`cd frontend && npm run dev -- --host 127.0.0.1 --port 5199`；`VITE_API_BASE_URL=/api`，代理到 8099
- 门禁：前端 5175 + `VITE_BACKEND_PROXY_TARGET=http://localhost:8003`，后端 8003
- 质量：项目根 `pyproject.toml`；`pytest backend/tests --timeout=120`（须 `pytest-timeout`）
- SQLite 相对路径解析为绝对路径并创建父目录

依赖约束：FastAPI、uvicorn、sqlalchemy[asyncio]、aiosqlite、httpx、pydantic、python-dotenv、pytest、pytest-timeout。LLM 不引入 `dashscope`、不为百炼装官方 SDK。前端：React、react-dom、react-router、axios、vite、@vitejs/plugin-react；地图用官方 loader，不另引入无关 UI 库。

### 配置表

后端 `backend/.env`（ConfigManager，键小写映射字段）。禁止 `os.getenv` 读业务配置。

| 字段 | 类型 | 默认 | 用途 | 敏感 |
| --- | --- | --- | --- | --- |
| debug | bool | true | 文档与日志 | 否 |
| secret_key | str | 无默认，必须配置 | PyCore 要求；本期无会话签名用途 | 是 |
| host | str | 127.0.0.1 | 监听 | 否 |
| port | int | 8099 | 监听 | 否 |
| cors_origins | JSON list | 5199/5175 四 origin | CORS | 否 |
| database_path | str | data/Travel_Helper.db | SQLite | 否 |
| deepseek_api_key | str | 空 | EXT-001 | 是 |
| deepseek_base_url | str | https://api.deepseek.com | 不含尾斜杠；代码拼 `/chat/completions` | 否 |
| deepseek_model | str | deepseek-flash | D-007 | 否 |
| qwen_api_key | str | 空 | EXT-002 | 是 |
| qwen_base_url | str | https://dashscope.aliyuncs.com/compatible-mode/v1 | 北京兼容模式 | 否 |
| qwen_model | str | qwen-plus | D-007 | 否 |
| manager_thinking_enabled | bool | false | D-007 A：Coco 问诊关思考 | 否 |
| itinerary_thinking_enabled | bool | true | D-007 A：行程设计开思考 | 否 |
| llm_timeout_seconds | int | 60 | 单次模型 HTTP | 否 |
| llm_max_retries | int | 1 | 超时/429 | 否 |
| amap_web_key | str | 空 | EXT-003 | 是 |
| amap_timeout_seconds | int | 10 | 高德 HTTP | 否 |
| planning_timeout_seconds | int | 180 | 整次规划看门狗，超时=失败 | 否 |
| max_tool_iterations_research | int | 8 | 研究循环 | 否 |
| max_tool_iterations_itinerary | int | 12 | 行程循环 | 否 |
| walk_threshold_m | int | 1200 | 先步行后公交 | 否 |
| manager_history_limit | int | 20 | 问诊上下文条数 | 否 |
| intake_max_followups | int | 2 | 与 PRD 一致 | 否 |

前端：

| 字段 | 默认 | 用途 | 敏感 |
| --- | --- | --- | --- |
| VITE_API_BASE_URL | /api | Axios base | 否 |
| VITE_BACKEND_PROXY_TARGET | http://localhost:8099 | 仅 Vite 代理 | 否 |
| VITE_AMAP_JS_KEY | 空 | JSAPI Key | 半公开 |
| VITE_AMAP_SECURITY_JS_CODE | 空 | Demo 明文安全密钥 | 是，仅 .env |

`.env` gitignore；`.env.example` 只放占位。文档不写真实值。

### 外部服务清单

| 名称 | 用途 | 依赖 | 配置状态 | Mock/真实 | 真实验证 |
| --- | --- | --- | --- | --- | --- |
| DeepSeek | 经理、行程设计 | API-004、规划任务 | 字段已列，仓库无 Key | 测试 Mock httpx；有 Key 走真实 | 需用户 Key 与额度 |
| 百炼千问 | 研究、预算 | 规划任务 | 同上 | 同上 | 北京地域 Key |
| 高德 Web 服务 | 点、天气、路线 | 专员 Plugin | 同上 | Mock 固定杭州 POI 可测编排 | Web 服务 Key、配额 |
| 高德 JS API | 地图展示 | 工作台右栏、详情 | 前端字段已列 | 无 Key 显示占位 | JSAPI Key + 安全密钥 |

无 Key 不阻塞：页面骨架、灵感、新建计划表单、日期滚动布局。阻塞：真问诊、真出方案、真地图点。

---

## 需求覆盖与待确认

| 项 | 实现路径 |
| --- | --- |
| REQ-001 AC-001,002,009,011 | API-001/004 + 问诊规则；AC-010 不实现验收用例 |
| REQ-002 AC-003,004,024 | 后台规划 + API-003/005 运行日志 |
| REQ-003 AC-005,006,007 | API-007～009 + 预算 over_cap |
| REQ-004 AC-008 | 行程提示词 + 两次规划对照 |
| REQ-005 AC-012,013,014,015,020 | API-010、前端三栏、API-001 预填、API-006 |
| REQ-006 AC-016～019,021～023 | API-007 结构 + 前端滚动；018/019 走 API-004 |
| D-001～D-006、D-008 | 已确认，落入槽位/页面/国内范围/Coco 与失败原因 |
| D-007 | **已确认 A**，问诊 DeepSeek Flash 关思考；研究+预算千问 Plus；行程设计 DeepSeek Flash 开思考 |

阻塞开发开工的产品歧义：无。阻塞 **真 Demo 联调**：模型与高德密钥（字段已列，仓库无 Key）。

本文件仅完成源文本；Mermaid 未用渲染器预览。
