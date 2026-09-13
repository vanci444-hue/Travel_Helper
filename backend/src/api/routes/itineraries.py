"""行程路由：API-006～009。"""

from fastapi import Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pycore.api import APIRouter, paginated_response, success_response
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import error_json, get_db
from src.models.common import AppError
from src.services.revision import CardPatch, ItineraryService

router = APIRouter(prefix="/api/itineraries", tags=["itineraries"])


@router.get("")
async def list_itineraries(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        items, total = await ItineraryService(db).list_ready(page, page_size)
    except AppError as exc:
        return error_json(exc)
    body = paginated_response(
        data=[item.model_dump(mode="json") for item in items],
        page=page,
        page_size=page_size,
        total_items=total,
    )
    return JSONResponse(content=jsonable_encoder(body))


@router.get("/{itinerary_id}")
async def get_itinerary(
    itinerary_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        data = await ItineraryService(db).get_public(itinerary_id)
    except AppError as exc:
        return error_json(exc)
    body = success_response(data=data.model_dump(mode="json"), message="ok")
    return JSONResponse(content=jsonable_encoder(body))


@router.patch("/{itinerary_id}/cards/{card_id}")
async def patch_card(
    itinerary_id: str,
    card_id: str,
    payload: CardPatch,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        data = await ItineraryService(db).patch_card(itinerary_id, card_id, payload)
    except AppError as exc:
        return error_json(exc)
    body = success_response(data=data.model_dump(mode="json"), message="ok")
    return JSONResponse(content=jsonable_encoder(body))


@router.delete("/{itinerary_id}/cards/{card_id}")
async def delete_card(
    itinerary_id: str,
    card_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        data = await ItineraryService(db).delete_card(itinerary_id, card_id)
    except AppError as exc:
        return error_json(exc)
    body = success_response(data=data.model_dump(mode="json"), message="ok")
    return JSONResponse(content=jsonable_encoder(body))
