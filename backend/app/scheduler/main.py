"""Scheduler process: reads sources from DB and enqueues scrape jobs per cron.

Run with: python -m app.scheduler.main
"""

import asyncio
from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.core.logging import get_logger, setup_logging
from app.db.session import get_session_factory
from app.models.models import Article, EventArticle, Source
from app.services.scraping.runner import run_source
from app.services.analysis.clustering import find_or_create_event
from app.services.healing.agent import heal_source
from app.services.notifications.dispatcher import dispatch_event_notifications
from app.services.analysis.analyzer import analyze_event

setup_logging()
log = get_logger("scheduler")


def cron_to_apscheduler(cron_expr: str) -> dict | None:
    parts = cron_expr.split()
    if len(parts) != 5:
        return None
    minute, hour, day, month, day_of_week = parts
    kwargs = {}
    for key, value in [
        ("minute", minute),
        ("hour", hour),
        ("day", day),
        ("month", month),
        ("day_of_week", day_of_week),
    ]:
        if value == "*":
            continue
        kwargs[key] = value
    return kwargs or {"minute": "*/5"}


async def run_scheduled_scrape(source_id: int) -> None:
    """Direct in-process execution of one scrape cycle (scheduler is its own worker)."""
    factory = get_session_factory()
    async with factory() as session:
        source_result = await session.execute(select(Source).where(Source.id == source_id))
        source = source_result.scalar_one_or_none()
        if source is None or not source.active:
            return

        async with httpx.AsyncClient() as http:
            outcome = await run_source(session, source, http_client=http)

        if outcome.status == "SUCCESS" and outcome.new_articles > 0:
            unclustered_result = await session.execute(
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
            event_ids = set()
            for article in unclustered_result.scalars():
                event = await find_or_create_event(session, article)
                event_ids.add(event.id)
            await session.commit()

            for event_id in event_ids:
                try:
                    event = await analyze_event(session, event_id)
                    if event and event.analysis_status == "DONE":
                        await dispatch_event_notifications(session, event_id)
                except Exception as exc:
                    log.warn("analysis.failed_in_scheduler", event=event_id, error=str(exc)[:200])

        if outcome.should_heal:
            log.warn("scraper.heal_triggered", source=source.slug)
            source.health_status = "HEALING"
            await session.commit()
            await heal_source(session, source.id, manual=False)
            # after healing, immediately re-run to prove recovery
            await session.refresh(source)
            if source.health_status == "HEALTHY":
                async with httpx.AsyncClient() as http:
                    await run_source(session, source, http_client=http)


async def refresh_jobs(scheduler: AsyncIOScheduler) -> None:
    """Sync APScheduler jobs with active sources in DB."""
    factory = get_session_factory()
    async with factory() as session:
        sources = (await session.execute(select(Source).where(Source.active.is_(True)))).scalars()

    wanted = {}
    for source in sources:
        job_id = f"scrape:{source.slug}"
        trigger_args = cron_to_apscheduler(source.schedule)
        if trigger_args is None:
            log.warn("scheduler.bad_cron", source=source.slug, schedule=source.schedule)
            continue
        wanted[job_id] = (source.id, source.name, trigger_args)

    existing = {job.id for job in scheduler.get_jobs()}
    for job_id, (sid, name, trigger_args) in wanted.items():
        if job_id not in existing:
            scheduler.add_job(
                run_scheduled_scrape,
                CronTrigger(**trigger_args),
                args=[sid],
                id=job_id,
                name=f"scrape {name}",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=120,
            )
            log.info("scheduler.job_added", source=name, schedule=source_schedule_str(trigger_args))
    for job_id in existing - set(wanted.keys()):
        scheduler.remove_job(job_id)
        log.info("scheduler.job_removed", job=job_id)


def source_schedule_str(trigger_args: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in sorted(trigger_args.items()))


async def main() -> None:
    scheduler = AsyncIOScheduler(timezone="UTC")
    await refresh_jobs(scheduler)
    scheduler.start()
    log.info("scheduler.started")

    # telegram subscriber bot — one poller, runs alongside the scheduler
    from app.services.notifications.bot_subscribers import poll_forever

    bot_task = asyncio.create_task(poll_forever())

    # periodically pick up newly added/changed sources
    while True:
        await asyncio.sleep(60)
        try:
            await refresh_jobs(scheduler)
        except Exception as exc:
            log.error("scheduler.refresh_failed", error=str(exc)[:200])
        if bot_task.done():
            exc = bot_task.exception()
            log.error("bot.task_died", error=str(exc)[:200] if exc else "unknown")
            bot_task = asyncio.create_task(poll_forever())


if __name__ == "__main__":
    asyncio.run(main())
