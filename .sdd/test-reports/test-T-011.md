# T-011 Tester 验收报告

任务：联调网页行程详情、逐项改、对话改与快捷建议  
日期：2026-09-13  
总结果：**FAIL**（AC-019 已证实偏离）  
路径：真链路 `VITE_USE_MOCK=false`，页面无 `[Mock]`，未用 Mock 行程顶替 AC-005。

## 环境

- 工作目录：`Projects_Repo/Travel_Helper`
- 后端：复用已有 `127.0.0.1:8099`（cwd=`.../Travel_Helper/backend`，uvicorn `src.main:app`，PID 97956）。Tester **未拉起、未停止**。
- 前端：复用已有 `127.0.0.1:5199`（cwd=`.../Travel_Helper/frontend`，Vite）。Tester **未拉起、未停止**。
- Chrome：152.0.7977.84；`--user-data-dir=/tmp/xtrip-t011-chrome`；CDP `127.0.0.1:9613`；开页 `Target.createTarget` + `Target.attachToTarget({flatten:true})`；视口 1440×900。**Tester 自启，结束时已停。**
- 核环境：只看 DOM 与 `/api`（经 5199 代理到 8099）。未 curl Vite `/src/*.ts`。
- 样本：展示/刷新用未改过的杭州 `itn_a79bf0c8d6c0ec62`；偏低预算核已有 `itn_8d75be294e483e2a`（cap 800、`over_cap=true`）；删卡用未动过的 `itn_e6e7ea18e5abc6c2`；侧边改松用 `itn_a79bf0c8d6c0ec62`；快捷建议两次分别点 `itn_541d4713e1061407`、`itn_63f6c180617024d5`（均未用开发删卡残留）。

机器证据：`.sdd/test-reports/t011-evidence.json`、`t011-recheck.json`、`t011-recheck-021-e6e7.json`；截图 `.sdd/test-reports/t011-shots/`。

## 检查表

| ID | 场景 | 动作 | 预期 | 方法 | 结果 |
| --- | --- | --- | --- | --- | --- |
| AC-015 | 已有真行程 | 左侧行程点进；对话「查看行程」；刷新 | 同一 `itinerary_id`，刷新仍在 | 浏览器点选 + `/api` | PASS |
| AC-005 | 杭州 5 天详情 | 打开报告、地图模式 | 按天卡片+预算+地图+清单；5 天；点对上当天卡；非「地图未配置」 | 浏览器点选 | PASS |
| AC-016 | 同上 | 抽查第 1 / 第 5 天 | 按天卡片、顶部日期 | 浏览器 | PASS |
| AC-021 | 超过 1 天 | 滚到第 3 天；点第 1 天 chip | 高亮与可见天一致；滚动与点选都能用 | 浏览器滚/点 + 观察带面积 | PASS |
| AC-022 | 连续两张地点卡 | 看卡间交通 | 方式 + 大约距离/时间；`estimate` 且含「约」仅当高德该段失败 | DOM + GET 详情 | PASS |
| AC-023 | 详情已开 | 点卡片开微详情再关 | 名称+介绍或地址；无支付金额；回到当天列表 | 浏览器点选 | PASS |
| AC-007 | 偏低上限已有行程 | 打开详情预算区 | UI「超出上限」且 `over_cap=true` | 浏览器 + GET | PASS |
| AC-006 | 未动过真行程第 2 天 | 菜单删除一景点 | 当天卡片更新；专员仍 succeeded，无新 running | 浏览器删 + GET 行程/对话 | PASS |
| AC-017 | 同上 | 对照地图当天点 | 第 2 天不再显示该点，地图也不再当作当天点 | 浏览器地图模式 | PASS |
| AC-018 | 未动过真行程侧边 | 发送「第三天不要排那么满」 | 第三天变少或变松；同一份 `itinerary_id` | 浏览器发送 + GET | PASS |
| AC-019 | 未动过真行程快捷建议 | 点一条建议 chip | 该句进对话、建议收起、方案更新 | 浏览器点选，两次 | **FAIL** |
| TC-01 | 列表 vs 对话 | 对照 id、刷新 | 同一 id | 浏览器 | PASS |
| TC-02 | 删/改后 planning | GET conversation | specialists 全 succeeded，无 running | `/api` | PASS（删卡、侧边改） |
| TC-03 | 国内清单 / PDF | 读 DOM 与 checklist | 无护照签证；无 PDF/导出 | 浏览器 | PASS |
| TC-04 | 真行程存在 | 列表 7 条 ready | 不因缺 Key BLOCKED | `/api/itineraries` | PASS |

