"""API 入口：装配 PyCore APIServer。"""

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pycore.api import APIConfig, APIServer
from pycore.api.middleware import RequestContextMiddleware
from pycore.api.responses import error_response
from pycore.core import Logger, LoggerConfig, LogLevel, get_logger
from src.api.deps import error_json
from src.api.routes.conversations import router as conversations_router
from src.api.routes.events import router as events_router
from src.api.routes.inspirations import router as inspirations_router
from src.api.routes.itineraries import router as itineraries_router
from src.config.settings import settings
from src.db.session import close_db, init_db
from src.models.common import PACE_ERROR, AppError

Logger.configure(
    LoggerConfig(
        level=LogLevel.DEBUG if settings.debug else LogLevel.INFO,
        app_name="xtrip",
        json_format=False,
        file_enabled=False,
    )
)
logger = get_logger()


async def on_startup() -> None:
    await init_db()
    logger.info("后端启动完成", host=settings.host, port=settings.port)


async def on_shutdown() -> None:
    await close_db()


server = APIServer(
    APIConfig(
        title="Xtrip",
        version="0.1.0",
        host=settings.host,
        port=settings.port,
        debug=settings.debug,
        cors_origins=settings.cors_origins,
    )
)
server.on_startup(on_startup)
server.on_shutdown(on_shutdown)
server.include_router(conversations_router)
server.include_router(events_router)
server.include_router(inspirations_router)
server.include_router(itineraries_router)
server.add_middleware(RequestContextMiddleware)

app = server.app


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return error_json(exc)


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    message = "参数验证失败"
    for err in exc.errors():
        loc = err.get("loc") or ()
        msg = str(err.get("msg") or "")
        if "pace" in loc or PACE_ERROR in msg:
            message = PACE_ERROR
            break
    resp, status = error_response(
        error=message,
        error_code="VALIDATION_ERROR",
        status_code=400,
    )
    return JSONResponse(status_code=status, content=jsonable_encoder(resp))


@app.exception_handler(Exception)
async def unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未归类异常", error_msg=str(exc))
    resp, status = error_response(
        error="服务器内部错误",
        error_code="INTERNAL_ERROR",
        status_code=500,
    )
    return JSONResponse(status_code=status, content=jsonable_encoder(resp))
