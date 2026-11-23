"""Idempotent schema upgrades for existing deployments.

The project intentionally keeps startup migrations small and additive instead
of running a full migration framework. Every statement here is safe to run on
each boot and on a brand-new database.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.logging import get_logger
from app.models.models import Base

log = get_logger("db.upgrade")


async def _ensure_notification_index(conn: AsyncConnection) -> None:
    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_once "
            "ON notifications (event_id, channel, (COALESCE(user_id, -1)))"
        )
    )


async def _ensure_article_uniqueness(conn: AsyncConnection) -> None:
    """Deduplicate legacy rows, then enforce one row per (source, url)."""
    duplicates = (
        await conn.execute(
            text(
                "SELECT count(*) FROM ("
                "  SELECT source_id, url FROM articles "
                "  GROUP BY source_id, url HAVING count(*) > 1"
                ") dupes"
            )
        )
    ).scalar() or 0

    if duplicates:
        deleted = await conn.execute(
            text(
                "DELETE FROM articles WHERE id NOT IN ("
                "  SELECT MIN(id) FROM articles GROUP BY source_id, url"
                ")"
            )
        )
        log.warn("db.articles_deduplicated", duplicate_groups=duplicates, deleted=deleted.rowcount)

    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_articles_source_url "
            "ON articles (source_id, url)"
        )
    )


async def _ensure_clustering_index(conn: AsyncConnection) -> None:
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_market_events_last_updated "
            "ON market_events (last_updated_at)"
        )
    )


async def _ensure_analysis_attempts(conn: AsyncConnection) -> None:
    # create_all only creates missing tables, not missing columns on existing
    # deployments. Postgres supports ADD COLUMN IF NOT EXISTS; SQLite test
    # databases are created fresh from the models.
    if conn.dialect.name == "postgresql":
        await conn.execute(
            text(
                "ALTER TABLE market_events "
                "ADD COLUMN IF NOT EXISTS analysis_attempts INTEGER NOT NULL DEFAULT 0"
            )
        )


async def ensure_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_notification_index(conn)
        await _ensure_article_uniqueness(conn)
        await _ensure_clustering_index(conn)
        await _ensure_analysis_attempts(conn)
