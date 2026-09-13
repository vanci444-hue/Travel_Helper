# 项目经验

存放位置：`<active_project_path>/.sdd/experience.md`。仅由编排器在修复复验后判断、去重并更新；Developer/Tester 返回建议与证据。开始任务时按关键词检索相关标题，无命中就继续，不读取全部历史。

流程依据：`<harness_root>/harness-core/protocols/experience-loop.md`。经验不覆盖当前项目契约与所选规范；未复验、原因推测、一次性问题留在错误记录，不为每次报错增加条目。

## 条目格式（说明，不是已发生的经验）

实际记录时使用有辨识度的标题，填写：

- 关键词与适用条件：已知的技术栈、版本或触发场景。
- 现象与已证实根因；有效修复；下次如何避免。
- 来源任务或独立 Bugfix 描述；复验日期；证据的项目相对路径和具体章节，交付时返回实际绝对路径。
- 同类复发时更新原条目，说明旧经验未能避免问题的已核实原因，补充新的验证证据；失效结论标明并保留旧来源。

有跨项目价值时在原条目附简短全局候选；经用户授权，由编排器更新 `<harness_root>/memory/harness-experience.md` 并回链对应标题。全局记录不是自动生效的强制规则，不自动修改 Skill 或技术规范。不记录密钥、敏感原始数据或完整日志。

## SVG 作为 img 必须是合法 UTF-8 良构 XML

- 关键词：SVG、`aria-label`、Chrome broken image、HTTP 200、UTF-8
- 适用条件：静态 SVG 作为 `<img src>`；Chrome / WebKit 把整份文件当 XML 解析。Vite/静态 200 且 `Content-Type: image/svg+xml` 不能证明可见。
- 现象：右栏灵感卡图全部 broken，卡图区是底色；HTTP 仍 200。
- 已证实根因：`frontend/public/inspirations/{hangzhou,chengdu,dali}.svg` 根节点 `aria-label` 含非法字节/控制字符，XML 非 well-formed。
- 有效修复：删掉 SVG 内 `role`/`aria-label`（外层 `img` 已有 `alt`），只留合法 UTF-8 的 `<svg xmlns …>`。
- 下次如何避免：写入 SVG 后做 UTF-8 解码 + XML 解析；用浏览器 `img.decode()` 或截图像素确认，不把 HTTP 200 当图可见。
- 来源：T-001 第 1 次返工；复验 2026-09-13；证据 `.sdd/test-reports/test-T-001.md`（TC-03 复验 PASS）。
- 全局候选：其他用 SVG 当 `<img>` 的前端项目同样适用。未授权，不写入全局经验。

## 行程卡片无金额时不要用天数常数重算预算

- 关键词：budget、over_cap、itinerary cards、amount
- 适用条件：预算专家已给出合计后，行程设计卡片可能没有 `amount`。
- 现象与根因：若用「天数 × 常数」回填，会覆盖已算出的 `over_cap`。
- 有效修复：仅当卡片带 `amount` 才重算；`test_budget_over_cap` 复验通过。
- 下次如何避免：汇总与超限以预算专家结果为准，缺金额不要编造人均日消费。
- 来源：T-007；复验 2026-09-13；证据 `.sdd/test-reports/test-T-007.md` TC-06。

## 用 httpx ASGITransport 测 SSE 不要等实时 heartbeat

- 关键词：SSE、httpx、ASGITransport、heartbeat
- 适用条件：pytest 里用 `httpx.ASGITransport` 消费 `text/event-stream`。
- 现象：传输会缓冲，等首个 heartbeat 可空等约 30s 仍无输出。
- 有效策略：先把 job 推到终态再读快照，或直接测 `_event_stream` generator；常量 `HEARTBEAT_SECONDS=15` 单独断言。不要写成「所有客户端都会缓冲」。
- 来源：T-007；复验 2026-09-13；证据 `.sdd/test-reports/test-T-007.md` TC-03 与经验候选 2。

## 短尾按日滚动需要一屏底部空间并按观察带面积选天

- 关键词：IntersectionObserver、rootMargin、scroll-spy、日期 chip、padding-bottom
- 适用条件：行程详情按日滚动；观察带为视口上约 45%（`rootMargin` 底部负值）；末几天卡片短于一屏。
- 现象：点 chip 能高亮，中栏滚到底 chip 停在中间某天。
- 已证实根因：滚动高度不够，后几天进不了观察带；只取当次 IO 最上一条会在短卡片重叠时跳回上一天。
- 有效修复：报告区加约一屏底部 spacer；按观察带内可见面积选当前天；全部滚出观察带时回落到最后一天。
- 下次如何避免：先保证最后一节能滚进观察带，再写 scroll-spy。
- 来源：T-003 第 1 次返工；复验 2026-09-13；证据 `.sdd/test-reports/test-T-003.md` TC-03。
- 未验证：其他页面或其他 rootMargin。

## Vite Mock 删点写在模块内存，刷新清不掉

- 关键词：Vite、Mock、module store、HMR
- 适用条件：`frontend/src/mocks/itineraries.ts` 这类模块级 store。
- 现象：同一 Vite 进程里删卡后刷新仍无该点。
- 有效做法：验收删点前重启该 Vite，或验收后 HMR/重启以恢复 fixture。
- 来源：T-003；复验 2026-09-13；证据 `.sdd/test-reports/test-T-003.md` 经验候选。

## 跨页行程必须对齐同一个 Mock id

