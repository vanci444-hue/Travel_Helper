"""
数据库会话管理。从 pycore/integrations/db/session.py 复制后扩展。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pycore.core.logger import get_logger
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from src.config.settings import database_url, settings

logger = get_logger()

_is_sqlite = str(database_url).startswith("sqlite")

_engine_kwargs: dict = {"echo": False, "future": True}
if _is_sqlite:
    _engine_kwargs["poolclass"] = NullPool
    _engine_kwargs["connect_args"] = {"timeout": 30}

engine = create_async_engine(database_url, **_engine_kwargs)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


def _enable_sqlite_fk(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def attach_sqlite_pragma(target_engine) -> None:
    event.listen(target_engine.sync_engine, "connect", _enable_sqlite_fk)


attach_sqlite_pragma(engine)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（用于 FastAPI Depends）。"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """上下文管理器形式的数据库会话。"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """初始化数据库（创建表）。"""
    from src.db.models import Base

    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库已初始化", debug=settings.debug)


async def close_db() -> None:
    """关闭数据库连接。"""
    await engine.dispose()
    logger.info("数据库连接已关闭")
