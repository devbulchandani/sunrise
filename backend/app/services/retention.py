"""Retention jobs for old scraped content."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.models.models import Article

log = get_logger("retention")


async def purge_expired_articles() -> int:
    """Delete articles older than the configured scrape-time retention window."""
    cutoff = datetime.now(timezone.utc) - timedelta(
        days=get_settings().article_retention_days
    )
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            delete(Article).where(Article.scraped_at < cutoff)
        )
        await session.commit()
        deleted = result.rowcount or 0

    log.info(
        "retention.articles_purged",
        deleted=deleted,
        retention_days=get_settings().article_retention_days,
    )
    return deleted
