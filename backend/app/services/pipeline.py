"""Shared post-scrape pipeline.

The scheduler, arq worker, and maintenance CLI all need the same sequence:
cluster new articles -> analyze events -> optional IPO deep-dive -> notify.
Keeping it here avoids three drifting copies of the orchestration.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.models import Article, EventArticle, MarketEvent
from app.services.analysis.analyzer import analyze_event
from app.services.analysis.clustering import find_or_create_event
from app.services.analysis.ipo_research import run_ipo_research
from app.services.notifications.dispatcher import dispatch_event_notifications

log = get_logger("pipeline")


async def cluster_new_articles(
    session: AsyncSession, source_id: int, limit: int
) -> set[int]:
    """Cluster the newest unclustered articles for one source."""
    if limit <= 0:
        return set()

    result = await session.execute(
        select(Article)
        .where(
            Article.source_id == source_id,
            ~select(EventArticle.article_id)
            .where(EventArticle.article_id == Article.id)
            .exists(),
        )
        .order_by(Article.scraped_at.desc())
        .limit(limit)
    )
    event_ids: set[int] = set()
    for article in result.scalars():
        event = await find_or_create_event(session, article)
        event_ids.add(event.id)
    await session.commit()
    return event_ids


async def finalize_event(session: AsyncSession, event_id: int) -> MarketEvent | None:
    """Analyze an event, run the IPO deep-dive when relevant, and notify."""
    event = await analyze_event(session, event_id)
    if event is None:
        return None
    if event.analysis_status != "DONE":
        return event

    if event.category == "IPO":
        try:
            await run_ipo_research(session, event_id)
        except Exception as exc:
            log.warn("ipo.task_failed", event=event_id, error=str(exc)[:200])

    await dispatch_event_notifications(session, event_id)
    return event


def should_retry_analysis(event: MarketEvent) -> bool:
    settings = get_settings()
    return (
        event.analysis_status == "PENDING"
        and (event.analysis_attempts or 0) < settings.analysis_max_attempts
    )
