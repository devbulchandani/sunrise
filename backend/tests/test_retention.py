"""Retention removes old events and their articles as one lifecycle."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import get_session_factory
from app.models.models import Article, Base, EventArticle, MarketEvent, Source
from app.services.retention import purge_expired_content


async def test_purge_removes_old_events_and_articles(tmp_path, monkeypatch):
    import app.db.session as db_session

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/retention.db")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "_engine", engine)
    monkeypatch.setattr(db_session, "_session_factory", factory)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    old = datetime.now(timezone.utc) - timedelta(days=40)
    async with factory() as session:
        source = Source(slug="ret", name="Retention", url="https://example.test", type="rss")
        session.add(source)
        await session.flush()
        article = Article(
            source_id=source.id,
            url="https://example.test/old",
            title="Old story",
            content_hash="hash",
            scraped_at=old,
        )
        session.add(article)
        await session.flush()
        event = MarketEvent(headline="Old event", last_updated_at=old)
        session.add(event)
        await session.flush()
        session.add(EventArticle(event_id=event.id, article_id=article.id))
        await session.commit()

    result = await purge_expired_content()
    assert result["events"] == 1
    assert result["articles"] == 1

    async with factory() as session:
        assert (await session.execute(select(func.count()).select_from(Article))).scalar() == 0
        assert (await session.execute(select(func.count()).select_from(MarketEvent))).scalar() == 0

    await engine.dispose()
