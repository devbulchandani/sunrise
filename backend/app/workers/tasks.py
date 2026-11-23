"""arq worker task definitions."""

import httpx
from sqlalchemy import select

from app.core.logging import get_logger, setup_logging
from app.db.session import get_session_factory
from app.models.models import Source
from app.services.healing.agent import heal_source
from app.services.pipeline import (
    cluster_new_articles,
    finalize_event,
    should_retry_analysis,
)
from app.services.scraping.runner import run_source

setup_logging()
log = get_logger("worker")


async def scrape_source(ctx, source_id: int) -> dict:
    """Scrape one source; cluster new articles into events; enqueue analysis."""
    factory = get_session_factory()
    async with factory() as session:
        source = (
            await session.execute(select(Source).where(Source.id == source_id))
        ).scalar_one_or_none()
        if source is None or not source.active:
            return {"skipped": True}

        async with httpx.AsyncClient() as http:
            outcome = await run_source(session, source, http_client=http)

        if outcome.skipped:
            return {"status": "skipped", "reason": "source lock held"}

        if outcome.status == "SUCCESS" and outcome.new_articles > 0:
            event_ids = await cluster_new_articles(session, source_id, outcome.new_articles)
            for event_id in event_ids:
                await ctx["enqueue"].enqueue_job("analyze_event", event_id)

        if outcome.should_heal:
            log.warn(
                "scraper.heal_triggered",
                source=source.slug,
                error_type=outcome.error_type,
            )
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
        event = await finalize_event(session, event_id)
        if event is None:
            return {"status": "missing"}
        if event.analysis_status == "DONE":
            return {"status": "done", "urgency": event.urgency}
        if should_retry_analysis(event):
            # Bounded retry: the analyzer increments analysis_attempts and marks
            # the event FAILED once the budget is exhausted.
            await ctx["enqueue"].enqueue_job("analyze_event", event_id, _defer_by=120)
            return {"status": "pending_retry", "attempts": event.analysis_attempts}
        return {"status": "failed", "attempts": event.analysis_attempts}


async def heal_source_job(ctx, source_id: int, manual: bool = False) -> dict:
    """Run the healing agent for a source. On success, immediately re-scrape.

    Failures are not re-enqueued in a tight loop: the source stays DEGRADED and
    the next failed scrape (after the configured consecutive-failure threshold)
    triggers another attempt.
    """
    factory = get_session_factory()
    async with factory() as session:
        result = await heal_source(session, source_id, manual=manual)
        status = result.status

    if status == "SUCCESS":
        await ctx["enqueue"].enqueue_job("scrape_source", source_id)
    return {"healing_status": status}


async def send_startup_ping(ctx):
    log.info("worker.started")
