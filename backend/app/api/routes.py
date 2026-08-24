"""FastAPI routes."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.db.session import get_db
from app.llm.client import LLMError, get_llm
from app.models.models import (
    Article,
    RawSnapshot,
    EventAsset,
    HealingEvent,
    MarketEvent,
    Notification,
    RunStatus,
    ScrapingRun,
    ScrapingStrategy,
    Source,
    User,
    UserPreference,
)
from app.schemas.schemas import (
    EventDetail,
    EventListItem,
    HealingEventOut,
    PreferencesIn,
    PreferencesOut,
    RunOut,
    ScraperHealth,
    SourceOut,
    StatsOut,
    StrategyOut,
)
from app.services.healing.agent import heal_source
from app.services.scraping.health import compute_metrics  # noqa: F401

log = get_logger("api")
router = APIRouter(prefix="/api")


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Gate debug/admin endpoints when ADMIN_TOKEN is set."""
    settings = get_settings()
    if settings.admin_token and x_admin_token != settings.admin_token:
        raise HTTPException(status_code=403, detail="admin token required")


# ---------------------------------------------------------------- health


@router.get("/health")
async def health():
    return {"status": "ok", "service": "sunrise", "time": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------- events


def _event_to_list_item(event: MarketEvent, article_count: int) -> EventListItem:
    return EventListItem(
        id=event.id,
        affected_markets=list(getattr(event, "affected_markets", []) or []),
        headline=event.headline,
        summary=event.summary,
        ai_summary=event.ai_summary,
        category=event.category,
        sentiment=event.sentiment,
        market_impact=event.market_impact,
        urgency=event.urgency,
        confidence=event.confidence,
        analysis_status=event.analysis_status,
        first_detected_at=event.first_detected_at,
        last_updated_at=event.last_updated_at,
        article_count=article_count,
    )


@router.get("/events")
async def list_events(
    min_urgency: int = Query(default=0, ge=0, le=100),
    level: str | None = None,
    category: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(MarketEvent).order_by(MarketEvent.last_updated_at.desc()).limit(300)
    if min_urgency:
        stmt = stmt.where(MarketEvent.urgency >= min_urgency)
    if category:
        stmt = stmt.where(MarketEvent.category == category.upper())
    result = await db.execute(stmt.options(selectinload(MarketEvent.articles)))
    events = list(result.unique().scalars())

    items = []
    for event in events:
        urgency = event.urgency
        if level and _urgency_level(urgency).upper() != level.upper():
            continue
        items.append(_event_to_list_item(event, len(event.articles)))
        if len(items) >= limit:
            break

    return {"events": [item.model_dump(mode="json") for item in items]}


def _urgency_level(score: int) -> str:
    from app.services.analysis.urgency import urgency_level

    return urgency_level(score)


@router.get("/events/{event_id}")
async def event_detail(event_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MarketEvent)
        .options(
            selectinload(MarketEvent.articles).selectinload(Article.source),
        )
        .where(MarketEvent.id == event_id)
    )
    event = result.unique().scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")

    assets_result = await db.execute(select(EventAsset).where(EventAsset.event_id == event.id))
    assets = list(assets_result.scalars())

    sources_map: dict[int, dict] = {}
    articles_out = []
    primary_url = None
    for article in sorted(event.articles, key=lambda a: a.scraped_at):
        source_name = article.source.name if article.source else None
        if article.source:
            if article.source.id not in sources_map:
                entry = {
                    "id": article.source.id,
                    "slug": article.source.slug,
                    "name": article.source.name,
                    "url": article.source.url,
                    "article_url": article.url,  # deep-link to the actual article
                    "type": article.source.type,
                    "schedule": article.source.schedule,
                    "category": article.source.category,
                    "credibility": article.source.credibility,
                    "active": article.source.active,
                    "health_status": article.source.health_status,
                    "current_strategy_version": article.source.current_strategy_version,
                    "last_success_at": article.source.last_success_at,
                    "last_failure_at": article.source.last_failure_at,
                }
                sources_map[article.source.id] = entry
            if primary_url is None:
                primary_url = article.url
        articles_out.append(
            {
                "id": article.id,
                "title": article.title,
                "url": article.url,
                "published_at": article.published_at,
                "scraped_at": article.scraped_at,
                "source_name": source_name,
            }
        )

    detail = _event_to_list_item(event, len(event.articles)).model_dump(mode="json")
    detail.update(
        {
            "reason": event.reason,
            "affected_markets": list(event.affected_markets or []),
            "ipo_research": event.ipo_research,
            "affected_assets": [
                {"symbol": a.symbol, "impact": a.impact, "confidence": a.confidence} for a in assets
            ],
            "sources": list(sources_map.values()),
            "articles": [
                {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in a.items()}
                for a in articles_out
            ],
        }
    )
    return detail


# ---------------------------------------------------------------- sources & scrapers


@router.get("/sources")
async def list_sources(db: AsyncSession = Depends(get_db)):
    sources = (await db.execute(select(Source).order_by(Source.id))).scalars()
    return {"sources": [SourceOut.model_validate(s).model_dump(mode="json") for s in sources]}


@router.get("/scrapers/health")
async def scrapers_health(db: AsyncSession = Depends(get_db)):
    sources = (await db.execute(select(Source).order_by(Source.id))).scalars()
    out = []
    day_ago = datetime.now(timezone.utc) - timedelta(hours=24)

    for source in sources:
        runs_result = await db.execute(
            select(ScrapingRun)
            .where(ScrapingRun.source_id == source.id)
            .order_by(ScrapingRun.started_at.desc())
            .limit(30)
        )
        runs = list(runs_result.scalars())

        recent = [r for r in runs if r.started_at.replace(tzinfo=None) >= day_ago.replace(tzinfo=None)]
        success_rate = (
            round(sum(1 for r in recent if r.status == "SUCCESS") / len(recent), 3) if recent else None
        )

        healing_count_result = await db.execute(
            select(func.count()).select_from(HealingEvent).where(HealingEvent.source_id == source.id)
        )
        healing_total = healing_count_result.scalar() or 0

        active_healing_result = await db.execute(
            select(HealingEvent.id)
            .where(HealingEvent.source_id == source.id, HealingEvent.status.in_(["PENDING", "RUNNING"]))
            .order_by(HealingEvent.created_at.desc())
            .limit(1)
        )
        active_healing = active_healing_result.scalar_one_or_none()

        out.append(
            {
                "source_id": source.id,
                "slug": source.slug,
                "name": source.name,
                "health_status": source.health_status,
                "strategy_version": source.current_strategy_version,
                "last_run_at": runs[0].started_at if runs else None,
                "last_success_at": source.last_success_at,
                "last_failure_at": source.last_failure_at,
                "last_error_type": next((r.error_type for r in runs if r.error_type), None),
                "last_articles_found": next((r.articles_found for r in runs), None),
                "success_rate_24h": success_rate,
                "healing_attempts_total": healing_total,
                "active_healing_event_id": active_healing,
            }
        )
    return {"scrapers": out}


@router.get("/sources/{source_id}")
async def source_detail(source_id: int, db: AsyncSession = Depends(get_db)):
    source = (await db.execute(select(Source).where(Source.id == source_id))).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")

    runs_result = await db.execute(
        select(ScrapingRun)
        .where(ScrapingRun.source_id == source_id)
        .order_by(ScrapingRun.started_at.desc())
        .limit(20)
    )
    strategies_result = await db.execute(
        select(ScrapingStrategy)
        .where(ScrapingStrategy.source_id == source_id)
        .order_by(ScrapingStrategy.version.desc())
    )
    healing_result = await db.execute(
        select(HealingEvent)
        .where(HealingEvent.source_id == source_id)
        .order_by(HealingEvent.created_at.desc())
        .limit(20)
    )
    all_runs_list = list(runs_result.scalars())
    successful_runs = [r for r in all_runs_list if r.status == "SUCCESS" and r.articles_found]
    avg_articles = (
        round(sum(r.articles_found for r in successful_runs) / len(successful_runs), 1)
        if successful_runs else 0
    )
    all_runs = list(runs_result.scalars())
    response_times = [r.response_time_ms for r in all_runs if r.response_time_ms]
    avg_response = round(sum(response_times) / len(response_times)) if response_times else None

    return {
        "source": SourceOut.model_validate(source).model_dump(mode="json"),
        "runs": [RunOut.model_validate(r).model_dump(mode="json") for r in runs_result.scalars()],
        "strategies": [
            StrategyOut.model_validate(s).model_dump(mode="json") for s in strategies_result.scalars()
        ],
        "healing_history": [
            HealingEventOut.model_validate(h).model_dump(mode="json") for h in healing_result.scalars()
        ],
        "avg_articles_per_run": avg_articles,
    }


@router.get("/scrapers/{source_id}/runs")
async def scraper_runs(source_id: int, limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ScrapingRun)
        .where(ScrapingRun.source_id == source_id)
        .order_by(ScrapingRun.started_at.desc())
        .limit(min(limit, 200))
    )
    return {"runs": [RunOut.model_validate(r).model_dump(mode="json") for r in result.scalars()]}


