"""共享类型、时间与业务异常。"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Pace = Literal["relaxed", "moderate", "packed"]
Region = Literal["domestic", "outbound"]
CompanionType = Literal["solo", "couple", "family", "friends", "parent_child", "unknown"]
PlanningStatus = Literal["idle", "running", "succeeded", "failed"]
SpecialistStatus = Literal["not_started", "running", "succeeded", "failed"]
SpecialistRole = Literal["destination_research", "budget_expert", "itinerary_design"]
MessageRole = Literal["user", "assistant", "system"]
ManagerAction = Literal["ask", "ready", "stop", "revise", "suggest_new_plan"]

PACE_ALIASES = {
    "relaxed": "relaxed",
    "moderate": "moderate",
    "packed": "packed",
    "轻松": "relaxed",
    "适中": "moderate",
    "紧凑": "packed",
}
PACE_ERROR = "节奏只能是轻松、适中或紧凑"
MISSING_MODEL_KEY = "未配置模型密钥"
COCO_UNAVAILABLE = "Coco 暂时没有回复，请再试一次"
CONVERSATION_NOT_FOUND = "找不到这场对话"
CONTINUE_HINTS = (
    "请根据已填写的计划继续",
    "已按表单创建，请根据已填项继续",
)


class CamelModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def utc_iso(value: datetime) -> str:
    return as_utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


class AppError(Exception):
    """业务错误，由路由转为统一信封。"""

    def __init__(
        self,
        message: str,
        error_code: str,
        status_code: int,
        data: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.data = data


class NotFoundError(AppError):
    def __init__(self, message: str = CONVERSATION_NOT_FOUND) -> None:
        super().__init__(message, "NOT_FOUND", 404)


class ValidationAppError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "VALIDATION_ERROR", 400)


class InternalAppError(AppError):
    def __init__(self, message: str, data: Any | None = None) -> None:
        super().__init__(message, "INTERNAL_ERROR", 500, data=data)


class MissingModelKeyError(InternalAppError):
    def __init__(self) -> None:
        super().__init__(MISSING_MODEL_KEY)


class ManagerUnavailableError(InternalAppError):
    def __init__(self) -> None:
        super().__init__(COCO_UNAVAILABLE)
