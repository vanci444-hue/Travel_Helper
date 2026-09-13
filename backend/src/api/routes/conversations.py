"""会话路由：API-001～004。"""

from fastapi import Depends, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pycore.api import APIRouter, paginated_response, success_response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import error_json, get_db
from src.models.common import PACE_ERROR, AppError, ValidationAppError
from src.models.conversation import ConversationCreate, MessageCreate
from src.services.manager import ManagerService

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _parse_create_body(raw: bytes) -> ConversationCreate:
    if not raw.strip():
        return ConversationCreate()
    try:
        return ConversationCreate.model_validate_json(raw)
    except ValidationError as exc:
        for err in exc.errors():
            loc = err.get("loc") or ()
            msg = str(err.get("msg") or "")
            if "pace" in loc or PACE_ERROR in msg:
                raise ValidationAppError(PACE_ERROR) from exc
        raise ValidationAppError("参数验证失败") from exc


@router.post("")
async def create_conversation(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        payload = _parse_create_body(await request.body())
        data = await ManagerService(db).create(payload)
    except AppError as exc:
        return error_json(exc)
    body = success_response(data=data.model_dump(mode="json"), message="ok")
    return JSONResponse(status_code=201, content=jsonable_encoder(body))


@router.get("")
async def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        items, total = await ManagerService(db).list_items(page, page_size)
    except AppError as exc:
        return error_json(exc)
    body = paginated_response(
        data=[item.model_dump(mode="json") for item in items],
        page=page,
        page_size=page_size,
        total_items=total,
    )
    return JSONResponse(content=jsonable_encoder(body))


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        data = await ManagerService(db).get(conversation_id)
    except AppError as exc:
        return error_json(exc)
    body = success_response(data=data.model_dump(mode="json"), message="ok")
    return JSONResponse(content=jsonable_encoder(body))


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    payload: MessageCreate,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        data = await ManagerService(db).send_message(conversation_id, payload)
    except AppError as exc:
        return error_json(exc)
    body = success_response(data=data.model_dump(mode="json"), message="ok")
    return JSONResponse(content=jsonable_encoder(body))
