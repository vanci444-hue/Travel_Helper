"""会话、消息与问诊槽 DTO。"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator
from src.models.common import (
    PACE_ALIASES,
    PACE_ERROR,
    CamelModel,
    CompanionType,
    MessageRole,
    Pace,
    PlanningStatus,
    Region,
    SpecialistRole,
    SpecialistStatus,
)


class ConversationCreate(CamelModel):
    origin_city: str | None = None
    region: Region | None = None
    destination_text: str | None = None
    destination_city: str | None = None
    duration_days: int | None = Field(default=None, ge=1, le=14)
    date_start: str | None = None
    date_end: str | None = None
    date_month: str | None = None
    companion_type: CompanionType | None = None
    adults: int | None = Field(default=None, ge=0)
    children: int | None = Field(default=None, ge=0)
    children_age_bands: list[str] | None = None
    budget_amount_cny: float | None = Field(default=None, ge=0)
    budget_tier: str | None = None
    budget_includes: str | None = None
    pace: Pace | None = None
    wish_text: str | None = None

    @field_validator("pace", mode="before")
    @classmethod
    def normalize_pace(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        mapped = PACE_ALIASES.get(str(value).strip())
        if mapped is None:
            raise ValueError(PACE_ERROR)
        return mapped

    @field_validator("budget_tier", mode="before")
    @classmethod
    def normalize_budget_tier(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        allowed = {"economy", "comfort", "premium"}
        text = str(value).strip()
        aliases = {
            "经济": "economy",
            "舒适": "comfort",
            "舒适档": "comfort",
            "高端": "premium",
            "不限": "premium",
            "预算不限": "premium",
            "没有上限": "premium",
        }
        mapped = aliases.get(text, text)
        if mapped not in allowed:
            raise ValueError("预算档位只能是经济、舒适或高端")
        return mapped


class MessageCreate(CamelModel):
    content: str = Field(..., min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("消息不能为空")
        return value


class MessagePublic(CamelModel):
    id: str
    role: MessageRole
    content: str
    created_at: str
    display_name: str | None = None


class SpecialistPublic(CamelModel):
    role: SpecialistRole
    status: SpecialistStatus
    summary: str | None = None


class ActivityLogEntry(CamelModel):
    id: str
    kind: str
    specialist: SpecialistRole
    title: str
    clickable: bool
    detail: dict[str, str] | None = None
    created_at: str


class PlanningPublic(CamelModel):
    status: PlanningStatus
    specialists: list[SpecialistPublic]
    activity_log: list[ActivityLogEntry] = Field(default_factory=list)
    error_message: str | None = None
    itinerary_id: str | None = None


class IntakePublic(CamelModel):
    origin_city: str | None = None
    region: Region | None = None
    destination_text: str | None = None
    destination_city: str | None = None
    duration_days: int | None = None
    date_start: str | None = None
    date_end: str | None = None
    date_month: str | None = None
    companion_type: CompanionType | None = None
    adults: int | None = None
    children: int = 0
    children_age_bands: list[str] = Field(default_factory=list)
    budget_amount_cny: float | None = None
    budget_tier: str | None = None
    budget_includes: str | None = None
    pace: Pace | None = None
    wish_text: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    followup_rounds_used: int = 0
    ready: bool = False


class ConversationPublic(CamelModel):
    id: str
    title: str
    intake: IntakePublic
    map_hint: dict[str, float] | None = None
    planning: PlanningPublic
    messages: list[MessagePublic] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ConversationListPlanning(CamelModel):
    status: PlanningStatus


class ConversationListItem(CamelModel):
    id: str
    title: str
    updated_at: str
    planning: ConversationListPlanning
    itinerary_id: str | None = None


class MessageTurnPublic(CamelModel):
    user_message: MessagePublic
    assistant_message: MessagePublic
    intake: IntakePublic
    planning: PlanningPublic
