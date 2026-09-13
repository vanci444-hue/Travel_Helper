"""
FastAPI 依赖注入。从 pycore/api/deps.py 复制后扩展。
无登录；数据库会话必须使用项目 src.db.session.get_db。
"""

from collections.abc import AsyncGenerator

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pycore.api.responses import APIResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.session import get_db as get_db_session
from src.models.common import AppError


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话。"""
    async for session in get_db_session():
        yield session


def error_json(exc: AppError) -> JSONResponse:
    response = APIResponse(
        success=False,
        data=exc.data,
        error=exc.message,
        error_code=exc.error_code,
    )
    return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(response))
