"""API-005：规划进度 SSE。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from pycore.api import APIRouter
from pycore.api.responses import error_response
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import error_json, get_db
from src.db.session import get_db_context
from src.models.common import NotFoundError, utc_iso, utcnow
from src.repositories.conversations import ConversationRepository
from src.services.activity_log import event_hub
from src.services.planning import load_planning_view

HEARTBEAT_SECONDS = 15
router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _accepts_sse(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    if not accept or "*/*" in accept:
        return True
    return "text/event-stream" in accept


async def _reload(conversation_id: str) -> dict:
    async with get_db_context() as db:
        return await load_planning_view(db, conversation_id) or {}


async def _event_stream(
    request: Request,
    conversation_id: str,
    snapshot: dict,
) -> AsyncIterator[str]:
    queue = event_hub.subscribe(conversation_id)
    latest = await _reload(conversation_id)
    if latest:
        snapshot = latest
    seen_logs = {item.get("id") for item in snapshot.get("activity_log") or []}
    try:
        yield _sse(
            "planning.updated",
            {
                "status": snapshot.get("status"),
                "specialists": snapshot.get("specialists") or [],
                "itinerary_id": snapshot.get("itinerary_id"),
            },
        )
        for entry in snapshot.get("activity_log") or []:
            yield _sse("planning.log", {"entry": entry})
        status = snapshot.get("status")
        if status == "succeeded":
            yield _sse(
                "itinerary.ready",
                {
                    "status": "succeeded",
                    "itinerary_id": snapshot.get("itinerary_id"),
                    "specialists": snapshot.get("specialists") or [],
                },
            )
            return
        if status == "failed":
            yield _sse(
                "planning.failed",
                {
                    "status": "failed",
                    "itinerary_id": None,
                    "failure_reason": snapshot.get("error_message") or "规划未能完成，原因未明确",
                    "coco_message_id": snapshot.get("coco_message_id"),
                    "specialists": snapshot.get("specialists") or [],
                },
            )
            return
        while True:
            try:
                queued = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            event, data = queued
            if event == "planning.log":
                entry = (data or {}).get("entry") or {}
                log_id = entry.get("id")
                if log_id in seen_logs:
                    continue
                seen_logs.add(log_id)
            yield _sse(event, data)
            if event in {"itinerary.ready", "planning.failed"}:
                return
        while True:
            if await request.is_disconnected():
                return
            try:
                event, data = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except TimeoutError:
                latest = await _reload(conversation_id)
                if latest.get("status") == "succeeded":
                    yield _sse(
                        "itinerary.ready",
                        {
                            "status": "succeeded",
                            "itinerary_id": latest.get("itinerary_id"),
                            "specialists": latest.get("specialists") or [],
                        },
                    )
                    return
                if latest.get("status") == "failed":
                    yield _sse(
                        "planning.failed",
                        {
                            "status": "failed",
                            "itinerary_id": None,
                            "failure_reason": latest.get("error_message")
                    or "规划未能完成，原因未明确",
                            "coco_message_id": latest.get("coco_message_id"),
                            "specialists": latest.get("specialists") or [],
                        },
                    )
                    return
                yield _sse("heartbeat", {"ts": utc_iso(utcnow())})
                continue
            if event == "planning.log":
                entry = (data or {}).get("entry") or {}
                log_id = entry.get("id")
                if log_id in seen_logs:
                    continue
                seen_logs.add(log_id)
            yield _sse(event, data)
            if event in {"itinerary.ready", "planning.failed"}:
                return
    finally:
        event_hub.unsubscribe(conversation_id, queue)


@router.get("/{conversation_id}/events")
async def conversation_events(
    conversation_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    conversation = await ConversationRepository(db).get(conversation_id)
    if conversation is None:
        return error_json(NotFoundError())
    if not _accepts_sse(request):
        resp, status = error_response(
            error="无法升级为事件流",
            error_code="INTERNAL_ERROR",
            status_code=500,
        )
        return JSONResponse(status_code=status, content=jsonable_encoder(resp))
    snapshot = await load_planning_view(db, conversation_id) or {}
    return StreamingResponse(
        _event_stream(request, conversation_id, snapshot),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
