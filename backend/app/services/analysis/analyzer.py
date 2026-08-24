"""AI financial intelligence: analyze market events with structured LLM output."""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import publish, get_redis, CHANNELS
from app.llm.client import get_llm
from app.llm.schemas import MarketAnalysis
from app.models.models import Article, EventAsset, MarketEvent, Source, utcnow
from app.services.analysis.clustering import attach_article
from app.services.analysis.urgency import compute_urgency, urgency_level

log = get_logger("analysis")

SYSTEM_PROMPT = """You are a senior financial markets analyst for Sunrise, an autonomous \
market intelligence platform. You analyze news events and assess their potential relevance \
to financial markets.

STRICT RULES:
- You provide interpretation, never guarantees. Markets are uncertain; your confidence \
numbers must reflect that.
- Distinguish clearly between what factually happened (from the article) and your \
interpretation of why it may matter.
- Never predict specific price movements or magnitudes.
- Respond ONLY with valid JSON matching this schema:

{
  "summary": "2-3 sentence factual summary of what happened",
  "category": "one of MONETARY_POLICY|INFLATION|EMPLOYMENT|GDP|REGULATION|CRYPTO|EARNINGS|MERGERS_ACQUISITIONS|GEOPOLITICS|COMMODITIES|MARKET_MOVEMENT|BANKING|TECHNOLOGY|AI|ENERGY|IPO|OTHER. Use IPO when the news is about a company filing, pricing, or debuting an initial public offering.",
  "sentiment": "BULLISH|BEARISH|NEUTRAL (expected direction for affected mainstream assets)",
  "market_impact": "LOW|MEDIUM|HIGH|CRITICAL",
  "urgency": 0-100 integer,
  "confidence": 0-100 integer (your confidence in this assessment),
  "affected_assets": [{"symbol": "SPY", "impact": "positive|negative|neutral", "confidence": 0-100}],
  "affected_sectors": ["technology", ...],
  "affected_regions": ["United States", ...],
  "affected_markets": ["US Equities", "European Equities", "Crypto", "Commodities", "Government Bonds", "FX", "Emerging Markets", "Energy Markets"],
  "reason": "why this may matter — clearly framed as assessment, e.g. 'This could...' "
}

Use well-known symbols: SPY, QQQ, BTC, ETH, GOLD, OIL, DXY, NVDA, TSLA, AAPL, EUR, GBP, JPY.
For affected_markets use broad market labels such as: US Equities, European Equities,
Asian Equities, Crypto, Commodities, Government Bonds, Corporate Bonds, FX, Energy Markets,
Emerging Markets, Real Estate, Money Markets. Only include markets genuinely relevant.
If the event is not market-relevant, urgency should be low and assets empty."""


def _build_user_prompt(event, articles, source_names: list[str]) -> str:
    article_texts = []
    for i, article in enumerate(articles[:5], 1):
        body = f"TITLE: {article.title}"
        if article.summary:
            body += f"\nSUMMARY: {article.summary[:1500]}"
        if article.published_at:
            body += f"\nPUBLISHED: {article.published_at.isoformat()}"
        article_texts.append(f"ARTICLE {i} ({source_names[i-1] if i <= len(source_names) else 'unknown'}):\n{body}")

    return (
        f"Analyze this market event. Multiple sources may report the same story.\n\n"
        + "\n\n".join(article_texts)
        + "\n\nRespond only with the JSON object."
    )


async def analyze_event(session: AsyncSession, event_id: int) -> MarketEvent | None:
    """Run AI analysis on an event, store it, compute blended urgency, broadcast."""
    settings = get_settings()
    result = await session.execute(
        select(MarketEvent)
        .options(selectinload(MarketEvent.articles).selectinload(Article.source))
        .where(MarketEvent.id == event_id)
    )
    event = result.unique().scalar_one_or_none()
    if event is None:
        return None

    articles = list(event.articles)
    if not articles:
        return event

    llm = get_llm()
    if not llm.configured:
        log.warn("analysis.skipped_no_llm", event=event.id)
        return event

    try:
        analysis: MarketAnalysis = await llm.structured(
            MarketAnalysis,
            SYSTEM_PROMPT,
            _build_user_prompt(
                event,
                articles,
                [a.source.name if a.source else "unknown" for a in articles],
            ),
        )
    except Exception as exc:
        log.warn("analysis.failed", event=event.id, error=str(exc)[:200])
        event.analysis_status = "PENDING"  # retry later
        await session.commit()
        return event

    best_credibility = max(
        (a.source.credibility if a.source else 0.5) for a in articles
    )
    urgency = compute_urgency(
        ai_urgency=analysis.urgency,
        source_credibility=best_credibility,
        category=analysis.category,
        article_count=len(articles),
        affected_asset_count=len(analysis.affected_assets),
        market_impact=analysis.market_impact,
    )

    # first analysis sets the headline; later ones keep the original but refresh scores
    if len(articles) == 1:
        event.headline = articles[0].title[:500]

    # WHAT HAPPENED: prefer the article's own summary (HTML-stripped); fall back
    # to the LLM's factual summary so the field is never empty
    import re as _re

    factual = ""
    for article in articles:
        raw = (article.summary or "").strip()
        if raw:
            factual = _re.sub(r"<[^>]+>", " ", raw)
            factual = _re.sub(r"\s+", " ", factual).strip()
            break
    event.summary = factual[:2000] or analysis.summary
    event.ai_summary = analysis.summary
    event.category = analysis.category
    event.sentiment = analysis.sentiment
    event.market_impact = analysis.market_impact
    event.confidence = analysis.confidence
    event.reason = analysis.reason
    event.affected_markets = analysis.affected_markets
    event.urgency = urgency
    event.analysis_status = "DONE"
    event.last_updated_at = utcnow()

    # replace assets
    from sqlalchemy import delete

    await session.execute(EventAsset.__table__.delete().where(EventAsset.event_id == event.id))
    for asset in analysis.affected_assets:
        session.add(
            EventAsset(
                event_id=event.id,
                symbol=asset.symbol.upper(),
                impact=asset.impact,
                confidence=asset.confidence,
            )
        )
    await session.flush()

    level = urgency_level(urgency)
    log.info(
        "analysis.completed",
        event=event.id,
        urgency=urgency,
        level=level,
        category=analysis.category,
    )

    redis = get_redis(settings.redis_url)
    payload = {
        "event_id": event.id,
        "headline": event.headline[:200],
        "urgency": urgency,
        "level": level,
        "sentiment": event.sentiment,
        "category": event.category,
    }
    await publish(redis, CHANNELS["new_event"], payload)
    if level in ("HIGH", "CRITICAL"):
        await publish(redis, CHANNELS["critical_alert"], payload)

    await session.commit()
    return event
