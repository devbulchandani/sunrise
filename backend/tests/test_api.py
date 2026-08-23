import asyncio
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DEMO_MODE", "true")


@pytest_asyncio.fixture
async def client(tmp_path):
    """FastAPI test client backed by a fresh SQLite DB."""
    import app.db.session as db_session

    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    from app.models.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    db_session._engine = engine
    db_session._session_factory = session_factory

    from app.main import app
    from app.api.routes import router  # ensure routes registered

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await engine.dispose()


@pytest.mark.asyncio
class TestAPI:
    async def test_health(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_sources_empty_then_seeded_shape(self, client):
        resp = await client.get("/api/sources")
        assert resp.status_code == 200
        assert "sources" in resp.json()

    async def test_scrapers_health(self, client):
        resp = await client.get("/api/scrapers/health")
        assert resp.status_code == 200
        assert "scrapers" in resp.json()

    async def test_events_list(self, client):
        resp = await client.get("/api/events")
        assert resp.status_code == 200
        assert "events" in resp.json()

    async def test_event_detail_404(self, client):
        resp = await client.get("/api/events/99999")
        assert resp.status_code == 404

    async def test_stats(self, client):
        resp = await client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "articles_scraped" in data and "scraper_healings" in data

    async def test_preferences_roundtrip(self, client):
        got = (await client.get("/api/preferences")).json()
        assert got["minimum_urgency"] >= 0

        updated = await client.put(
            "/api/preferences",
            json={
                "email": "demo@sunrise.local",
                "minimum_urgency": 80,
                "asset_preferences": ["btc", "spy"],
                "category_preferences": ["crypto"],
                "email_enabled": True,
                "telegram_enabled": False,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["minimum_urgency"] == 80
        assert updated.json()["asset_preferences"] == ["BTC", "SPY"]

    async def test_run_missing_source_404(self, client):
        resp = await client.post("/api/scrapers/9999/run")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestDemoBreakRestore:
    async def test_break_requires_source(self, client):
        from app.demo import break_scraper

        with pytest.raises(SystemExit):
            await break_scraper("does-not-exist")
