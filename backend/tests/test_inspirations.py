from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.config.settings import settings
from src.db.session import attach_sqlite_pragma, init_db


@pytest.fixture
async def client(tmp_path, monkeypatch) -> AsyncGenerator[AsyncClient, None]:
    test_db = tmp_path / "Travel_Helper.insp.test.db"
    url = f"sqlite+aiosqlite:///{test_db}"
    test_engine = create_async_engine(url, future=True)
    test_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    attach_sqlite_pragma(test_engine)
    import src.db.session as session_mod

    monkeypatch.setattr(session_mod, "engine", test_engine)
    monkeypatch.setattr(session_mod, "async_session_maker", test_maker)
    await init_db()
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", trust_env=False) as ac:
        yield ac
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_inspirations_have_domestic_static_images(client: AsyncClient) -> None:
    resp = await client.get("/api/inspirations")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert isinstance(data, list)
    assert len(data) >= 1
    first = data[0]
    assert first["city"]
    assert first["description"]
    assert str(first["image_url"]).startswith("/inspirations/")
    assert all(item["image_url"].startswith("/inspirations/") for item in data)


def test_cors_includes_agent_and_gate_origins() -> None:
    joined = " ".join(settings.cors_origins)
    assert "5199" in joined
    assert "5175" in joined
    assert "8099" in joined
    assert "8003" in joined