## 逐条 AC

### AC-015 PASS

左侧「行程」7 行，无 `[Mock]`。点第 4 行进入 `/itineraries/itn_a79bf0c8d6c0ec62`。把该行程 `conversation_id` 写入本机会话后回首页，点「查看行程」`href=/itineraries/itn_a79bf0c8d6c0ec62`，仍是同一 id。刷新后路径与 5 天报告仍在。

证据：`t011-shots/02-trips.png`、`04-chat-view-trip.png`、`05-detail-from-chat.png`、`06-after-reload.png`；`t011-evidence.json` → `acs.AC-015`。

### AC-005 PASS

杭州 5 天：预算、行前清单、日期 chip、按天卡片同时在。点「地图模式」：`aria-label=当天行程地图`，canvas 764×360，高德网络请求 21 条，瓦片与标注可见（非「地图未配置」空列表）。当天条上的点与第 1 天两张地点卡对应。无 PDF、无护照签证、无 `[Mock]`。

证据：`t011-shots/11-map-mode.png`、`12-map-day1.png`。

### AC-016 PASS

顶部 5 个日期 chip。第 1 天 2 张地点卡，第 5 天 1 张地点卡。

证据：`05-detail-from-chat.png`；`acs.AC-016`。

### AC-021 PASS

首次在展示行程上滚过观察带，chip 曾落到第 4 天（测试滚幅过大，不作产品缺陷）。定向复核改用页面同一套观察带面积算法：

- 从第 1 天逐步下滚，观察带最大可见面积为第 3 天时，chip 高亮「第 3 天」。
- 点「第 3 天」chip：高亮第 3 天，第 3 天区块在视口顶部。
- 再点「第 1 天」chip：滚回第 1 天，高亮第 1 天。

样本为删卡后仍保持第 3 天两张卡的 `itn_e6e7ea18e5abc6c2`（避免吃本轮 AC-018 改短后的单卡天）。

证据：`t011-recheck-021-e6e7.json`；`t011-shots/r3-scroll-day3.png`、`r3-chip-day3.png`、`r3-chip-day1.png`。

范围外：本轮把展示行程第 3 天改成单卡后，再点「第 3 天」会被更高的第 4 天占满观察带，chip 跳到第 4 天。不计入本 AC（验收方法要求的是滚到第 3 天再点回第 1 天）。

### AC-022 PASS

卡间文案为「步行约 15 分钟」「步行约 13 分钟」「公交约 39 分钟」，不是地点名硬接。对应 GET 腿 `source=amap`，含方式、`duration_min`、`distance_m`。本份展示行程没有 `source=estimate` 且含「约」的腿。

证据：`05-detail-from-chat.png`；`acs.AC-022`。

### AC-023 PASS

点第 1 天地点卡：微详情有名称与一段介绍/地址（正文长度 71），无支付/支出金额。关后回到当天列表。

证据：`07-micro-detail.png`、`08-micro-closed.png`。

### AC-007 PASS

打开已有偏低预算页 `itn_8d75be294e483e2a`：预算区可见合计 1280、上限 800、文案「超出上限」。GET `over_cap=true`。未再新出一版。

证据：`13-over-cap.png`。

### AC-006 PASS / AC-017 PASS

在未动过的 `itn_e6e7ea18e5abc6c2` 第 2 天点「更多操作」→「删除」雷峰塔：卡片 2→1，该点标题消失。GET 行程已变。`planning.status=succeeded`，三专员仍 succeeded，无 running。地图模式第 2 天只剩西湖一处点，不再把雷峰塔当天行程点。

首次脚本在同一事件循环里找「删除」未等到菜单，属测试时序，已复核通过。

