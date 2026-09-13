# T-013 Tester 报告

- 任务：T-013 生成或刷新页面功能导航
- 总结果：**PASS**
- 时间：2026-09-13
- 类型：delivery；DEL 不计业务 AC
- 未改 `tasks.json`、业务代码、`experience.md`

## 环境

- 工作目录：`Projects_Repo/Travel_Helper`
- 静态服务：Tester 自启 `cd docs && python3 -m http.server 8765` → `http://127.0.0.1:8765/project-console.html`（首启误落用户主目录，已停并改从 `docs/` 再起）
- Chrome：152.0.7977.84；`--user-data-dir=/tmp/xtrip-t013-chrome`；CDP `127.0.0.1:9616`；开页 `Target.createTarget({newWindow:true})` + `Target.attachToTarget({flatten:true})`。**Tester 自启，结束时已停。**
- 视口：桌面 1440×900；窄屏 `Emulation.setDeviceMetricsOverride` 390×844（mobile）
- 未调付费模型/高德；未读真实 `.env`；未请求业务 `/api`
- 长证据：`.sdd/test-reports/t013-evidence.json`、`.sdd/test-reports/t013-recheck.json`、`.sdd/test-reports/t013-shots/`

## 检查表

| ID | 场景 / 预期 | 方法 | 结果 |
| --- | --- | --- | --- |
| DEL-001 | 按 `/`、`/trips`、`/itineraries/:id` 组织；卡片可导航展开；无旧六区；桌面+窄屏无整页溢出 | Chrome 点导航/展开 + 截图 + 溢出元素扫描 | **PASS** |
| DEL-002 | 功能有触发/输入输出/带分支流程；接口 method/URL/字段与源码对应；共享接口可跳到 | 展开卡片 + API 点击 + 对照路由/DTO | **PASS** |
| DEL-003 | ready、followup=2、思考开关、高德六工具、walk=1200、timeout=180；不编造出境必验/PDF；Coco 不是自由选工具 Agent | 对照 manager/settings/amap/planning + 页面文案 | **PASS** |
| DEL-004 | 来源可定位、指纹相符；复制路径成功；复制失败出手选；无业务/付费调用 | sha256_16 全量核对 + 剪贴板/prompt | **PASS** |
| DEL-005 | README 刷新有效；样例：源变更待复核、缺失、解析错误；无密钥；只写导航产物 | 点重新加载/样例/文件 change；密钥扫描 | **PASS** |

## DEL-001 — PASS

实际：

- 左侧三入口：工作台 `/`、行程列表 `/trips`、行程详情 `/itineraries/:id`。点击后 `h2` 与 `is-on` 同步。
- 功能卡默认收起；点「新建计划预填」展开触发/输入/输出/4 步带分支流程。
- 正文与导航无「项目概况 / 启动指南 / 验收看板 / 决策看板」。
- 桌面 `html.scrollWidth === clientWidth === 1440`，`xOverflow=false`。
- 窄屏改为 `wrap=block`、`aside=relative`，入口与工具条折行。初次 `scrollWidth=439` vs `clientWidth=390`；定向复核无任何子元素 `width > 390`，差值为 mobile emulation 的 `innerWidth` 与 layout viewport 不一致，不是内容撑破。截图未见裁切。

证据：`t013-evidence.json` `page_nav` / `expand`；`t013-recheck.json` `overflow.offenders=[]`；`t013-shots/desktop-page-*.png`、`narrow-*.png`、`desktop-expand.png`。

## DEL-002 — PASS

实际：8 个功能均有 trigger/input/output，flow 每步有 branch。浏览器展开「新建计划预填」可见 4 条分支（全空允许 / 解析失败为 null / pace 非法 / Mock 或无预填不补发）。接口链接 `POST /api/conversations` 点击后目标 `api-api-001` 进入视口。

与源码对应（只读路由/封装，未执行业务）：

