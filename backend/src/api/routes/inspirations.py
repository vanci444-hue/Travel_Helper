"""灵感路由：API-010。"""

import json
from pathlib import Path

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pycore.api import APIRouter, success_response
from src.models.inspiration import InspirationPublic

router = APIRouter(prefix="/api/inspirations", tags=["inspirations"])

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "inspirations.json"


@router.get("")
async def list_inspirations() -> JSONResponse:
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    items = [InspirationPublic.model_validate(item).model_dump(mode="json") for item in raw]
    body = success_response(data=items, message="ok")
    return JSONResponse(content=jsonable_encoder(body))
