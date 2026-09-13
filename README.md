# Xtrip（Travel_Helper）

本项目由 SDD Harness 管理。身份、项目类型和规范选择见 `.sdd/project.json`。

- `docs/PRD.md`：需求、业务规则和验收标准。
- `docs/tech-spec.md`：技术方案、接口与数据约定。
- `.sdd/tasks.json`：任务和运行状态，由编排器维护。
- `docs/ui-style.md`：有界面时的设计风格，由 UI Skill 生成并供实现、验收引用。
- `docs/prototypes/`：可选界面设计。
- `.sdd/`：阶段摘要、工作日志、经验与验证报告。

`specification` 为集合名称时按需读取该集合，为 `null` 时不加载规范集。核心工作规则位于 Harness 根目录；本项目 `AGENTS.md` 提供轻量入口。

## 本地运行

密钥只放本机 `backend/.env` 与 `frontend/.env`，不要写进文档。`frontend/.env` 中 `VITE_USE_MOCK=false` 走真后台。

```bash
cd backend && PYTHONPATH=.. ../.venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8099
cd frontend && npm run dev -- --host 127.0.0.1 --port 5199
```

打开 [http://127.0.0.1:5199/](http://127.0.0.1:5199/) 。页面上不应再有 `[Mock]`。用户验收端口是前端 5175 / 后端 8003，本轮联调用的是 5199 / 8099。

已知限制：开聊后右栏会换成地图，但不会跟着 Coco 的回复飞到城市或按行程打点；本期验收未含出境。

## 页面功能导航（交付）

入口（相对本仓库根目录）：

- 页面：`docs/project-console.html`
- 结构化数据：`docs/project-map.json`

覆盖实际路由：工作台 `/`、行程列表 `/trips`、行程详情 `/itineraries/:id`。按页面组织功能，不是旧六区管理看板，也不维护任务状态。

### 打开

静态打开即可，不必调业务 API、不必填真实 Key：

```bash
open docs/project-console.html
```

或用系统文件管理器双击该 HTML。页面内嵌了一份核对过的 map，`file://` 也能看。

若要用「重新加载 project-map.json」抓取同目录 JSON（避免只看内嵌副本）：

```bash
cd docs
python3 -m http.server 8765
```

浏览器打开 `http://127.0.0.1:8765/project-console.html`。

### 刷新

1. 只改可机器摘录的字段（路由、method/URL、配置默认值、来源路径）时：更新 `docs/project-map.json` 后，用上面的静态服务打开页面并点「重新加载 project-map.json」；或用「选择 map 文件」加载新 JSON。
2. 人工归纳的算法（问诊 ready、followup、专员工具循环、芯片映射等）对应源码指纹变化时：先把该算法标成「来源已变化待复核」，定向重读源码后再改核对基线。不能只改刷新时间冒充已重新核对。
3. 来源缺失或 JSON 解析失败必须在页面上降级提示，过期算法不得继续标「源码已核对」。

页面自带隔离样例（不改业务代码）：

- 「样例：源变更」：`manager.py` 指纹对不上，问诊/发消息改为待复核。
- 「样例：来源缺失」：出现「导出 PDF（未找到实现）」和缺失路径提示。
- 「样例：解析错误」：展示转义后的非法 JSON 与解析失败原因，不再渲染已核对算法。

配置只列字段名与 `backend/src/config/settings.py`、`backend/.env.example`、`frontend/.env.example` 的源码默认值，不读取真实 `.env`，不展示密钥。