证据：`r1-after-delete.png`、`r1-map-after-delete.png`；`t011-recheck.json`。

### AC-018 PASS

在 `itn_a79bf0c8d6c0ec62` 侧边发送「第三天不要排那么满」（约 2.0s）。用户气泡出现该句，快捷建议收起。第 3 天卡片 2→1。Coco 回复按第三天只留一个主要点。同一 `itinerary_id`，专员仍 succeeded，无新 running。

证据：`16-after-loosen.png`；`acs.AC-018`。

### AC-019 FAIL

必验：点快捷建议应把该句发给 Coco、其余建议立刻消失、**方案随之更新**。

1. `itn_541d4713e1061407` 点「白天少走路，多坐公交」：用户气泡出现，chip 收起，id 不变。等满 180s，`updated_at` 未变，卡片数未变。侧边出现「Coco 暂时没有回复，请再试一次」。对话里该用户句已在，无后续助手回复。
2. 定向复核：未动过的海南 `itn_63f6c180617024d5` 点「换一家更安静的推荐住宿」。同样：用户句出现、chip 收起、同一 id；180s 内行程未更新；再次「Coco 暂时没有回复，请再试一次」。专员状态仍是上次 succeeded（修订未完成，也没有新 running）。

对照：同一详情侧边手打改（AC-018）走同一 `pushTurn` → POST 原 conversation → GET 同一 itinerary，2s 成功。前端 `sendMessage` 超时 30s。点建议两次都在超时后失败，方案未改。

最短复现：打开一份 ready 行程详情 → 侧边仍有建议 chip → 点其中一条 → 建议消失、用户句出现 → 约 30s 后 Coco 报未回复，GET 行程与点前相同。

修复方向（交 Developer，不改代码）：侧边快捷建议与手打应真正完成 API-004 修订；查 30s 超时是否短于修订、失败是否只写了用户句、错误是否让 `updated_at`/卡片不变。功能失败已证实；超时根因未用后端日志钉死，见经验核对。

证据：`17-after-suggest.png`、`r1-after-suggest.png`；`t011-evidence.json` → `acs.AC-019`；`t011-recheck.json` → `acs.AC-019`。

## 技术检查

- 列表入口与对话「查看行程」同一 `itinerary_id`，刷新仍在：PASS。
- 删卡/侧边改后 GET 已变，专员 succeeded、无 running：PASS。AC-019 未完成修订，故无新 running，但方案也没变。
- 偏低上限 UI「超出上限」且 `over_cap=true`：PASS。
- AC-021 滚到第 3 天再点回第 1 天：PASS（见上）。
- AC-022：展示腿均为 `amap`，文案含方式+约时间；本轮未见「高德失败却写成 estimate+约」的反例。
- 国内清单无护照签证；无 PDF/导出：PASS。
- 已有 T-010 真行程，未 BLOCKED。有 JS Key，地图不是空配置态。

## 经验核对（不落盘）

| 候选 | 核对 | 适用边界 |
| --- | --- | --- |
| 不要 curl Vite `/src` 核 env | **已遵守 / 已验证做法**：本轮只看 DOM 与 `/api`。浏览器自身会加载 Vite 模块，不能把 Network 里的 `/src` 当成 Tester curl。 | Chrome 152 + Vite 开发服 |
| 卡片无金额不要按天数重算预算 | **已验证现象**：偏低预算页合计 1280 / 上限 800 / `over_cap=true`，「超出上限」仍在，未被 5×日均覆盖。未再拆预算重算代码。 | 真行程详情预算区 |
| 日期滚动看观察带面积 | **已验证**：按视口上 45% 面积选天时，chip 与期望天一致；只凭一次 `offsetTop` 硬滚会偏到邻天。 | 行程详情 `.detail-report-body` |
| 插入 service 勿截断旧函数头 | **未验证**：本轮失败不在函数头截断。 | — |
| 侧边改必须 POST 原 conversation 再 GET 同一 itinerary | **部分验证**：AC-018 同 id 且方案变了。AC-019 用户句进了原会话、GET 仍是同一 id，但修订未完成所以卡片没变。 | 详情侧边 `pushTurn` |
| 功能 PASS 不自动证明根因 | **采纳为判定纪律**：AC-018 成功不能推断 AC-019 根因；两次建议失败的超时原因仍是推测。 | 本任务 |

