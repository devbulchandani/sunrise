"""Retention jobs for old scraped content.

Articles and the events they belong to are one lifecycle: keeping events after
their articles are purged leaves empty event pages, so both are removed after
the configured window. Orphaned events from older deployments are also cleaned
up.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.models.models import Article, EventArticle, MarketEvent

log = get_logger("retention")


async def purge_expired_content() -> dict[str, int]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    article_cutoff = now - timedelta(days=settings.article_retention_days)
    event_cutoff = now - timedelta(days=settings.event_retention_days)
    orphan_cutoff = now - timedelta(days=1)

    factory = get_session_factory()
    async with factory() as session:
        # Events first: the FK cascade removes event_articles/assets/notifications.
        events = await session.execute(
            delete(MarketEvent).where(MarketEvent.last_updated_at < event_cutoff)
        )
        articles = await session.execute(
            delete(Article).where(Article.scraped_at < article_cutoff)
        )
        # Safety net for events left without articles by an older retention run.
        orphans = await session.execute(
            delete(MarketEvent).where(
                MarketEvent.last_updated_at < orphan_cutoff,
                ~select(EventArticle.id)
                .where(EventArticle.event_id == MarketEvent.id)
                .exists(),
            )
        )
        await session.commit()

    result = {
        "events": events.rowcount or 0,
        "articles": articles.rowcount or 0,
        "orphan_events": orphans.rowcount or 0,
    }
    log.info(
        "retention.purged",
        article_retention_days=settings.article_retention_days,
        event_retention_days=settings.event_retention_days,
        **result,
    )
    return result


async def purge_expired_articles() -> int:
    """Backward-compatible entry point; returns the number of articles removed."""
    result = await purge_expired_content()
    return result["articles"]
