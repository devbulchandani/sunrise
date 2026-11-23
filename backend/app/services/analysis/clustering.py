"""Event clustering: group related articles into a single market event.

Cross-outlet headlines paraphrase the same story, so a raw fuzzy ratio is not
enough: generic news templates ("X Share Price Live Updates", "Stock Price
History") can score high while describing different companies. The scorer below
strips that boilerplate and requires meaningful token overlap in addition to a
fuzzy ratio.
"""

import re
from datetime import datetime, timedelta, timezone

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.models import EventArticle, MarketEvent, utcnow

log = get_logger("analysis.cluster")

# Phrases that appear in list-page templates rather than in the story itself.
_BOILERPLATE = re.compile(
    r"\b(?:share price|stock price|rates|live updates?|live blog|"
    r"stock price history|what to know|explained|opinion)\b",
    re.I,
)

_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "for", "on", "as", "at", "with", "from",
    "and", "or", "is", "are", "be", "by", "its", "this", "that", "after", "over",
    "amid", "says", "said", "will", "may", "could", "than", "into", "about",
    "more", "less", "new", "up", "down", "out", "off", "not", "but", "has",
    "have", "had", "was", "were", "been", "who", "what", "when", "where", "why",
    "how", "his", "her", "their", "our", "your", "it", "we", "they", "he", "she",
}


def _normalize(title: str) -> str:
    text = _BOILERPLATE.sub(" ", title or "")
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return " ".join(text.split())


def _significant_tokens(title: str) -> set[str]:
    return {
        token
        for token in _normalize(title).split()
        if (len(token) >= 3 or token.isdigit()) and token not in _STOPWORDS
    }


def similarity_components(title_a: str, title_b: str) -> tuple[float, float, float]:
    """Return (combined_score, fuzzy_ratio, token_jaccard) for two headlines."""
    norm_a, norm_b = _normalize(title_a), _normalize(title_b)
    if not norm_a or not norm_b:
        return 0.0, 0.0, 0.0

    fuzzy = max(
        fuzz.token_set_ratio(norm_a, norm_b),
        fuzz.token_sort_ratio(norm_a, norm_b),
    )
    tokens_a, tokens_b = _significant_tokens(title_a), _significant_tokens(title_b)
    union = tokens_a | tokens_b
    jaccard = len(tokens_a & tokens_b) / len(union) if union else 0.0
    score = 0.75 * fuzzy + 0.25 * jaccard * 100
    return score, float(fuzzy), jaccard


def title_similarity(title_a: str, title_b: str) -> float:
    """Combined similarity in 0-100 (kept for callers/tests)."""
    return similarity_components(title_a, title_b)[0]


async def find_or_create_event(
    session: AsyncSession, article, similarity_threshold: float | None = None
):
    """Attach an article to an existing recent event if sufficiently similar,
    otherwise create a new event seeded with this article."""
    settings = get_settings()
    threshold = (
        settings.clustering_similarity_threshold
        if similarity_threshold is None
        else similarity_threshold
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

    events_result = await session.execute(
        select(MarketEvent)
        .options(selectinload(MarketEvent.articles))
        .where(MarketEvent.last_updated_at >= cutoff)
        .order_by(MarketEvent.last_updated_at.desc())
        .limit(settings.clustering_candidate_limit)
    )
    events = list(events_result.scalars())

    best_event = None
    best_score = 0.0
    best_jaccard = 0.0
    for event in events:
        candidates = [event.headline] + [a.title for a in event.articles]
        for candidate in candidates:
            score, _fuzzy, jaccard = similarity_components(article.title, candidate)
            if score > best_score:
                best_score = score
                best_jaccard = jaccard
                best_event = event

    if (
        best_event is not None
        and best_score >= threshold
        and best_jaccard >= settings.clustering_jaccard_floor
    ):
        event = best_event
        await attach_article(session, event, article)
        event.last_updated_at = utcnow()
        log.info(
            "event.updated",
            event=event.id,
            similarity=round(best_score, 1),
            jaccard=round(best_jaccard, 2),
        )
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
