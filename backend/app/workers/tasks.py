"""arq worker task definitions."""

from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.session import get_session_factory
from app.models.models import Article, EventArticle, Source
from app.services.analysis.analyzer import analyze_event
from app.services.analysis.clustering import find_or_create_event
from app.services.healing.agent import heal_source
from app.services.notifications.dispatcher import dispatch_event_notifications
from app.services.scraping.runner import run_source

setup_logging()
log = get_logger("worker")


async def scrape_source(ctx, source_id: int) -> dict:
    """Scrape one source; cluster new articles into events; enqueue analysis."""
    factory = get_session_factory()
    async with factory() as session:
        source_result = await session.execute(select(Source).where(Source.id == source_id))
        source = source_result.scalar_one_or_none()
        if source is None or not source.active:
            return {"skipped": True}

        async with httpx.AsyncClient() as http:
            outcome = await run_source(session, source, http_client=http)

        if outcome.status == "SUCCESS" and outcome.new_articles > 0:
            # cluster only articles not yet attached to any event
            unclustered = (
                await session.execute(
                    select(Article)
                    .where(
                        Article.source_id == source_id,
                        ~select(EventArticle.article_id)
                        .where(EventArticle.article_id == Article.id)
                        .exists(),
                    )
                    .order_by(Article.scraped_at.desc())
                    .limit(outcome.new_articles)
                )
            ).scalars()

            event_ids = set()
            for article in unclustered:
                event = await find_or_create_event(session, article)
                event_ids.add(event.id)
            await session.commit()

            for event_id in event_ids:
                await ctx["enqueue"].enqueue_job("analyze_event", event_id)

        if outcome.should_heal:
            log.warn(
                "scraper.heal_triggered",
                source=source.slug,
                error_type=outcome.error_type,
            )
            source.health_status = "HEALING"
            await session.commit()
            await ctx["enqueue"].enqueue_job("heal_source_job", source_id, False)

        return {
            "status": outcome.status,
            "articles_found": outcome.articles_found,
            "new_articles": outcome.new_articles,
            "error_type": outcome.error_type,
            "should_heal": outcome.should_heal,
        }


async def analyze_event_task(ctx, event_id: int) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        event = await analyze_event(session, event_id)
        if event is None:
            return {"status": "missing"}
        if event.analysis_status == "DONE":
            await dispatch_event_notifications(session, event_id)
            return {"status": "done", "urgency": event.urgency}
        # LLM failed -> analysis stays PENDING for retry
        await ctx["enqueue"].enqueue_job("analyze_event", event_id, _defer_by=120)
        return {"status": "pending_retry"}


async def heal_source_job(ctx, source_id: int, manual: bool = False) -> dict:
    """Run the healing agent for a source. On success, immediately re-scrape."""
    factory = get_session_factory()
    async with factory() as session:
        result = await heal_source(session, source_id, manual=manual)
        status = result.status

    if status == "SUCCESS":
        await ctx["enqueue"].enqueue_job("scrape_source", source_id)
    elif status == "ERROR" and manual is False:
        # retry healing later (LLM may be temporarily unavailable)
        await ctx["enqueue"].enqueue_job("heal_source_job", source_id, _defer_by=300)
    return {"healing_status": status}


async def send_startup_ping(ctx):
    log.info("worker.started")