@router.get("/scrapers/{source_id}/articles")
async def scraper_articles(source_id: int, limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Article)
        .where(Article.source_id == source_id)
        .order_by(Article.scraped_at.desc())
        .limit(min(limit, 200))
    )
    articles = result.scalars()
    return {
        "articles": [
            {
                "id": a.id,
                "title": a.title,
                "url": a.url,
                "summary": a.summary,
                "published_at": a.published_at,
                "scraped_at": a.scraped_at,
            }
            for a in articles
        ]
    }


@router.get("/scrapers/{source_id}/healing-history")
async def healing_history(source_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(HealingEvent)
        .where(HealingEvent.source_id == source_id)
        .order_by(HealingEvent.created_at.desc())
        .limit(50)
    )
    return {
        "healing_events": [
            HealingEventOut.model_validate(h).model_dump(mode="json") for h in result.scalars()
        ]
    }


_manual_trigger_locks: set[int] = set()


@router.post("/scrapers/{source_id}/run")
async def trigger_scrape(source_id: int, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin)):
    if source_id in _manual_trigger_locks:
        raise HTTPException(status_code=429, detail="a run is already in progress")
    source = (await db.execute(select(Source).where(Source.id == source_id))).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    _manual_trigger_locks.add(source_id)
    try:
        # enqueue on the real arq queue so clustering/analysis chain normally
        from arq import create_pool
        from arq.connections import RedisSettings

        settings = get_settings()
        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        try:
            await pool.enqueue_job("scrape_source", source_id)
        finally:
            await pool.aclose()
        return {"triggered": True, "queued": "scrape_source", "source": source.slug}
    finally:
        _manual_trigger_locks.discard(source_id)