- 关键词：itinerary_id、查看行程、Mock
- 适用条件：对话成功入口与行程列表/详情共用一份假数据。
- 现象：T-002 链 `itn_mock_01`、T-003 主 id 为 `itn_01` 时会进空页。
- 有效修复：主 id 与规划成功 id 相同，旧 id 只做别名。
- 来源：T-004；复验 2026-09-13；证据 `.sdd/test-reports/test-T-004.md` TC-02。

## 工作台 `/` 不要叠行程列表

- 关键词：nav、pathname、WorkbenchPage
- 适用条件：对话 `/`、列表 `/trips`、详情 `/itineraries/:id`。
- 现象：用内存 `nav` 在 `/` 上切列表，刷新后 URL 是对话、内容却可能是列表。
- 有效修复：选中态跟 pathname；`/` 只渲染对话。
- 来源：T-004；复验 2026-09-13；证据 `.sdd/test-reports/test-T-004.md` TC-01。

## 不要用 curl 打 Vite 转换后的前端源码核环境变量

- 关键词：Vite、import.meta.env、VITE_USE_MOCK、curl /src
- 适用条件：核对前端是否走 Mock 或是否带 Key。
- 现象：转换后的模块会展开 env，Key 会进日志。
- 有效做法：看页面 DOM 与 `/api` 网络请求。
- 来源：T-009 Developer 建议；Tester 2026-09-13 已遵守。

## 国内只有画面没有城市须在规则层推荐一座城

- 关键词：看海、intake、region、destination_city、children_age_bands、AC-009
- 适用条件：Travel_Helper 问诊硬规则；国内模糊愿望（如看海）且出发地/天数/预算/节奏已齐。
- 现象：模型只举例城市并追问出境或儿童年龄，`planning=idle`。
- 已证实根因：`_infer_region` 不认「看海」为国内；`compute_missing_fields` 把 `region`、无城市、儿童年龄当缺口，模型 `ready` 被改回 `ask`。
- 有效修复：规则层把看海判 `domestic`、无城市推荐青岛、缺年龄写「学龄儿童」，模型追问不能挡住开工。
- 下次如何避免：最小集齐且只有画面时，ready 由规则层补齐，不依赖模型自己选定城市。
- 来源：T-009 第 1 次返工；复验 2026-09-13；证据 `.sdd/test-reports/test-T-009.md` 复验 AC-009。
- 未验证：关掉规则层后模型是否仍不追问。

## SQLite WAL 消不掉规划写库时的 database is locked

- 关键词：SQLite、database is locked、WAL、busy_timeout、planning
- 适用条件：本机 SQLite + 问诊后立刻再开新对话或专员写库。
- 现象：`sqlite3.OperationalError: database is locked`，规划开工或连续新建对话 500。
- 已证实：仅开 WAL + `busy_timeout=30s` 后锁仍复现。高压根因未定位。
- 下次如何避免：真规划写库若再 500，不要只加 PRAGMA；查并发会话/长事务/多连接写同一文件。T-010 已改为逐步短提交 + `NullPool`，成功+失败连续写库未再锁，高压未验。
- 来源：T-009 复验；T-010 复验补充；证据 `.sdd/test-reports/test-T-009.md`、`.sdd/test-reports/test-T-010.md`。不作为根因已消。

## 点名国内目的地后须规则层开工，不要改口名单城市

- 关键词：乱码地名、AC-004、region、destination_city、destination_not_found
- 适用条件：用户已给出发地/天数/同行/预算/节奏，并点名一座国内城（含检索不到的乱码）。
- 现象：问诊因城不在名单缺 `region`，`planning=idle`，无失败日志、无 `error_message`。
- 已证实根因：`_infer_region` 只认名单城/出境/看海；模型追问「哪座城」挡住规划失败闭环。
- 有效修复：未知名目的地且未提出境 → `domestic` + `ready`；挡住改写成杭州；规划失败写 Coco 原因与可点日志。
- 下次如何避免：最小集齐且用户已点名国内城时不要再拦问诊；失败交给研究/高德/预算，不要用名单城顶替。
- 来源：T-010 第 1 次返工；复验 2026-09-13；证据 `.sdd/test-reports/test-T-010.md` 复验 AC-004。
- 未验证：geocode 空结果是否立刻让研究失败（本轮实际失败来自预算专家）。

## 写死的快捷建议必须能落到修订操作

- 关键词：quick_suggestions、AC-019、prefer_transit、revision operations、sendMessage
- 适用条件：详情侧边点产品写死的芯片，与手打修订共用 API-004。
- 现象：点「白天少走路，多坐公交」约 30s 后「Coco 暂时没有回复」，行程未变；手打「第三天不要排那么满」约 2s 成功。
- 已证实根因：芯片原文原先只当闲聊，修订只认 `remove_card` / `set_day_pace`，模型空转；`sendMessage` 超时 30s 会掐断较慢修订。
- 有效修复：芯片映射到可执行操作（本轮验证了 `prefer_transit`：步行腿改公交）；修订超时不要再用问诊 30s。
- 下次如何避免：改芯片文案时先对修订操作表。共用 API-004 的详情修订不要沿用 30s。
- 来源：T-011 第 1 次返工；复验 2026-09-13；证据 `.sdd/test-reports/test-T-011.md` 复验 AC-019。
- 未验证：`replace_lodging` 浏览器点选；是否必须等到 180s（本轮修订约 1s）。