不建议仅凭 AC-019 超时就沉淀「axios 30s 太短」——未核对服务端耗时与错误体。

## 未验项

- 未新开一轮偏低预算规划（已有页已满足 AC-007）。
- 未在无 JS Key 条件下看「地图未配置」（本机已配 Key，按有 Key 路径验瓦片）。
- 未对 AC-019 抓后端修订耗时/错误体（前端已见超时文案与行程未变）。
- 未验换目的地「请去新建计划」大改分支（非本任务必验 AC）。
- 列表页未改，仅作为 AC-015 入口。

## 进程

- Tester 自启 Chrome 152 CDP 9613：**结束时停止**。
- 8099 / 5199：开发残留且仍给后续用，**未停**。

---

# 第 1 次返工复验（2026-09-13）

总结果：**PASS**  
路径：真链路 `VITE_USE_MOCK=false`，页面无 `[Mock]`，未用 Mock 行程顶替。未用开发刚改过的 `itn_15845ef143d2cc56` / `itn_e6e7ea18e5abc6c2` 当唯一样本。未 curl Vite `/src/*.ts`。

## 环境

- 工作目录：`Projects_Repo/Travel_Helper`
- 后端：开发残留 PID 28142（17:21:12 重启加载修订）在本轮开验后已退出，5199 代理 `/api` 变 502。Tester 用项目 `.venv` 按方案命令重新拉起 `127.0.0.1:8099`（PID 32517，cwd=`.../Travel_Helper/backend`，`PYTHONPATH=.. ../.venv/bin/python -m uvicorn src.main:app`）。**本轮 Tester 自启，结束时停止。**
- 前端：复用开发残留 `127.0.0.1:5199`（PID 98000，cwd=`.../Travel_Helper/frontend`，Vite，16:46:48 起）。Tester **未拉起、未停止**。
- Chrome：152.0.7977.84；`--user-data-dir=/tmp/xtrip-t011-r1-chrome`；CDP `127.0.0.1:9614`；开页 `Target.createTarget` + `Target.attachToTarget({flatten:true})`；视口 1440×900。Chip / 发送用 `Input.dispatchMouseEvent`。**Tester 自启，结束时停止。**
- 核环境：只看 DOM 与 `/api`（经 5199 代理到 8099）。未 curl Vite `/src`。
- 样本：AC-019 用上轮失败且本轮未改的杭州 `itn_541d4713e1061407`；AC-018 另选海南 `itn_63f6c180617024d5`（第 3 天仍 2 卡）；抽检偏低预算 `itn_8d75be294e483e2a`。

机器证据：`.sdd/test-reports/t011-retest1.json`；截图 `t011-shots/r1-*.png`。

## 本轮检查表

| ID | 场景 | 动作 | 预期 | 方法 | 结果 |
| --- | --- | --- | --- | --- | --- |
| AC-019 | 未改过且仍显示建议的真行程 | 点「白天少走路，多坐公交」 | 该句进对话、chip 收起、Coco 有回复（非超时文案）、同一 id、交通或卡片可观察变化 | 浏览器点选 + GET | **PASS** |
| AC-018 | 另一份真行程侧边 | 手打「第三天不要排那么满」 | 第三天变少或变松；同一 id | 浏览器发送 + GET | **PASS** |
| 抽检 | 再开一份详情 | 打开报告 | 仍有预算/清单/按天卡 + 地图入口 | 浏览器 | **PASS** |
| AC-005/015/016/021/022/023/007/006/017 | 上轮已 PASS，本轮未改地图/删卡/预算 UI | 不重走全量 | 抽检未推翻 | 抽检 | 沿用上轮 PASS |

## 逐条本轮复验

### AC-019 PASS（上轮 FAIL 已复验）

打开 `itn_541d4713e1061407`，侧边 3 条 chip 都在。点「白天少走路，多坐公交」（CDP 鼠标点在 chip 中心）。约 1.0s：

