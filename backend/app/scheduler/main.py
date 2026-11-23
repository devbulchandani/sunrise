"""Scheduler process: reads sources from DB and runs one scrape cycle per cron.

Run with: python -m app.scheduler.main
"""

import asyncio

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.session import get_session_factory
from app.models.models import Source
from app.services.healing.agent import heal_source
from app.services.healing.recovery import recover_stuck_healing
from app.services.pipeline import cluster_new_articles, finalize_event
from app.services.retention import purge_expired_content
from app.services.scraping.runner import run_source

setup_logging()
log = get_logger("scheduler")

# job_id -> cron signature, so changed schedules are picked up without a restart
_job_signatures: dict[str, str] = {}


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
        source = (
            await session.execute(select(Source).where(Source.id == source_id))
        ).scalar_one_or_none()
        if source is None or not source.active:
            return

        async with httpx.AsyncClient() as http:
            outcome = await run_source(session, source, http_client=http)

        if outcome.skipped:
            return

        if outcome.status == "SUCCESS" and outcome.new_articles > 0:
            event_ids = await cluster_new_articles(session, source_id, outcome.new_articles)
            for event_id in event_ids:
                try:
                    await finalize_event(session, event_id)
                except Exception as exc:
                    log.warn("analysis.failed_in_scheduler", event=event_id, error=str(exc)[:200])

        if outcome.should_heal:
            log.warn("scraper.heal_triggered", source=source.slug)
            await heal_source(session, source.id, manual=False)
            # after healing, immediately re-run to prove recovery
            await session.refresh(source)
            if source.health_status == "HEALTHY":
                async with httpx.AsyncClient() as http:
                    await run_source(session, source, http_client=http)


def _signature(trigger_args: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in sorted(trigger_args.items()))


async def refresh_jobs(scheduler: AsyncIOScheduler) -> None:
    """Sync APScheduler jobs with active sources in DB."""
    factory = get_session_factory()
    async with factory() as session:
        sources = list(
            (await session.execute(select(Source).where(Source.active.is_(True)))).scalars()
        )
        await recover_stuck_healing(session)

    wanted: dict[str, tuple[int, str, dict]] = {}
    for source in sources:
        job_id = f"scrape:{source.slug}"
        trigger_args = cron_to_apscheduler(source.schedule)
        if trigger_args is None:
            log.warn("scheduler.bad_cron", source=source.slug, schedule=source.schedule)
            continue
        wanted[job_id] = (source.id, source.name, trigger_args)

    existing = {job.id for job in scheduler.get_jobs()}
    for job_id, (sid, name, trigger_args) in wanted.items():
        signature = _signature(trigger_args)
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
            _job_signatures[job_id] = signature
            log.info("scheduler.job_added", source=name, schedule=signature)
        elif _job_signatures.get(job_id) != signature:
            scheduler.reschedule_job(job_id, trigger=CronTrigger(**trigger_args))
            _job_signatures[job_id] = signature
            log.info("scheduler.job_rescheduled", source=name, schedule=signature)

    for job_id in existing - set(wanted.keys()):
        scheduler.remove_job(job_id)
        _job_signatures.pop(job_id, None)
        log.info("scheduler.job_removed", job=job_id)


async def main() -> None:
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone="UTC")
    await refresh_jobs(scheduler)
    await purge_expired_content()
    scheduler.add_job(
        purge_expired_content,
        CronTrigger(hour=3, minute=15),
        id="retention:articles",
        name="purge expired content",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    log.info("scheduler.started")

    # telegram subscriber bot — one poller, runs alongside the scheduler
    bot_task: asyncio.Task | None = None
    if settings.telegram_bot_token:
        from app.services.notifications.bot_subscribers import poll_forever

        bot_task = asyncio.create_task(poll_forever())
    else:
        log.info("bot.disabled_no_token")

    # periodically pick up newly added/changed sources
    while True:
        await asyncio.sleep(60)
        try:
            await refresh_jobs(scheduler)
        except Exception as exc:
            log.error("scheduler.refresh_failed", error=str(exc)[:200])
        if bot_task is not None and bot_task.done():
            exc = bot_task.exception()
            log.error("bot.task_died", error=str(exc)[:200] if exc else "unknown")
            from app.services.notifications.bot_subscribers import poll_forever

            bot_task = asyncio.create_task(poll_forever())


if __name__ == "__main__":
    asyncio.run(main())
