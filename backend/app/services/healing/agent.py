"""The Sunrise Healing Agent.

Pipeline:
  failure -> capture context (old strategy, HTML snapshot, last good output)
          -> LLM generates candidate strategy (declarative JSON only)
          -> schema validation -> static safety checks -> dry-run on snapshot
          -> quality score vs history -> accept: activate versioned strategy
                                        -> reject: retry with feedback
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import CHANNELS, get_redis, publish
from app.llm.client import LLMError, get_llm
from app.llm.schemas import ExtractionStrategy, HealingCandidate
from app.models.models import (
    Article,
    HealingEvent,
    RawSnapshot,
    RunStatus,
    ScrapingRun,
    ScrapingStrategy,
    Source,
)
from app.services.healing.prompts import HEALING_SYSTEM_PROMPT, build_healing_user_prompt
from app.services.healing.validation import validate_candidate

log = get_logger("healing")

MAX_CANDIDATES = 3


def _append_step(event: HealingEvent, stage: str, detail: str) -> None:
    """Append to the JSON timeline and mark the column dirty so it persists."""
    entry = {"at": datetime.now(timezone.utc).isoformat(), "stage": stage, "detail": detail}
    event.timeline = [*(event.timeline or []), entry]
    flag_modified(event, "timeline")


async def _load_context(session: AsyncSession, source: Source):
    old_strategy = (
        await session.execute(
            select(ScrapingStrategy)
            .where(ScrapingStrategy.source_id == source.id)
            .order_by(ScrapingStrategy.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    snapshot = (
        await session.execute(
            select(RawSnapshot)
            .where(RawSnapshot.source_id == source.id)
            .order_by(RawSnapshot.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    failure_run = (
        await session.execute(
            select(ScrapingRun)
            .where(ScrapingRun.source_id == source.id, ScrapingRun.status == RunStatus.FAILED.value)
            .order_by(ScrapingRun.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    historical_counts = list(
        (
            await session.execute(
                select(ScrapingRun.articles_found)
                .where(
                    ScrapingRun.source_id == source.id,
                    ScrapingRun.status == RunStatus.SUCCESS.value,
                    ScrapingRun.articles_found > 0,
                )
                .order_by(ScrapingRun.started_at.desc())
                .limit(10)
            )
        ).scalars()
    )

    samples = [
        {"title": a.title, "url": a.url}
        for a in (
            await session.execute(
                select(Article).where(Article.source_id == source.id).order_by(Article.scraped_at.desc()).limit(5)
            )
        ).scalars()
    ]

    return old_strategy, snapshot, failure_run, historical_counts, samples


async def heal_source(session: AsyncSession, source_id: int, manual: bool = False):
    """Attempt to heal a broken source. Returns the HealingEvent."""
    source = (await session.execute(select(Source).where(Source.id == source_id))).scalar_one_or_none()
    if source is None:
        raise ValueError(f"source {source_id} not found")

    healing_event = HealingEvent(
        source_id=source.id,
        status="RUNNING",
        failure_reason="manual trigger" if manual else "extraction failure",
        timeline=[],
    )
    _append_step(healing_event, "healing.started", f"healing agent started for {source.slug}")
    session.add(healing_event)
    await session.flush()

    source.health_status = "HEALING"
    await session.commit()

    try:
        return await _run_healing(session, source, healing_event)
    except LLMError as exc:
        # graceful degradation: keep scraper degraded, retry later
        healing_event.status = "ERROR"
        healing_event.error = f"LLM unavailable: {exc}"[:500]
        _append_step(healing_event, "healing.llm_unavailable", str(exc)[:200])
        source.health_status = "DEGRADED"
        await session.commit()
        log.warn("healing.llm_error", source=source.slug, error=str(exc)[:200])
        return healing_event
    except Exception as exc:
        healing_event.status = "ERROR"
        healing_event.error = f"{type(exc).__name__}: {exc}"[:500]
        _append_step(healing_event, "healing.error", str(exc)[:300])
        source.health_status = "DEGRADED"
        await session.commit()
        log.error("healing.failed", source=source.slug, error=str(exc)[:300])
        return healing_event


async def _run_healing(session: AsyncSession, source: Source, healing_event: HealingEvent):
    llm = get_llm()
    if not llm.configured:
        raise LLMError("LLM_API_KEY not configured")

    old_strategy, snapshot, failure_run, historical_counts, samples = await _load_context(session, source)

    if snapshot is None:
        raise RuntimeError("no HTML snapshot available for healing — run the scraper first")
    if old_strategy is None:
        raise RuntimeError("no existing strategy found for source")

    healing_event.old_strategy_version = old_strategy.version
    healing_event.failure_reason = (
        f"{failure_run.error_type}: {failure_run.error_message}"
        if failure_run and failure_run.error_message
        else "extraction failure"
    )[:1000]
    healing_event.failure_type = failure_run.error_type if failure_run else None

    candidate_scores = []
    feedback = ""

    for attempt in range(1, MAX_CANDIDATES + 1):
        _append_step(
            healing_event,
            "healing.generating",
            f"generating candidate strategy #{attempt}" + (f" after feedback: {feedback[:150]}" if feedback else ""),
        )
        await session.commit()
        log.info("healing.candidate_start", source=source.slug, attempt=attempt)

        user_prompt = build_healing_user_prompt(
            source.name,
            source.url,
            old_strategy.strategy_json,
            healing_event.failure_reason + (f"\nPrevious attempt rejected because: {feedback}" if feedback else ""),
            samples,
            snapshot.html,
        )

        candidate: HealingCandidate = await llm.structured(
            HealingCandidate, HEALING_SYSTEM_PROMPT, user_prompt, max_tokens=8000
        )
        healing_event.candidate_count = attempt
        _append_step(
            healing_event,
            "healing.candidate_generated",
            candidate.reasoning[:300] or "candidate strategy generated",
        )
        await session.commit()
        log.info("healing.candidate_generated", source=source.slug, attempt=attempt)

        validation = validate_candidate(
            candidate.strategy,
            snapshot.html,
            base_url=source.url,
            historical_counts=historical_counts,
        )
        candidate_scores.append(validation.summary())
        healing_event.candidate_scores = list(candidate_scores)
        flag_modified(healing_event, "candidate_scores")
        _append_step(
            healing_event,
            "healing.validated",
            f"score={validation.score:.0f} articles={validation.articles_found} "
            + ("; ".join(validation.reasons) or ""),
        )
        log.info(
            "healing.candidate_scored",
            source=source.slug,
            attempt=attempt,
            score=round(validation.score),
            accepted=validation.accepted,
        )

        if validation.accepted:
            new_version = old_strategy.version + 1
            old_strategy.is_active = False
            session.add(
                ScrapingStrategy(
                    source_id=source.id,
                    version=new_version,
                    strategy_json=candidate.strategy.model_dump(),
                    validation_score=round(validation.score, 1),
                    is_active=True,
                    created_by="healing_agent",
                )
            )
            source.current_strategy_version = new_version
            source.health_status = "HEALTHY"
            source.consecutive_failures = 0

            healing_event.new_strategy_version = new_version
            healing_event.validation_score = round(validation.score, 1)
            healing_event.status = "SUCCESS"
            healing_event.articles_recovered = validation.articles_found
            _append_step(
                healing_event,
                "healing.activated",
                f"strategy v{new_version} activated (score {validation.score:.0f})",
            )
            _append_step(
                healing_event,
                "scraper.recovered",
                f"validation passed with {validation.articles_found} articles recovered",
            )
            await session.commit()

            settings = get_settings()
            redis = get_redis(settings.redis_url)
            await publish(
                redis,
                CHANNELS["scraper_healed"],
                {
                    "source": source.slug,
                    "source_name": source.name,
                    "old_version": healing_event.old_strategy_version,
                    "new_version": new_version,
                    "score": round(validation.score),
                    "articles_recovered": validation.articles_found,
                    "timeline": healing_event.timeline,
                },
            )
            log.info(
                "healing.accepted",
                source=source.slug,
                version=new_version,
                score=round(validation.score),
            )
            return healing_event

        feedback = "; ".join(validation.reasons)

    healing_event.status = "REJECTED"
    healing_event.timeline = [*(healing_event.timeline or []), *[]]
    _append_step(healing_event, "healing.rejected", f"all {MAX_CANDIDATES} candidates rejected")
    source.health_status = "FAILED"
    await session.commit()
    log.warn("healing.rejected", source=source.slug)
    return healing_event
