"""Article persistence must tolerate duplicate URLs in one feed batch."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import Article, Base, Source
from app.services.scraping.runner import _persist_articles


async def test_persist_dedupes_within_batch(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/persist.db")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with factory() as session:
        source = Source(slug="bbc", name="BBC", url="https://example.test", type="rss")
        session.add(source)
        await session.flush()

        entries = [
            {"title": "Story A", "url": "https://example.test/a"},
            {"title": "Story A (repeated in feed)", "url": "https://example.test/a"},
            {"title": "Story B", "url": "https://example.test/b"},
        ]
        new_count, duplicate_ratio = await _persist_articles(session, source, entries)
        await session.commit()

        assert new_count == 2
        assert duplicate_ratio == round(1 / 3, 3)

        stored = (
            await session.execute(select(func.count()).select_from(Article))
        ).scalar()
        assert stored == 2

    await engine.dispose()
