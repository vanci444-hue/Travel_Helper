"""规划经理 Coco：问诊槽合并、最小集硬校验与会话编排。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pycore.core import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from src.config.settings import settings
from src.db.models import Conversation, Message
from src.models.common import (
    CONTINUE_HINTS,
    PACE_ALIASES,
    ManagerUnavailableError,
    MissingModelKeyError,
    NotFoundError,
    ValidationAppError,
    new_id,
    utc_iso,
    utcnow,
)
from src.models.conversation import (
    ConversationCreate,
    ConversationListItem,
    ConversationListPlanning,
    ConversationPublic,
    IntakePublic,
    MessageCreate,
    MessagePublic,
    MessageTurnPublic,
    PlanningPublic,
    SpecialistPublic,
)
from src.repositories.conversations import ConversationRepository
from src.repositories.itineraries import ItineraryRepository
from src.repositories.messages import MessageRepository
from src.repositories.planning import PlanningRepository
from src.services import llm_client
from src.services.planning import start_planning_stub
from src.services.revision import (
    NEW_PLAN_REPLY,
    REVISED_REPLY,
    UNMAPPED_REPLY,
    ItineraryService,
    is_major_replan,
    itinerary_summary,
    known_revision_operations,
    loads_payload,
    reply_for_known_operations,
)

logger = get_logger()

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "manager_intake.md"
REVISE_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "manager_revise.md"

DOMESTIC_CITIES = {
    "北京",
    "上海",
    "天津",
    "重庆",
    "杭州",
    "苏州",
    "南京",
    "成都",
    "西安",
    "广州",
    "深圳",
    "厦门",
    "青岛",
    "大连",
    "哈尔滨",
    "昆明",
    "丽江",
    "大理",
    "桂林",
    "三亚",
    "海口",
    "长沙",
    "武汉",
    "郑州",
    "济南",
    "合肥",
    "福州",
    "南昌",
    "太原",
    "石家庄",
    "沈阳",
    "长春",
    "南宁",
    "贵阳",
    "兰州",
    "西宁",
    "银川",
    "乌鲁木齐",
    "呼和浩特",
    "拉萨",
    "黄山",
    "张家界",
    "威海",
    "烟台",
    "北戴河",
    "秦皇岛",
    "无锡",
    "宁波",
    "扬州",
    "嘉兴",
}

OUTBOUND_MARKERS = ("出国", "出境", "国外", "海外")
DOMESTIC_MARKERS = ("国内",)
SEA_WISH_MARKERS = ("想看海", "看海", "海边", "海滩", "海滨")
DEFAULT_SEA_CITY = "青岛"
DEFAULT_CHILD_AGE_BAND = "学龄儿童"
OUTBOUND_PLACES = (
    "日本",
    "韩国",
    "泰国",
    "新加坡",
    "马来西亚",
    "欧洲",
    "东南亚",
    "京都",
    "大阪",
    "东京",
    "巴黎",
    "伦敦",
)

MISSING_LABELS = {
    "origin_city": "出发城市",
    "region": "国内或出境",
    "duration_days": "出行时长",
    "companion": "和谁同行",
    "budget": "预算",
    "pace": "节奏",
    "destination_or_wish": "目的地或旅行想法",
    "children_age_bands": "儿童年龄段",
    "destination_city": "目的地城市",
}


def empty_intake() -> dict[str, Any]:
    return {
        "origin_city": None,
        "region": None,
        "destination_text": None,
        "destination_city": None,
        "duration_days": None,
        "date_start": None,
        "date_end": None,
        "date_month": None,
        "companion_type": None,
        "adults": None,
        "children": 0,
        "children_age_bands": [],
        "budget_amount_cny": None,
        "budget_tier": None,
        "budget_includes": "domestic_transport_and_local",
        "pace": None,
        "wish_text": None,
        "missing_fields": [],
        "followup_rounds_used": 0,
        "ready": False,
    }


def default_planning() -> dict[str, Any]:
    return {
        "status": "idle",
        "specialists": [
            {"role": "destination_research", "status": "not_started", "summary": None},
            {"role": "budget_expert", "status": "not_started", "summary": None},
            {"role": "itinerary_design", "status": "not_started", "summary": None},
        ],
        "activity_log": [],
        "error_message": None,
        "itinerary_id": None,
    }


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False


def _has_companion(intake: dict[str, Any]) -> bool:
    companion = intake.get("companion_type")
    if companion in {"solo", "couple", "family", "friends", "parent_child"}:
        return True
    adults = intake.get("adults") or 0
    children = intake.get("children") or 0
    return adults + children >= 1


def _has_budget(intake: dict[str, Any]) -> bool:
    amount = intake.get("budget_amount_cny")
    tier = intake.get("budget_tier")
    return amount is not None or not _is_blank(tier)


def _has_destination_or_wish(intake: dict[str, Any]) -> bool:
    return not _is_blank(intake.get("destination_city")) or not _is_blank(
        intake.get("wish_text")
    ) or not _is_blank(intake.get("destination_text"))


def _needs_child_ages(intake: dict[str, Any]) -> bool:
    if intake.get("companion_type") == "parent_child":
        return True
    return (intake.get("children") or 0) > 0


def _intake_text_blob(intake: dict[str, Any]) -> str:
    return "".join(
        str(intake.get(key) or "")
        for key in ("destination_city", "destination_text", "wish_text")
    )


def _has_sea_wish(intake: dict[str, Any]) -> bool:
    blob = _intake_text_blob(intake)
    return any(marker in blob for marker in SEA_WISH_MARKERS)


def _is_placeholder_destination(value: Any) -> bool:
    if _is_blank(value) or not isinstance(value, str):
        return False
    if value in DOMESTIC_CITIES or value in OUTBOUND_PLACES:
        return False
    return any(marker in value for marker in SEA_WISH_MARKERS)


def _is_named_destination(value: Any) -> bool:
    return (
        isinstance(value, str)
        and not _is_blank(value)
        and not _is_placeholder_destination(value)
    )


def _infer_region(intake: dict[str, Any]) -> str | None:
    if intake.get("region") in {"domestic", "outbound"}:
        return intake["region"]
    dest = intake.get("destination_city") or ""
    text = intake.get("destination_text") or ""
    blob = _intake_text_blob(intake)
    if dest in OUTBOUND_PLACES or any(place in blob for place in OUTBOUND_PLACES):
        return "outbound"
    if any(marker in blob for marker in OUTBOUND_MARKERS):
        return "outbound"
    if dest in DOMESTIC_CITIES or text in DOMESTIC_CITIES:
        return "domestic"
    if any(marker in blob for marker in DOMESTIC_MARKERS):
        return "domestic"
    if _has_sea_wish(intake):
        return "domestic"
    if _is_named_destination(dest) or _is_named_destination(text):
        return "domestic"
    return None


def _apply_hard_defaults(intake: dict[str, Any]) -> dict[str, Any]:
    dest = intake.get("destination_city")
    if _is_placeholder_destination(dest):
        if _is_blank(intake.get("wish_text")):
            intake["wish_text"] = dest
        intake["destination_city"] = None
        if intake.get("destination_text") == dest:
            intake["destination_text"] = None
    intake["region"] = _infer_region(intake)
    if _needs_child_ages(intake) and not intake.get("children_age_bands"):
        intake["children_age_bands"] = [DEFAULT_CHILD_AGE_BAND]
    if (
        intake.get("region") == "domestic"
        and _is_blank(intake.get("destination_city"))
        and _has_sea_wish(intake)
    ):
        intake["destination_city"] = DEFAULT_SEA_CITY
        if _is_blank(intake.get("destination_text")):
            intake["destination_text"] = DEFAULT_SEA_CITY
    return intake


def compute_missing_fields(intake: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if _is_blank(intake.get("origin_city")):
        missing.append("origin_city")
    region = _infer_region(intake)
    if region is None:
        missing.append("region")
    if intake.get("duration_days") is None and _is_blank(intake.get("date_month")):
        missing.append("duration_days")
    if not _has_companion(intake):
        missing.append("companion")
    if not _has_budget(intake):
        missing.append("budget")
    if _is_blank(intake.get("pace")):
        missing.append("pace")
    if not _has_destination_or_wish(intake):
        missing.append("destination_or_wish")
    if _needs_child_ages(intake) and not intake.get("children_age_bands"):
        missing.append("children_age_bands")
    if region == "domestic" and _is_blank(intake.get("destination_city")):
        if _is_blank(intake.get("wish_text")) and _is_blank(intake.get("destination_text")):
            missing.append("destination_city")
        elif "destination_city" not in missing and _is_blank(intake.get("destination_city")):
            # 有画面但无城市：可由经理推荐后补齐，未推荐前仍缺
            missing.append("destination_city")
    if region == "outbound":
        dest = f"{intake.get('destination_city') or ''}{intake.get('destination_text') or ''}"
        if not any(place in dest for place in OUTBOUND_PLACES):
            if "destination_city" not in missing:
                missing.append("destination_city")
    return missing


def finalize_intake(intake: dict[str, Any]) -> dict[str, Any]:
    merged = {**empty_intake(), **intake}
    if merged.get("children") is None:
        merged["children"] = 0
    if merged.get("children_age_bands") is None:
        merged["children_age_bands"] = []
    if (
        merged.get("companion_type") == "couple"
        and merged.get("adults") is None
    ):
        merged["adults"] = 2
    _apply_hard_defaults(merged)
    missing = compute_missing_fields(merged)
    merged["missing_fields"] = missing
    merged["ready"] = len(missing) == 0
    merged["followup_rounds_used"] = int(merged.get("followup_rounds_used") or 0)
    return merged


def merge_intake(base: dict[str, Any], patch: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    if not patch:
        return finalize_intake(merged)
    for key, value in patch.items():
        if key in {"missing_fields", "ready", "followup_rounds_used"}:
            continue
        if _is_blank(value):
            continue
        if key == "pace":
            mapped = PACE_ALIASES.get(str(value).strip())
            if mapped is None:
                continue
            merged[key] = mapped
            continue
        if key == "children_age_bands" and isinstance(value, list):
            merged[key] = [str(item) for item in value if str(item).strip()]
            continue
        merged[key] = value
    return finalize_intake(merged)


def _parse_budget(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*万", text)
    if match:
        return float(match.group(1)) * 10000
    match = re.search(r"(\d+(?:\.\d+)?)\s*千", text)
    if match:
        return float(match.group(1)) * 1000
    match = re.search(r"预算\s*(\d+(?:\.\d+)?)", text)
    if match:
        return float(match.group(1))
    return None


def extract_from_text(text: str) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    origin_match = re.search(r"从([^，,。\s]{2,8})出发", text)
    if origin_match:
        patch["origin_city"] = origin_match.group(1)
    dest_match = re.search(r"去([^，,。\s玩]{2,16})", text)
    if dest_match:
        city = dest_match.group(1)
        if not _is_placeholder_destination(city):
            patch["destination_city"] = city
            patch["destination_text"] = city
    if "destination_city" not in patch:
        persist_match = re.search(r"按([^，,。\s]{2,16})出方案", text)
        if persist_match:
            city = persist_match.group(1)
            if not _is_placeholder_destination(city):
                patch["destination_city"] = city
                patch["destination_text"] = city
    days_match = re.search(r"(\d{1,2})\s*天", text)
    if days_match:
        patch["duration_days"] = int(days_match.group(1))
    budget = _parse_budget(text)
    if budget is not None:
        patch["budget_amount_cny"] = budget
    if any(marker in text for marker in ("预算不限", "没有上限", "不限预算")) or re.search(
        r"预算\s*不限", text
    ):
        patch["budget_tier"] = "premium"
    if (
        "不要太赶" in text
        or "自由探索" in text
        or "别太赶" in text
        or "轻松" in text
        or "放松" in text
    ):
        patch["pace"] = "relaxed"
    elif "特种兵" in text or "打卡" in text or "快速" in text or "紧凑" in text:
        patch["pace"] = "packed"
    elif "一般" in text or "适中" in text:
        patch["pace"] = "moderate"
    if "带老婆" in text or "带配偶" in text or "和老婆" in text or "情侣" in text:
        patch["companion_type"] = "couple"
        patch["adults"] = 2
        patch["children"] = 0
    elif "带小孩" in text or "亲子" in text or "带孩子" in text:
        patch["companion_type"] = "parent_child"
        if patch.get("adults") is None:
            patch["adults"] = 2
        if "children" not in patch:
            patch["children"] = 1
    elif "一个人" in text or "自己" in text:
        patch["companion_type"] = "solo"
        patch["adults"] = 1
    elif "朋友" in text:
        patch["companion_type"] = "friends"
    elif "家人" in text or "家庭" in text:
        patch["companion_type"] = "family"
    age_match = re.search(r"(\d{1,2})\s*岁", text)
    if age_match:
        patch["children_age_bands"] = [f"{age_match.group(1)}岁"]
    if any(marker in text for marker in OUTBOUND_MARKERS) and "destination_city" not in patch:
        patch["region"] = "outbound"
    elif any(marker in text for marker in DOMESTIC_MARKERS):
        patch["region"] = "domestic"
    cities_in_text = [city for city in DOMESTIC_CITIES if city in text]
    if "origin_city" not in patch and cities_in_text:
        if "出发" in text:
            patch["origin_city"] = cities_in_text[0]
        elif "destination_city" not in patch and len(cities_in_text) == 1:
            patch["destination_city"] = cities_in_text[0]
            patch["destination_text"] = cities_in_text[0]
    if "destination_city" not in patch and len(cities_in_text) >= 2:
        patch["destination_city"] = cities_in_text[-1]
        patch["destination_text"] = cities_in_text[-1]
        if "origin_city" not in patch:
            patch["origin_city"] = cities_in_text[0]
    if "wish_text" not in patch:
        wish_bits = []
        for phrase in ("想看海", "看海", "海边", "吃吃走走", "不要太赶", "别太赶", "想出去玩"):
            if phrase in text:
                wish_bits.append(phrase)
        if wish_bits:
            patch["wish_text"] = "，".join(wish_bits)
        elif len(text.strip()) >= 4 and not any(
            key in patch for key in ("destination_city", "origin_city")
        ):
            patch["wish_text"] = text.strip()[:200]
    return patch


def apply_create_payload(payload: ConversationCreate | None) -> dict[str, Any]:
    intake = empty_intake()
    if payload is None:
        return finalize_intake(intake)
    data = payload.model_dump(exclude_none=True)
    if data.get("destination_city") and not data.get("destination_text"):
        data["destination_text"] = data["destination_city"]
    return merge_intake(intake, data)


def conversation_title(intake: dict[str, Any]) -> str:
    city = intake.get("destination_city")
    days = intake.get("duration_days")
    if city and days:
        return f"{city} {days} 天"
    if city:
        return str(city)
    return "新对话"


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _loads(raw: str) -> dict[str, Any]:
    return json.loads(raw)


def _intake_public(raw: dict[str, Any]) -> IntakePublic:
    return IntakePublic.model_validate(finalize_intake(raw))


def _planning_public(raw: dict[str, Any]) -> PlanningPublic:
    specialists = [
        SpecialistPublic.model_validate(item) for item in raw.get("specialists") or []
    ]
    return PlanningPublic(
        status=raw.get("status") or "idle",
        specialists=specialists,
        activity_log=raw.get("activity_log") or [],
        error_message=raw.get("error_message"),
        itinerary_id=raw.get("itinerary_id"),
    )


def _message_public(row: Message) -> MessagePublic:
    display = None
    if row.role == "assistant":
        display = "Coco"
    elif row.role == "user":
        display = "我"
    return MessagePublic(
        id=row.id,
        role=row.role,  # type: ignore[arg-type]
        content=row.content,
        created_at=utc_iso(row.created_at),
        display_name=display,
    )


def _to_public(
    conversation: Conversation, messages: list[Message]
) -> ConversationPublic:
    intake = finalize_intake(_loads(conversation.intake_json))
    planning = _loads(conversation.planning_json)
    return ConversationPublic(
        id=conversation.id,
        title=conversation.title,
        intake=_intake_public(intake),
        map_hint=None,
        planning=_planning_public(planning),
        messages=[_message_public(item) for item in messages],
        created_at=utc_iso(conversation.created_at),
        updated_at=utc_iso(conversation.updated_at),
    )


def _is_continue_message(content: str) -> bool:
    return any(hint in content for hint in CONTINUE_HINTS)


def _normalize_manager_output(raw: dict[str, Any]) -> dict[str, Any]:
    action = str(raw.get("action") or "ask")
    if action not in {"ask", "ready", "stop", "revise", "suggest_new_plan"}:
        action = "ask"
    reply = str(raw.get("reply") or "").strip()
    patch = raw.get("intake_patch")
    if not isinstance(patch, dict):
        patch = {}
    recommended = raw.get("recommended_destination")
    if isinstance(recommended, str) and recommended.strip():
        recommended = recommended.strip()
    else:
        recommended = None
    operations = raw.get("operations")
    if not isinstance(operations, list):
        operations = []
    return {
        "action": action,
        "reply": reply,
        "intake_patch": patch,
        "recommended_destination": recommended,
        "operations": [item for item in operations if isinstance(item, dict) and item.get("op")],
    }


def _force_stop_reply(intake: dict[str, Any]) -> str:
    labels = [MISSING_LABELS.get(item, item) for item in intake.get("missing_fields") or []]
    missing = "、".join(labels) if labels else "出发地或时长"
    return f"📌 还缺{missing}，这轮先不出假装完整的旅行计划。你补一下出发地或天数，我再帮你安排。"


def _wait_reply() -> str:
    return "⏳ 专员还在做，完成后会放到行程里。"


def _reply_blocks_ready(reply: str) -> bool:
    blockers = (
        "几岁",
        "国内还是",
        "还是出境",
        "还是想出境",
        "出国吗",
        "哪座城",
        "哪座城市",
        "哪个城市",
        "哪一区域",
        "对应哪",
    )
    return any(marker in reply for marker in blockers)


def _drop_destination_rewrite(
    named: str | None, patch: dict[str, Any], recommended: str | None
) -> tuple[dict[str, Any], str | None]:
    if not _is_named_destination(named):
        return patch, recommended
    cleaned = dict(patch)
    for key in ("destination_city", "destination_text"):
        value = cleaned.get(key)
        if value and value != named and value in DOMESTIC_CITIES:
            cleaned.pop(key, None)
    if recommended and recommended != named:
        recommended = None
    return cleaned, recommended


def _assumed_ready_reply(intake: dict[str, Any]) -> str:
    city = intake.get("destination_city") or DEFAULT_SEA_CITY
    ages = intake.get("children_age_bands") or [DEFAULT_CHILD_AGE_BAND]
    return (
        f"🧭 按带小孩、看海、别太赶来，我推荐{city}，孩子先按{ages[0]}排。"
        "信息齐了，我这就让专员出一版。"
    )


class ManagerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.conversations = ConversationRepository(db)
        self.messages = MessageRepository(db)
        self.planning = PlanningRepository(db)
        self.itineraries = ItineraryRepository(db)

    async def create(self, payload: ConversationCreate | None) -> ConversationPublic:
        intake = apply_create_payload(payload)
        now = utcnow()
        conversation = Conversation(
            id=new_id("conv"),
            title=conversation_title(intake),
            intake_json=_dumps(intake),
            planning_json=_dumps(default_planning()),
            created_at=now,
            updated_at=now,
        )
        await self.conversations.create(conversation)
        logger.info("新建对话成功", conversation_id=conversation.id)
        return _to_public(conversation, [])

    async def list_items(self, page: int, page_size: int) -> tuple[list[ConversationListItem], int]:
        rows, total = await self.conversations.list_page(
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        items: list[ConversationListItem] = []
        for row in rows:
            planning = _loads(row.planning_json)
            items.append(
                ConversationListItem(
                    id=row.id,
                    title=row.title,
                    updated_at=utc_iso(row.updated_at),
                    planning=ConversationListPlanning(status=planning.get("status") or "idle"),
                    itinerary_id=planning.get("itinerary_id"),
                )
            )
        return items, total

    async def get(self, conversation_id: str) -> ConversationPublic:
        conversation = await self.conversations.get(conversation_id)
        if conversation is None:
            raise NotFoundError()
        messages = await self.messages.list_by_conversation(conversation_id)
        return _to_public(conversation, messages)

    async def send_message(
        self, conversation_id: str, payload: MessageCreate
    ) -> MessageTurnPublic:
        conversation = await self.conversations.get(conversation_id)
        if conversation is None:
            raise NotFoundError()
        content = payload.content.strip()
        if not content:
            raise ValidationAppError("消息不能为空")
        user_row = Message(
            id=new_id("msg"),
            conversation_id=conversation_id,
            role="user",
            content=content,
            created_at=utcnow(),
        )
        await self.messages.create(user_row)
        logger.info("用户消息已落库", conversation_id=conversation_id, message_id=user_row.id)

        intake = finalize_intake(_loads(conversation.intake_json))
        planning = _loads(conversation.planning_json)
        history = await self.messages.list_by_conversation(conversation_id)

        if planning.get("status") == "running":
            assistant_row = await self._add_assistant(conversation_id, _wait_reply())
            await self.conversations.save(conversation)
            return self._turn(user_row, assistant_row, intake, planning)

        ready_itinerary = await self.itineraries.get_ready_by_conversation(conversation_id)
        if ready_itinerary is not None and not _is_continue_message(content):
            return await self._revise(
                conversation,
                user_row,
                content,
                intake,
                planning,
                ready_itinerary,
            )

        user_blob = "\n".join(
            item.content for item in history if item.role == "user" and item.content
        )
        extracted = extract_from_text(user_blob or content)
        locked_dest = extracted.get("destination_city")
        if not _is_named_destination(locked_dest):
            locked_dest = intake.get("destination_city")
        intake = merge_intake(intake, extracted)
        if not _is_named_destination(locked_dest):
            locked_dest = intake.get("destination_city")

        try:
            model_out = await self._call_manager(intake, history)
        except MissingModelKeyError:
            await self.conversations.save(conversation)
            raise
        except ManagerUnavailableError:
            await self.conversations.save(conversation)
            raise

        patch, recommended = _drop_destination_rewrite(
            locked_dest,
            model_out["intake_patch"],
            model_out["recommended_destination"],
        )
        intake = merge_intake(intake, patch)
        if recommended and _is_blank(intake.get("destination_city")):
            intake = merge_intake(
                intake,
                {
                    "destination_city": recommended,
                    "destination_text": recommended,
                    "region": "domestic",
                },
            )

        action = model_out["action"]
        reply = model_out["reply"]
        max_followups = settings.intake_max_followups
        used = intake["followup_rounds_used"]

        if intake["ready"]:
            action = "ready"
        elif action == "ready":
            action = "stop" if used >= max_followups else "ask"
        if not intake["ready"] and used >= max_followups:
            action = "stop"
        if action == "ask":
            intake["followup_rounds_used"] = used + 1
            if intake["followup_rounds_used"] > max_followups:
                action = "stop"
                intake["followup_rounds_used"] = max_followups
        if action == "stop":
            intake["ready"] = False
            if not reply:
                reply = _force_stop_reply(intake)
        if action == "ask" and not reply:
            labels = [MISSING_LABELS.get(item, item) for item in intake["missing_fields"]]
            reply = f"📝 还差这些就能出计划：{'、'.join(labels)}。"
        if action == "ready" and (not reply or _reply_blocks_ready(reply)):
            if _has_sea_wish(intake):
                reply = _assumed_ready_reply(intake)
            else:
                reply = "🧭 信息齐了，我这边让专员出一版，你可以在过程里看到进度。"

        conversation.intake_json = _dumps(intake)
        conversation.title = conversation_title(intake)
        assistant_row = await self._add_assistant(conversation_id, reply)

        if action == "ready":
            planning = await start_planning_stub(
                conversation,
                intake,
                planning_repo=self.planning,
            )
            conversation.planning_json = _dumps(planning)
            logger.info("问诊就绪，已创建规划任务", conversation_id=conversation_id)
        else:
            conversation.planning_json = _dumps(planning)

        await self.conversations.save(conversation)
        return self._turn(user_row, assistant_row, intake, _loads(conversation.planning_json))

    async def _revise(
        self,
        conversation: Conversation,
        user_row: Message,
        content: str,
        intake: dict[str, Any],
        planning: dict[str, Any],
        ready_itinerary,
    ) -> MessageTurnPublic:
        payload = loads_payload(ready_itinerary.payload_json)
        known_ops = known_revision_operations(content)
        if known_ops:
            _public, changed = await ItineraryService(self.db).apply_revision(
                ready_itinerary.id,
                known_ops,
            )
            if changed:
                assistant_row = await self._add_assistant(
                    conversation.id,
                    reply_for_known_operations(known_ops),
                )
                await self.conversations.save(conversation)
                return self._turn(user_row, assistant_row, intake, planning)

        history = await self.messages.list_by_conversation(conversation.id)
        try:
            model_out = await self._call_revise_manager(intake, history, itinerary_summary(payload))
        except MissingModelKeyError:
            await self.conversations.save(conversation)
            raise
        except ManagerUnavailableError:
            await self.conversations.save(conversation)
            raise

        action = model_out["action"]
        reply = model_out["reply"]
        forced_new_plan = is_major_replan(content, payload)
        if forced_new_plan or action == "suggest_new_plan":
            if forced_new_plan and action != "suggest_new_plan":
                text = NEW_PLAN_REPLY
            else:
                text = reply or NEW_PLAN_REPLY
            assistant_row = await self._add_assistant(conversation.id, text)
            await self.conversations.save(conversation)
            return self._turn(user_row, assistant_row, intake, planning)

        changed = False
        if action == "revise":
            _public, changed = await ItineraryService(self.db).apply_revision(
                ready_itinerary.id,
                model_out["operations"],
            )
        if not changed:
            assistant_row = await self._add_assistant(conversation.id, reply or UNMAPPED_REPLY)
            await self.conversations.save(conversation)
            return self._turn(user_row, assistant_row, intake, planning)

        assistant_row = await self._add_assistant(conversation.id, reply or REVISED_REPLY)
        await self.conversations.save(conversation)
        return self._turn(user_row, assistant_row, intake, planning)

    async def _call_revise_manager(
        self,
        intake: dict[str, Any],
        history: list[Message],
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        limit = settings.manager_history_limit
        recent = history[-limit:]
        prompt = REVISE_PROMPT_PATH.read_text(encoding="utf-8")
        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "system",
                "content": (
                    "当前问诊槽 json："
                    + _dumps(intake)
                    + "；当前行程摘要 json："
                    + _dumps(summary)
                ),
            },
        ]
        for item in recent:
            if item.role == "system":
                continue
            messages.append({"role": item.role, "content": item.content})
        raw = await llm_client.chat_json(messages)
        return _normalize_manager_output(raw)

    async def _call_manager(
        self, intake: dict[str, Any], history: list[Message]
    ) -> dict[str, Any]:
        limit = settings.manager_history_limit
        recent = history[-limit:]
        prompt = _load_prompt()
        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "system",
                "content": (
                    "当前问诊槽 json："
                    + _dumps(intake)
                    + f"；followup_rounds_used={intake.get('followup_rounds_used', 0)}"
                ),
            },
        ]
        for item in recent:
            if item.role == "system":
                continue
            messages.append({"role": item.role, "content": item.content})
        raw = await llm_client.chat_json(messages)
        return _normalize_manager_output(raw)

    async def _add_assistant(self, conversation_id: str, content: str) -> Message:
        row = Message(
            id=new_id("msg"),
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            created_at=utcnow(),
        )
        await self.messages.create(row)
        return row

    def _turn(
        self,
        user_row: Message,
        assistant_row: Message,
        intake: dict[str, Any],
        planning: dict[str, Any],
    ) -> MessageTurnPublic:
        return MessageTurnPublic(
            user_message=_message_public(user_row),
            assistant_message=_message_public(assistant_row),
            intake=_intake_public(intake),
            planning=_planning_public(planning),
        )