@router.post("/scrapers/{source_id}/heal")
async def trigger_heal(source_id: int, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin)):
    source = (await db.execute(select(Source).where(Source.id == source_id))).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    healing_event = await heal_source(db, source_id, manual=True)
    return {
        "triggered": True,
        "status": healing_event.status,
        "validation_score": healing_event.validation_score,
        "new_version": healing_event.new_strategy_version,
        "timeline": healing_event.timeline,
    }


@router.post("/scrapers/{source_id}/test-strategy")
async def test_strategy(source_id: int, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin)):
    """Dry-run the active strategy against the latest snapshot without side effects."""
    strategy_result = await db.execute(
        select(ScrapingStrategy)
        .where(ScrapingStrategy.source_id == source_id, ScrapingStrategy.is_active.is_(True))
    )
    strategy = strategy_result.scalar_one_or_none()
    snapshot_result = await db.execute(
        select(RawSnapshot)
        .where(RawSnapshot.source_id == source_id)
        .order_by(RawSnapshot.created_at.desc())
        .limit(1)
    )
    snapshot = snapshot_result.scalar_one_or_none()
    if strategy is None or snapshot is None:
        raise HTTPException(status_code=400, detail="need an active strategy and a stored snapshot")

    from app.llm.schemas import ExtractionStrategy
    from app.services.healing.validation import validate_candidate

    counts_result = await db.execute(
        select(ScrapingRun.articles_found)
        .where(
            ScrapingRun.source_id == source_id,
            ScrapingRun.status == RunStatus.SUCCESS.value,
            ScrapingRun.articles_found > 0,
        )
        .limit(10)
    )
    validation = validate_candidate(
        ExtractionStrategy.model_validate(strategy.strategy_json),
        snapshot.html,
        base_url=snapshot.url,
        historical_counts=list(counts_result.scalars()),
    )
    return validation.summary()