| map | 源码 |
| --- | --- |
| POST `/api/conversations` | `conversations.py` `@router.post("")` |
| GET `/api/conversations/{id}` | `@router.get("/{conversation_id}")`；前端 `getConversation` |
| POST `.../messages` body `content` 1–2000 | `@router.post("/{conversation_id}/messages")` + `MessageCreate` |
| GET `.../events` | `events.py` SSE |
| GET `/api/itineraries` | `itineraries.py` list_ready |
| GET `/api/itineraries/{id}` | `get_itinerary` |
| PATCH `.../cards/{id}` title/start_time/day_index/sort_order | `CardPatch`；map 写明前端未挂 PATCH |
| DELETE `.../cards/{id}` | `delete_card` / `deleteItineraryCard` |
| GET `/api/inspirations` | `inspirationService` `GET /inspirations`（axios base `/api`） |

页面路由与 `frontend/src/router/index.tsx` 三路一致。`ConversationCreate.budget_includes` 前端 `draftToPayload` 不发送，map 未列，不记缺陷。

## DEL-003 — PASS

| 项 | 源码 | map/页面 |
| --- | --- | --- |
| ready | `ready = len(missing_fields)==0`；槽齐强制 ready；自称 ready 未齐则 ask/stop | 问诊算法步骤一致 |
| followup | `intake_max_followups=2` | 参数 2 |
| 思考 | `manager_thinking_enabled=False`；`itinerary_thinking_enabled=True` | D-007 开关一致 |
| 高德六工具 | `create_amap_registry` 注册 geocode_city / search_poi / get_poi_detail / get_weather / route_walking / route_transit | 同名六工具 |
| walk_threshold_m | 1200 | 1200 |
| planning_timeout_seconds | 180；`wait_for(..., timeout=settings.planning_timeout_seconds)` | 180 |
| Coco | `chat_json` 无 tools；kind=固定 JSON 决策流水线 | 页面写「不是自由选工具 Agent」 |
| 出境/PDF | 出境只推断 region / 城市名单；无护照签证必验；无 PDF 导出 | 活数据未编造；缺失样例才出现「导出 PDF（未找到实现）」 |

研究 4 工具、行程 4 工具、预算 0 工具与 `ALLOWED_TOOLS` / `tools=()` 一致。

## DEL-004 — PASS

- `project-map.json` 与 HTML 内嵌 map 一致。35 个来源路径均存在；`sha256[:16]` 与核对指纹全部相符（含 `manager.py=8640db39eeccb7bf`）。
- 点「复制路径」：剪贴板得到 `frontend/src/pages/WorkbenchPage.tsx`，未弹 prompt。
- 注入 `clipboard.writeText` 拒绝后再点：`prompt("复制失败，请手选路径", 同上路径)`。
- 无业务/付费请求。

## DEL-005 — PASS

- README 所述 `python3 -m http.server 8765` + 打开 `project-console.html` 可用。
- 「重新加载 project-map.json」：`fetch("./project-map.json")` HTTP 200，横幅空，三入口仍在。http.server 日志同路径 200。
- 「选择 map 文件」：Chrome 152 CDP 无 `Page.handleFileChooser`。用同一 `#file-map` change 处理函数灌入带 `T013-FILE-PICKER-MARKER` 的 JSON，笔记区出现该标记。
- 样例源变更：问诊卡「来源已变化待复核」，横幅基线 `8640db39eeccb7bf → deadbeef00000000`。
- 样例缺失：出现「导出 PDF（未找到实现）」与 `未找到实现` chip，缺失路径 `backend/src/services/not_implemented_export.py`。
- 样例解析错误：正文清空（`contentLen=0`），转义展示 `{page: workbench, broken: true,}`，不再渲染已核对算法。
- 产物与页面无密钥形态；配置只列字段名与源码默认值（`amap_web_key`/`deepseek_api_key` 为空占位；`secret_key` 写 example 的 change-me 占位说明）。

## 未验项

- 操作系统原生「选择文件」对话框（Chrome 152 无 `Page.handleFileChooser`）。文件 input 的 change 处理已验。
- 未打开业务前端/后端，未验真实问诊或规划运行（本任务不要求）。

## 范围外

- 无。