- 用户气泡出现该句；chip 立即收起。
- Coco 回复「白天这段我改成多坐公交、少走路，还是这一份行程。」**不是**「Coco 暂时没有回复」。
- 同一 `itinerary_id`。专员仍 succeeded，无 running。
- 交通可观察变化：第 1 天「步行约 15 分钟」→「公交约 32 分钟」；第 2/4 天步行腿改为公交。卡片数量未变（本条 chip 改交通，不要求删卡）。`updated_at` 已变。

未再出现上轮约 30s 超时文案。本轮修订约 1s 完成，**不能据此证明 180s 超时上限本身被用到**；只能证明超时文案未再出现，且方案因该 chip 对应的交通映射而变。

证据：`r1-019-before.png`、`r1-019-clicked.png`、`r1-019-after.png`；`t011-retest1.json` → `acs.AC-019`。

### AC-018 PASS（抽检，另一份）

另开 `itn_63f6c180617024d5`（海南，本轮未先点 chip）。手打「第三天不要排那么满」并点发送。约 1.1s：

- 用户句进对话；chip 收起。
- Coco 回复「第三天我帮你排松一点，还是这一份行程。」无超时文案。
- 第 3 天卡片 2→1（去掉其中一处海滩点）。同一 `itinerary_id`。专员 succeeded，无 running。

证据：`r1-018-before.png`、`r1-018-after.png`；`acs.AC-018`。

### 抽检（上轮已 PASS 的报告+地图入口）PASS

打开 `itn_8d75be294e483e2a`：预算（合计 1280 / 上限 800 /「超出上限」）、行前清单、5 个日期 chip、按天卡片同时在；顶部有「地图模式」。无 `[Mock]`、无「地图未配置」。未再点地图瓦片、未再删卡。

证据：`r1-spot-detail.png`。

## 经验核对（不落盘）

| 候选 | 核对 | 适用边界 |
| --- | --- | --- |
| 详情修订与规划共用 API-004 时，前端超时须对齐 180s | **部分验证**：本轮 AC-019/018 均约 1s 完成，超时文案未出现。功能已过，但本轮修订很快，**未验证「必须等到接近 180s」**。上轮 30s 超时症状在本路径消失，不能单独归因于超时数字——见下一行映射。 | 真链路详情侧边 `sendMessage` → API-004 |
| 写死芯片必须能落到修订 operations | **已验证（本条 chip）**：点「白天少走路，多坐公交」后步行腿改为公交，同一 id。**未点**「换一家更安静的推荐住宿」，住宿映射本轮未验。 | 快捷建议原文 → 修订 operations |
| 功能 PASS 不自动证明两处根因都成立 | **采纳**：超时是否仍出现 = 否；方案是否因映射而变 = 是（交通）。两处分开记，不把 1s 成功写成「180s 被证明必要」。 | 本任务返工 |
| 不要 curl Vite `/src` | **已遵守**：Tester 未请求 `/src/*.ts`。Chrome 自行加载 Vite 模块（Network `src_hits=92`）不记作 Tester curl。 | Chrome 152 + Vite 5199 |

建议编排器：可沉淀「芯片原文须映射到修订 operations」；「axios 必须 180s」本轮证据不足，宜暂缓或写清「避免 30s 掐断，本轮未测到长耗时」。

## 未验项

- 未点住宿 chip「换一家更安静的推荐住宿」，住宿映射未独立复验。
- 未制造接近 180s 的慢修订，未证明 180s 上限被用到。
- 未全量重走 AC-005/006/007/015/016/017/021/022/023（上轮 PASS，本轮仅抽检报告+地图入口）。
- 未新开偏低预算规划；抽检页仍显示超出上限。
- 未在无 JS Key 下看「地图未配置」。
- 未验换目的地「请去新建计划」。

## 进程

- Tester 自启 Chrome 152 CDP 9614：**结束时停止**。
- 8099：开发残留已死，Tester 自启 PID 32517：**结束时停止**。
- 5199：开发残留 PID 98000，**未停**。