# ---------------------------------------------------------------- stats


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    settings = get_settings()

    async def count(model, *conditions):
        q = select(func.count()).select_from(model)
        for c in conditions:
            q = q.where(c)
        return (await db.execute(q)).scalar() or 0

    redis = get_redis(settings.redis_url)
    try:
        queue_keys = ["sunrise:queue", "arq:queue"]
        pending = sum(int(await redis.llen(k) or 0) for k in queue_keys)
    except Exception:
        pending = 0

    articles_count = await count(Article)
    events_count = await count(MarketEvent)
    alerts_sent = await count(Notification, Notification.status == "SENT")
    failures = await count(ScrapingRun, ScrapingRun.error_type.isnot(None))
    healings = await count(HealingEvent, HealingEvent.status == "SUCCESS")
    llm_calls = await count(HealingEvent) + events_count  # approximation of LLM usage
    jobs_processed = (await count(ScrapingRun)) + events_count + healings

    return {
        "jobs_processed": jobs_processed,
        "jobs_pending": pending,
        "jobs_failed": failures,
        "articles_scraped": articles_count,
        "events_detected": events_count,
        "alerts_sent": alerts_sent,
        "scraper_failures": failures,
        "scraper_healings": healings,
        "llm_calls": llm_calls,
    }


# ---------------------------------------------------------------- preferences


DEMO_EMAIL = "demo@sunrise.local"


@router.get("/preferences")
async def get_preferences(db: AsyncSession = Depends(get_db)):
    pref = await _get_or_create_demo_user(db)
    return pref.model_dump(mode="json")


@router.put("/preferences")
async def update_preferences(body: PreferencesIn, db: AsyncSession = Depends(get_db)):
    user, pref = await _get_demo_user_and_pref(db)
    user.email = body.email or user.email
    user.telegram_chat_id = body.telegram_chat_id
    pref.minimum_urgency = body.minimum_urgency
    pref.asset_preferences = [a.upper().strip()[:16] for a in body.asset_preferences]
    pref.category_preferences = [c.lower().strip()[:32] for c in body.category_preferences]
    pref.email_enabled = body.email_enabled
    pref.telegram_enabled = body.telegram_enabled
    await db.commit()
    await db.refresh(user)
    await db.refresh(pref)
    return PreferencesOut(
        user_id=user.id,
        email=user.email,
        telegram_chat_id=user.telegram_chat_id,
        minimum_urgency=pref.minimum_urgency,
        asset_preferences=pref.asset_preferences,
        category_preferences=pref.category_preferences,
        email_enabled=pref.email_enabled,
        telegram_enabled=pref.telegram_enabled,
    ).model_dump(mode="json")


async def _get_demo_user_and_pref(db: AsyncSession):
    user = (await db.execute(select(User).where(User.email == DEMO_EMAIL))).scalar_one_or_none()
    if user is None:
        user = User(email=DEMO_EMAIL)
        db.add(user)
        await db.flush()
    pref = (
        await db.execute(select(UserPreference).where(UserPreference.user_id == user.id))
    ).scalar_one_or_none()
    if pref is None:
        pref = UserPreference(user_id=user.id)
        db.add(pref)
        await db.flush()
    return user, pref


async def _get_or_create_demo_user(db: AsyncSession) -> PreferencesOut:
    user, pref = await _get_demo_user_and_pref(db)
    await db.commit()
    return PreferencesOut(
        user_id=user.id,
        email=user.email,
        telegram_chat_id=user.telegram_chat_id,
        minimum_urgency=pref.minimum_urgency,
        asset_preferences=pref.asset_preferences,
        category_preferences=pref.category_preferences,
        email_enabled=pref.email_enabled,
        telegram_enabled=pref.telegram_enabled,
    )


# ---------------------------------------------------------------- SSE stream


@router.get("/stream")
async def stream(request_headers: dict | None = None):
    """Server-Sent Events stream fed by Redis pub/sub."""
    settings = get_settings()

    async def event_generator():
        redis = get_redis(settings.redis_url)
        pubsub = redis.pubsub()
        await pubsub.subscribe(*[
            "sunrise:events:new",
            "sunrise:alerts:critical",
            "sunrise:scrapers:failure",
            "sunrise:scrapers:healed",
        ])
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if message is None:
                    yield ": keepalive\n\n"
                    continue
                channel = message.get("channel", "")
                kind = channel.split(":")[-2] if ":" in channel else channel
                data = message.get("data", "{}")
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    payload = {}
                yield f"event: {kind}\ndata: {json.dumps(payload)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
