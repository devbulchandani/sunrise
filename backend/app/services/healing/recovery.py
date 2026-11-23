"""Recover healing events and sources left in a transient state by a crash."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.models import HealingEvent, Source

log = get_logger("healing.recovery")


async def recover_stuck_healing(session: AsyncSession) -> int:
    """Mark stale healing runs as errors and release their sources.

    A process restart during healing leaves the event RUNNING and the source
    HEALING forever. Healing normally takes seconds to a few minutes, so
    anything older than `healing_stale_minutes` is treated as abandoned.
    """
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.healing_stale_minutes)
    recovered = 0

    stale_events = list(
        (
            await session.execute(
                select(HealingEvent).where(
                    HealingEvent.status.in_(["PENDING", "RUNNING"]),
                    HealingEvent.created_at < cutoff,
                )
            )
        ).scalars()
    )
    for event in stale_events:
        event.status = "ERROR"
        event.error = "healing timed out (process restart or stalled LLM call)"
        event.timeline = [
            *(event.timeline or []),
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "stage": "healing.timeout",
                "detail": "stale healing run recovered by the scheduler",
            },
        ]
        flag_modified(event, "timeline")
        recovered += 1

    # Sources marked HEALING with no live healing event.
    active_source_ids = set(
        (
            await session.execute(
                select(HealingEvent.source_id).where(
                    HealingEvent.status.in_(["PENDING", "RUNNING"])
                )
            )
        ).scalars()
    )
    stuck_sources = list(
        (
            await session.execute(
                select(Source).where(Source.health_status == "HEALING")
            )
        ).scalars()
    )
    for source in stuck_sources:
        if source.id not in active_source_ids:
            source.health_status = "DEGRADED"
            recovered += 1

    if recovered:
        await session.commit()
        log.warn("healing.recovered_stale", count=recovered)
    return recovered
