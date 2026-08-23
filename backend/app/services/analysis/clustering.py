"""Event clustering: group related articles into a single market event."""

from datetime import datetime, timedelta, timezone

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.models import EventArticle, MarketEvent, utcnow

log = get_logger("analysis.cluster")


def title_similarity(a: str, b: str) -> float:
    return max(
        fuzz.token_set_ratio(a.lower(), b.lower()),
        fuzz.token_sort_ratio(a.lower(), b.lower()),
    )


async def find_or_create_event(
    session: AsyncSession, article, similarity_threshold: float = 80.0
):
    """Attach an article to an existing recent event if sufficiently similar,
    otherwise create a new event seeded with this article."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=48)

    events_result = await session.execute(
        select(MarketEvent)
        .options(selectinload(MarketEvent.articles))
        .where(MarketEvent.last_updated_at >= cutoff)
        .order_by(MarketEvent.last_updated_at.desc())
        .limit(100)
    )
    events = list(events_result.scalars())

    best_event = None
    best_score = 0.0
    for event in events:
        candidates = [event.headline] + [a.title for a in event.articles]
        score = max(title_similarity(article.title, c) for c in candidates)
        if score > best_score:
            best_score = score
            best_event = event

    if best_event is not None and best_score >= similarity_threshold:
        event = best_event
        exists = await session.execute(
            select(EventArticle.id).where(
                EventArticle.event_id == event.id,
                EventArticle.article_id == article.id,
            )
        )
        if exists.scalar() is None:
            session.add(EventArticle(event_id=event.id, article_id=article.id))
            event.last_updated_at = utcnow()
            log.info("event.updated", event=event.id, similarity=round(best_score, 1))
    else:
        event = MarketEvent(headline=article.title[:500], summary=(article.summary or "")[:2000])
        session.add(event)
        await session.flush()
        session.add(EventArticle(event_id=event.id, article_id=article.id))
        log.info("event.created", event=event.id, headline=event.headline[:80])

    return event


async def attach_article(session: AsyncSession, event: MarketEvent, article) -> None:
    exists = await session.execute(
        select(EventArticle.id).where(
            EventArticle.event_id == event.id, EventArticle.article_id == article.id
        )
    )
    if not exists.scalar():
        session.add(EventArticle(event_id=event.id, article_id=article.id))
