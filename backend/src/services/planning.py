"""三专员规划任务：研究成功后再并行预算与行程，经 SSE 推送日志。"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from pycore.core import get_logger
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from src.config.settings import settings
from src.db.models import Conversation, Itinerary, Message, PlanningJob
from src.db.session import get_db_context
from src.models.common import new_id, utcnow
from src.plugins import create_amap_registry
from src.repositories.planning import PlanningRepository
from src.services.activity_log import append_entry, build_entry, event_hub, sanitize_value
from src.services.llm_client import parse_json_object
from src.services.specialists import budget as budget_specialist
from src.services.specialists import itinerary as itinerary_specialist
from src.services.specialists import research as research_specialist

logger = get_logger()

REASON_TEMPLATES = {
    "destination_not_found": "在国内地图里找不到这个目的地，没有可用的景点信息",
    "poi_empty": "检索不到可用景点信息",
    "amap_unavailable": "地图服务不可用，没法完成这次检索",
    "iteration_limit": "研究或排程超时，无法形成结论",
    "model_error": "模型服务不可用",
}
TOOL_TITLES = {
    "geocode_city": "查询城市位置",
    "search_poi": "搜索景点",
    "get_poi_detail": "查看地点详情",
    "get_weather": "读取天气",
    "route_walking": "查询步行路线",
    "route_transit": "查询公交路线",
}
BUDGET_RECOMPUTE_RATIO = 0.2
FORBIDDEN_FAIL_WORDS = {"失败", "失败了", "失败。"}
QWEN_DEFAULT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEEPSEEK_DEFAULT_BASE = "https://api.deepseek.com"
WRITE_LOCK_RETRIES = 5

ChatFn = Callable[..., Awaitable[dict[str, Any]]]
RegistryFn = Callable[[], Any]

_specialist_chat: ChatFn | None = None
_registry_factory: RegistryFn | None = None
_background_tasks: set[asyncio.Task] = set()


def set_planning_hooks(
    *,
    specialist_chat: ChatFn | None = None,
    registry_factory: RegistryFn | None = None,
) -> None:
    global _specialist_chat, _registry_factory
    _specialist_chat = specialist_chat
    _registry_factory = registry_factory


def _secrets() -> list[str]:
    return [
        item
        for item in (
            settings.deepseek_api_key,
            settings.qwen_api_key,
            settings.amap_web_key,
            settings.secret_key,
        )
        if item
    ]


def _specialists_running(destination_city: str | None) -> list[dict[str, Any]]:
    city = destination_city or "目的地"
    return [
        {
            "role": "destination_research",
            "status": "running",
            "summary": f"正在查{city}点位与天气",
        },
        {"role": "budget_expert", "status": "not_started", "summary": None},
        {"role": "itinerary_design", "status": "not_started", "summary": None},
    ]


def _dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _loads(raw: str) -> dict[str, Any]:
    return json.loads(raw)


def _is_locked(exc: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).lower()
        if "database is locked" in text or "database locked" in text:
            return True
        current = current.__cause__ or getattr(current, "orig", None)
        if not isinstance(current, BaseException):
            current = None
    return False


def _provider_base(provider: str) -> str:
    if provider == "qwen":
        return (settings.qwen_base_url or "").strip() or QWEN_DEFAULT_BASE
    return (settings.deepseek_base_url or "").strip() or DEEPSEEK_DEFAULT_BASE


def resolve_reason(reason_code: str | None, reason: str | None) -> str:
    text = (reason or "").strip()
    if text and text not in FORBIDDEN_FAIL_WORDS:
        return text
    return REASON_TEMPLATES.get(reason_code or "", REASON_TEMPLATES["model_error"])


KNOWN_REWRITE_CITIES = frozenset(
    {
        "北京",
        "上海",
        "杭州",
        "苏州",
        "南京",
        "成都",
        "西安",
        "广州",
        "深圳",
        "厦门",
        "青岛",
        "昆明",
        "丽江",
        "大理",
        "桂林",
        "三亚",
        "海口",
    }
)


def _research_rewrote_destination(intake: dict[str, Any], research: dict[str, Any]) -> bool:
    asked = str(intake.get("destination_city") or "").strip()
    got = str(research.get("destination_city") or "").strip()
    if not asked or not research.get("ok") or not got:
        return False
    if asked == got or asked in got or got in asked:
        return False
    return got in KNOWN_REWRITE_CITIES


def assemble_coco_failure(reason: str) -> str:
    return f"🌫️ 这次没法帮你出方案。原因是：{reason}。你可以换一个目的地，或者说得更具体一点再试。"


def assemble_coco_success(city: str | None) -> str:
    dest = city or "目的地"
    return f"✨ 去{dest}的方案已经准备好了，可以去行程详情查看。对话里不贴按天安排。"


def _in_pytest_without_hooks() -> bool:
    return "pytest" in sys.modules and _specialist_chat is None


def _planning_snapshot(
    *,
    status: str,
    specialists: list[dict[str, Any]],
    activity_log: list[dict[str, Any]],
    error_message: str | None,
    itinerary_id: str | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "specialists": specialists,
        "activity_log": activity_log,
        "error_message": error_message,
        "itinerary_id": itinerary_id,
    }


def _updated_payload(planning: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": planning.get("status"),
        "specialists": planning.get("specialists") or [],
        "itinerary_id": planning.get("itinerary_id"),
    }


def _tool_title(name: str, arguments: dict[str, Any]) -> str:
    base = TOOL_TITLES.get(name, "查询地点信息")
    hint = (
        arguments.get("address")
        or arguments.get("keywords")
        or arguments.get("city")
        or arguments.get("id")
        or ""
    )
    hint_text = str(hint).strip()
    if hint_text:
        return f"{base} {hint_text}"
    return base


def _tool_body(name: str, result: Any) -> str:
    if not result:
        error = getattr(result, "error", None) or "这次没有查到结果"
        reason = ""
        if getattr(result, "metadata", None):
            reason = str(result.metadata.get("reason") or "")
        detail = f"{error}"
        if reason:
            detail += f"。原因类型：{reason}"
        return detail
    data = sanitize_value(getattr(result, "data", None), _secrets())
    if name == "search_poi" and isinstance(data, dict):
        pois = data.get("pois") or data.get("items") or []
        if isinstance(pois, list):
            names = [
                str(item.get("name"))
                for item in pois
                if isinstance(item, dict) and item.get("name")
            ]
            if names:
                return "找到：" + "、".join(names[:8])
    if name == "geocode_city" and isinstance(data, dict):
        return f"已定位，adcode={data.get('adcode') or '未知'}"
    if name == "get_weather" and isinstance(data, dict):
        return "已记下近期天气摘要。"
    if name in {"route_walking", "route_transit"} and isinstance(data, dict):
        duration = data.get("duration") or data.get("duration_min")
        return f"路线耗时约 {duration}，已按脱敏摘要记录。" if duration else "已记下路线耗时摘要。"
    if isinstance(data, dict):
        return "已记下该步结果摘要。"
    return "已记下该步结果摘要。"


async def specialist_chat(
    *,
    role: str,
    provider: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    json_object: bool = False,
    thinking_enabled: bool = False,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    if _specialist_chat is not None:
        return await _specialist_chat(
            role=role,
            provider=provider,
            messages=messages,
            tools=tools,
            json_object=json_object,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
        )
    if _in_pytest_without_hooks():
        return {
            "content": _dumps(
                {
                    "ok": False,
                    "reason_code": "model_error",
                    "reason": REASON_TEMPLATES["model_error"],
                }
            ),
            "tool_calls": None,
            "reasoning": None,
        }
    if provider == "qwen":
        api_key = (settings.qwen_api_key or "").strip()
        url = f"{_provider_base('qwen').rstrip('/')}/chat/completions"
        model = settings.qwen_model
        extra: dict[str, Any] = {"enable_thinking": False}
    else:
        api_key = (settings.deepseek_api_key or "").strip()
        url = f"{_provider_base('deepseek').rstrip('/')}/chat/completions"
        model = settings.deepseek_model
        extra = {
            "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
        }
        if thinking_enabled and reasoning_effort:
            extra["reasoning_effort"] = reasoning_effort
    if not api_key:
        return {
            "content": _dumps(
                {
                    "ok": False,
                    "reason_code": "model_error",
                    "reason": REASON_TEMPLATES["model_error"],
                }
            ),
            "tool_calls": None,
            "reasoning": None,
        }
    payload: dict[str, Any] = {"model": model, "messages": messages, **extra}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    elif json_object:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(settings.llm_timeout_seconds)
    attempts = 1 + max(0, settings.llm_max_retries)
    async with httpx.AsyncClient(trust_env=False, timeout=timeout) as client:
        data: dict[str, Any] | None = None
        for attempt in range(attempts):
            try:
                response = await client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException:
                logger.warning("专员模型接口超时", provider=provider, role=role, attempt=attempt + 1)
                if attempt < attempts - 1:
                    await asyncio.sleep(1)
                    continue
                break
            except httpx.HTTPError as exc:
                logger.warning(
                    "专员模型接口网络错误",
                    provider=provider,
                    role=role,
                    attempt=attempt + 1,
                    error_type=type(exc).__name__,
                )
                if attempt < attempts - 1:
                    await asyncio.sleep(1)
                    continue
                break
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning(
                    "专员模型接口可重试错误",
                    provider=provider,
                    role=role,
                    status_code=response.status_code,
                    attempt=attempt + 1,
                )
                if attempt < attempts - 1:
                    await asyncio.sleep(1)
                    continue
                break
            if response.status_code >= 400:
                err_code = None
                try:
                    err_body = response.json()
                    if isinstance(err_body, dict):
                        err = err_body.get("error") or {}
                        if isinstance(err, dict):
                            err_code = err.get("code") or err.get("type")
                except ValueError:
                    err_code = None
                logger.warning(
                    "专员模型接口客户端错误",
                    provider=provider,
                    role=role,
                    status_code=response.status_code,
                    error_code=err_code,
                )
                break
            body = response.json()
            if isinstance(body, dict):
                data = body
                break
        if data is None:
            return {
                "content": _dumps(
                    {
                        "ok": False,
                        "reason_code": "model_error",
                        "reason": REASON_TEMPLATES["model_error"],
                    }
                ),
                "tool_calls": None,
                "reasoning": None,
            }
    choices = data.get("choices") or []
    message = (choices[0].get("message") if choices else {}) or {}
    return {
        "content": message.get("content"),
        "tool_calls": message.get("tool_calls"),
        "reasoning": message.get("reasoning_content") or message.get("reasoning"),
    }


def _registry():
    if _registry_factory is not None:
        return _registry_factory()
    return create_amap_registry(settings=settings)


def _filter_tools(registry, allowed: tuple[str, ...]) -> list[dict[str, Any]]:
    if not allowed:
        return []
    return [
        spec
        for spec in registry.to_specs()
        if spec.get("function", {}).get("name") in allowed
    ]


class _PlanningSession:
    def __init__(
        self,
        conversation_id: str,
        job_id: str,
        intake: dict[str, Any],
        specialists: list[dict[str, Any]],
        activity_log: list[dict[str, Any]],
    ) -> None:
        self.conversation_id = conversation_id
        self.job_id = job_id
        self.intake = intake
        self.lock = asyncio.Lock()
        self.specialists = specialists
        self.activity_log = activity_log
        self.itinerary_id: str | None = None
        self.error_message: str | None = None

    def planning_dict(self, status: str) -> dict[str, Any]:
        return _planning_snapshot(
            status=status,
            specialists=self.specialists,
            activity_log=self.activity_log,
            error_message=self.error_message,
            itinerary_id=self.itinerary_id,
        )

    def set_role(self, role: str, status: str, summary: str | None) -> None:
        for item in self.specialists:
            if item.get("role") == role:
                item["status"] = status
                item["summary"] = summary
                return
        self.specialists.append({"role": role, "status": status, "summary": summary})

    async def _persist_unlocked(
        self,
        db: AsyncSession,
        conversation: Conversation,
        job: PlanningJob,
        status: str,
    ) -> None:
        job.status = status
        job.specialists_json = _dumps(self.specialists)
        job.activity_json = _dumps(self.activity_log)
        job.error_message = self.error_message
        if status in {"succeeded", "failed"}:
            job.finished_at = utcnow()
        planning = self.planning_dict(status)
        conversation.planning_json = _dumps(planning)
        conversation.updated_at = utcnow()
        await db.flush()

    async def write(
        self,
        status: str,
        extra: Callable[[AsyncSession, Conversation], Awaitable[Any]] | None = None,
    ) -> Any:
        last_error: BaseException | None = None
        for attempt in range(WRITE_LOCK_RETRIES):
            try:
                async with get_db_context() as db:
                    conversation = await db.get(Conversation, self.conversation_id)
                    job = await db.get(PlanningJob, self.job_id)
                    if conversation is None or job is None:
                        return None
                    extra_result = await extra(db, conversation) if extra else None
                    await self._persist_unlocked(db, conversation, job, status)
                    return extra_result
            except OperationalError as exc:
                last_error = exc
                if not _is_locked(exc) or attempt == WRITE_LOCK_RETRIES - 1:
                    raise
                await asyncio.sleep(0.15 * (2**attempt))
        if last_error:
            raise last_error
        return None

    async def persist(self, status: str) -> None:
        async with self.lock:
            await self.write(status)

    async def persist_extra(
        self,
        status: str,
        extra: Callable[[AsyncSession, Conversation], Awaitable[Any]],
    ) -> Any:
        async with self.lock:
            return await self.write(status, extra)

    async def publish_updated(self, status: str) -> None:
        await self.persist(status)
        event_hub.publish(
            self.conversation_id,
            "planning.updated",
            _updated_payload(self.planning_dict(status)),
        )

    async def mark_role(self, role: str, status: str, summary: str | None) -> None:
        async with self.lock:
            self.set_role(role, status, summary)
            await self.write("running")

    async def add_log(
        self,
        *,
        kind: str,
        specialist: str,
        title: str,
        body: str | None = None,
        clickable: bool | None = None,
    ) -> dict[str, Any]:
        async with self.lock:
            entry = build_entry(
                kind=kind,
                specialist=specialist,
                title=title,
                body=body,
                clickable=clickable,
                secrets=_secrets(),
            )
            self.activity_log = append_entry(self.activity_log, entry)
            await self.write("running")
        event_hub.publish(self.conversation_id, "planning.log", {"entry": entry})
        return entry

    async def run_loop(
        self,
        *,
        role: str,
        provider: str,
        system_prompt: str,
        user_content: str,
        tools: tuple[str, ...],
        max_iter: int,
        thinking_enabled: bool,
        json_object: bool,
        reasoning_effort: str | None = None,
    ) -> dict[str, Any]:
        registry = _registry()
        tool_specs = _filter_tools(registry, tools)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        last_error: dict[str, Any] | None = None
        rounds = max(1, max_iter)
        for index in range(rounds):
            if index >= max(0, rounds - 2):
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "剩余轮次很少，不要再调用工具，立刻只输出一个符合要求的 json 结论。"
                        ),
                    }
                )
            turn = await specialist_chat(
                role=role,
                provider=provider,
                messages=messages,
                tools=tool_specs or None,
                json_object=json_object,
                thinking_enabled=thinking_enabled,
                reasoning_effort=reasoning_effort,
            )
            reasoning = turn.get("reasoning")
            if isinstance(reasoning, str) and reasoning.strip():
                excerpt = reasoning.strip()[:280]
                await self.add_log(
                    kind="thought",
                    specialist=role,
                    title="思考一步",
                    body=excerpt,
                )
            tool_calls = turn.get("tool_calls") or []
            if tool_calls:
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": turn.get("content") or "",
                    "tool_calls": tool_calls,
                }
                messages.append(assistant_msg)
                for call in tool_calls:
                    function = call.get("function") or {}
                    name = str(function.get("name") or "")
                    raw_args = function.get("arguments") or "{}"
                    try:
                        if isinstance(raw_args, str):
                            arguments = json.loads(raw_args)
                        else:
                            arguments = dict(raw_args)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        arguments = {}
                    if not isinstance(arguments, dict):
                        arguments = {}
                    result = await registry.execute(name, **arguments)
                    await self.add_log(
                        kind="tool",
                        specialist=role,
                        title=_tool_title(name, arguments),
                        body=_tool_body(name, result),
                    )
                    if not result and result is not None:
                        meta = getattr(result, "metadata", None) or {}
                        code = str(meta.get("reason") or "")
                        if code in REASON_TEMPLATES:
                            last_error = {
                                "ok": False,
                                "reason_code": code,
                                "reason": resolve_reason(code, getattr(result, "error", None)),
                            }
                            if name == "geocode_city" and code == "destination_not_found":
                                return last_error
                    observed = (
                        sanitize_value(getattr(result, "data", None), _secrets())
                        if result
                        else None
                    )
                    observed_error = (
                        getattr(result, "error", None)
                        if result is not None and not result
                        else None
                    )
                    observation = {
                        "ok": bool(result),
                        "data": observed,
                        "error": observed_error,
                    }
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id") or new_id("call"),
                            "content": _dumps(observation),
                        }
                    )
                continue
            content = turn.get("content")
            if isinstance(content, str) and content.strip():
                try:
                    parsed = parse_json_object(content)
                except (ValueError, json.JSONDecodeError):
                    last_error = {
                        "ok": False,
                        "reason_code": "model_error",
                        "reason": REASON_TEMPLATES["model_error"],
                    }
                    continue
                if parsed.get("ok") is False:
                    return parsed
                return parsed
        if last_error:
            return last_error
        return {
            "ok": False,
            "reason_code": "iteration_limit",
            "reason": REASON_TEMPLATES["iteration_limit"],
        }


async def _add_coco(db: AsyncSession, conversation_id: str, content: str) -> Message:
    row = Message(
        id=new_id("msg"),
        conversation_id=conversation_id,
        role="assistant",
        content=content,
        created_at=utcnow(),
    )
    db.add(row)
    await db.flush()
    return row


def _build_checklist(city: str | None) -> list[dict[str, Any]]:
    dest = city or "目的地"
    items = [
        "携带身份证",
        "按天气准备季节衣物",
        f"查看{dest}热门景点是否需要预约",
        "市内按公交+适量步行出行",
    ]
    return [{"id": new_id("chk"), "text": text, "relevant": True} for text in items]


def _build_itinerary_payload(
    *,
    itinerary_id: str,
    conversation_id: str,
    intake: dict[str, Any],
    research: dict[str, Any],
    budget: dict[str, Any],
    itinerary: dict[str, Any],
) -> dict[str, Any]:
    city = research.get("destination_city") or intake.get("destination_city")
    days = itinerary.get("days") or []
    map_center = None
    for day in days:
        for card in day.get("cards") or []:
            map_center = {"lng": card["lng"], "lat": card["lat"]}
            break
        if map_center:
            break
    now = utcnow().isoformat(timespec="seconds").replace("+00:00", "Z")
    title = f"{city or '行程'} {intake.get('duration_days') or len(days)} 日"
    if intake.get("pace") == "relaxed":
        title += "轻松游"
    elif intake.get("pace") == "packed":
        title += "紧凑游"
    else:
        title += "行程"
    return {
        "id": itinerary_id,
        "conversation_id": conversation_id,
        "title": title,
        "destination_city": city,
        "origin_city": intake.get("origin_city"),
        "duration_days": intake.get("duration_days") or len(days),
        "pace": intake.get("pace"),
        "companion_type": intake.get("companion_type"),
        "assumptions": ["市内交通按公交+适量步行", "住宿为推荐档，不代订"],
        "days": days,
        "budget": {
            "currency": budget.get("currency") or "CNY",
            "cap_amount": budget.get("cap_amount"),
            "total_amount": budget.get("total_amount"),
            "over_cap": bool(budget.get("over_cap")),
            "includes_note": budget.get("includes_note"),
            "categories": budget.get("categories") or [],
        },
        "checklist": _build_checklist(city),
        "map_center": map_center,
        "quick_suggestions": [
            {"id": new_id("qs"), "text": "第三天不要排那么满"},
            {"id": new_id("qs"), "text": "白天少走路，多坐公交"},
            {"id": new_id("qs"), "text": "换一家更安静的推荐住宿"},
        ],
        "status": "ready",
        "created_at": now,
        "updated_at": now,
    }


async def _fail(
    session: _PlanningSession,
    *,
    role: str,
    result: dict[str, Any],
    keep_others: bool = False,
) -> None:
    reason = resolve_reason(result.get("reason_code"), result.get("reason"))
    session.set_role(role, "failed", result.get("summary") or reason)
    if not keep_others:
        for item in session.specialists:
            if item["role"] != role and item.get("status") == "not_started":
                continue
            if item["role"] != role and item.get("status") == "running":
                item["status"] = "not_started"
                item["summary"] = None
    await session.add_log(
        kind="specialist",
        specialist=role,
        title="这一步没有完成",
        body=reason,
    )
    session.error_message = reason

    async def extra(db: AsyncSession, conversation: Conversation) -> Message:
        return await _add_coco(db, conversation.id, assemble_coco_failure(reason))

    coco = await session.persist_extra("failed", extra)
    event_hub.publish(
        session.conversation_id,
        "planning.failed",
        {
            "status": "failed",
            "itinerary_id": None,
            "failure_reason": reason,
            "coco_message_id": coco.id if coco is not None else None,
            "specialists": session.specialists,
        },
    )


async def _succeed(
    session: _PlanningSession,
    *,
    research: dict[str, Any],
    budget: dict[str, Any],
    itinerary: dict[str, Any],
) -> None:
    itinerary_id = new_id("itn")
    payload = _build_itinerary_payload(
        itinerary_id=itinerary_id,
        conversation_id=session.conversation_id,
        intake=session.intake,
        research=research,
        budget=budget,
        itinerary=itinerary,
    )
    session.itinerary_id = itinerary_id
    city = payload.get("destination_city")

    async def extra(db: AsyncSession, _conversation: Conversation) -> Message:
        db.add(
            Itinerary(
                id=itinerary_id,
                conversation_id=session.conversation_id,
                payload_json=_dumps(payload),
                status="ready",
                title=payload["title"],
                destination_city=payload.get("destination_city"),
                duration_days=payload.get("duration_days"),
                pace=payload.get("pace"),
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
        return await _add_coco(db, session.conversation_id, assemble_coco_success(city))

    await session.persist_extra("succeeded", extra)
    event_hub.publish(
        session.conversation_id,
        "itinerary.ready",
        {
            "status": "succeeded",
            "itinerary_id": itinerary_id,
            "specialists": session.specialists,
        },
    )


async def execute_planning(conversation_id: str, job_id: str) -> None:
    async with get_db_context() as db:
        conversation = await db.get(Conversation, conversation_id)
        job = await db.get(PlanningJob, job_id)
        if conversation is None or job is None:
            return
        intake = _loads(conversation.intake_json)
        specialists = _loads(job.specialists_json)
        activity_log = _loads(job.activity_json or "[]")
    session = _PlanningSession(
        conversation_id,
        job_id,
        intake,
        specialists,
        activity_log,
    )
    await session.publish_updated("running")

    async def run_loop(**kwargs: Any) -> dict[str, Any]:
        return await session.run_loop(**kwargs)

    research = await research_specialist.run_research(intake, run_loop=run_loop)
    if _research_rewrote_destination(intake, research):
        research = {
            "ok": False,
            "reason_code": "destination_not_found",
            "reason": REASON_TEMPLATES["destination_not_found"],
            "summary": REASON_TEMPLATES["destination_not_found"],
        }
    if not research.get("ok"):
        await _fail(session, role="destination_research", result=research)
        return
    await session.mark_role("destination_research", "succeeded", research.get("summary"))
    await session.add_log(
        kind="specialist",
        specialist="destination_research",
        title="目的地研究已完成",
        body=research.get("summary") or "点位与天气可用",
    )
    await session.mark_role("budget_expert", "running", "正在估算花费")
    await session.mark_role("itinerary_design", "running", "正在排每天行程")
    await session.publish_updated("running")

    async def _budget() -> dict[str, Any]:
        result = await budget_specialist.run_budget(
            intake, research, None, run_loop=run_loop
        )
        if result.get("ok"):
            await session.mark_role("budget_expert", "succeeded", result.get("summary"))
            await session.add_log(
                kind="specialist",
                specialist="budget_expert",
                title="预算估算已完成",
                body=result.get("summary"),
            )
        return result

    async def _itinerary() -> dict[str, Any]:
        result = await itinerary_specialist.run_itinerary(
            intake, research, run_loop=run_loop
        )
        if result.get("ok"):
            await session.mark_role("itinerary_design", "succeeded", result.get("summary"))
            await session.add_log(
                kind="specialist",
                specialist="itinerary_design",
                title="行程设计已完成",
                body=result.get("summary"),
            )
        return result

    budget_result, itinerary_result = await asyncio.gather(_budget(), _itinerary())
    if not budget_result.get("ok"):
        await _fail(session, role="budget_expert", result=budget_result, keep_others=True)
        return
    if not itinerary_result.get("ok"):
        await _fail(session, role="itinerary_design", result=itinerary_result, keep_others=True)
        return

    first_total = float(budget_result.get("total_amount") or 0)
    days = itinerary_result.get("days") or []
    draft_total = 0.0
    has_card_amount = False
    for day in days:
        for card in day.get("cards") or []:
            if card.get("amount") is None:
                continue
            try:
                draft_total += float(card.get("amount") or 0)
                has_card_amount = True
            except (TypeError, ValueError):
                continue
    if has_card_amount and first_total > 0:
        if abs(draft_total - first_total) / first_total > BUDGET_RECOMPUTE_RATIO:
            recomputed = await budget_specialist.run_budget(
                intake,
                research,
                {"days": days},
                run_loop=run_loop,
            )
            if recomputed.get("ok"):
                budget_result = recomputed
                await session.mark_role("budget_expert", "succeeded", recomputed.get("summary"))

    await _succeed(
        session,
        research=research,
        budget=budget_result,
        itinerary=itinerary_result,
    )


async def _run_job(conversation_id: str, job_id: str) -> None:
    try:
        retries = 8
        delay = 0.05
        for _ in range(retries):
            if delay:
                await asyncio.sleep(delay)
            else:
                await asyncio.sleep(0)
            async with get_db_context() as db:
                job = await db.get(PlanningJob, job_id)
                if job is None:
                    continue
            await asyncio.wait_for(
                execute_planning(conversation_id, job_id),
                timeout=settings.planning_timeout_seconds,
            )
            return
    except TimeoutError:
        async with get_db_context() as db:
            conversation = await db.get(Conversation, conversation_id)
            job = await db.get(PlanningJob, job_id)
            if conversation is None or job is None:
                return
            intake = _loads(conversation.intake_json)
            specialists = _loads(job.specialists_json)
            activity_log = _loads(job.activity_json or "[]")
        session = _PlanningSession(
            conversation_id,
            job_id,
            intake,
            specialists,
            activity_log,
        )
        await _fail(
            session,
            role="destination_research",
            result={
                "ok": False,
                "reason_code": "iteration_limit",
                "reason": REASON_TEMPLATES["iteration_limit"],
                "summary": REASON_TEMPLATES["iteration_limit"],
            },
        )
    except Exception:
        logger.exception("规划后台任务异常", conversation_id=conversation_id)


def _schedule(conversation_id: str, job_id: str) -> None:
    task = asyncio.create_task(_run_job(conversation_id, job_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def wait_background_tasks() -> None:
    pending = [task for task in _background_tasks if not task.done()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def start_planning_stub(
    conversation: Conversation,
    intake: dict[str, Any],
    *,
    planning_repo: PlanningRepository,
) -> dict[str, Any]:
    """创建 planning_job 并后台跑三专员；同步返回 running。"""
    existing = await planning_repo.get_running(conversation.id)
    if existing is not None:
        specialists = _loads(existing.specialists_json)
        activity = _loads(existing.activity_json or "[]")
        return _planning_snapshot(
            status="running",
            specialists=specialists,
            activity_log=activity,
            error_message=None,
            itinerary_id=None,
        )
    specialists = _specialists_running(intake.get("destination_city"))
    job = PlanningJob(
        id=new_id("job"),
        conversation_id=conversation.id,
        status="running",
        specialists_json=_dumps(specialists),
        activity_json="[]",
        error_message=None,
        started_at=utcnow(),
        finished_at=None,
    )
    await planning_repo.create(job)
    logger.info("规划任务已创建", conversation_id=conversation.id, job_id=job.id)
    _schedule(conversation.id, job.id)
    return _planning_snapshot(
        status="running",
        specialists=specialists,
        activity_log=[],
        error_message=None,
        itinerary_id=None,
    )


async def load_planning_view(db: AsyncSession, conversation_id: str) -> dict[str, Any] | None:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        return None
    planning = _loads(conversation.planning_json)
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.role == "assistant")
        .order_by(Message.created_at.desc())
    )
    last_coco = result.scalars().first()
    planning["coco_message_id"] = last_coco.id if last_coco else None
    return planning
