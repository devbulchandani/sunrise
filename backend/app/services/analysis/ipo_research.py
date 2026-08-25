"""Agentic IPO research pipeline.

When an event is categorized as IPO, Sunrise runs a multi-step research agent:

  1. EXTRACT   — pull company name, exchange and IPO terms from the event's articles
  2. RESEARCH  — agentic tool use: Bright Data SERP search + page fetches to gather
                 public information about the company (falls back to LLM knowledge,
                 explicitly marked unverified, when tools are unavailable)
  3. SYNTHESIZE— structured IPIOResearch: overview, business model, financials,
                 strengths, risks, valuation notes, considerations

Everything produced is AI research with confidence levels — never investment
advice. The output always carries the disclaimer.
"""

from datetime import datetime, timezone
from typing import Literal

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.core.redis import CHANNELS, get_redis, publish
from app.core.config import get_settings
from app.llm.client import LLMError, get_llm
from app.models.models import MarketEvent, utcnow

log = get_logger("analysis.ipo")


# ---------------------------------------------------------------- schemas


class ResearchDecision(BaseModel):
    action: Literal["search", "fetch", "done"]
    query: str = ""
    url: str = ""


class IPOExtraction(BaseModel):
    company_name: str = ""
    ticker: str = ""
    exchange: str = ""
    ipo_terms: list[str] = Field(default_factory=list, max_length=8)
    is_ipo_event: bool = False


class IPIOResearch(BaseModel):
    company_name: str
    ticker: str = ""
    exchange: str = ""
    sector: str = ""
    company_overview: str = Field(min_length=20, max_length=2000)
    business_model: str = Field(default="", max_length=1500)
    key_financials: list[str] = Field(default_factory=list, max_length=8)
    ipo_terms: list[str] = Field(default_factory=list, max_length=8)
    strengths: list[str] = Field(default_factory=list, max_length=6)
    risks: list[str] = Field(default_factory=list, max_length=6)
    valuation_notes: str = Field(default="", max_length=1200)
    use_of_proceeds: str = Field(default="", max_length=800)
    considerations: list[str] = Field(default_factory=list, max_length=8)
    research_confidence: int = Field(ge=0, le=100)
    sources_used: list[str] = Field(default_factory=list, max_length=8)
    researched_at: str = ""


# ---------------------------------------------------------------- tools


from app.services.analysis.tools import fetch_page as _tool_fetch
from app.services.analysis.tools import tools_available, web_search as _tool_search


# ---------------------------------------------------------------- pipeline

EXTRACT_SYSTEM = """You extract IPO facts from news. Respond only with JSON:
{"company_name": "...", "ticker": "...", "exchange": "...",
 "ipo_terms": ["price range $X-$Y", "raising $Z", ...],
 "is_ipo_event": true/false}
If the news is not about an IPO, set is_ipo_event false and leave fields empty."""

RESEARCH_SYSTEM = """You are the Sunrise IPO research agent. You investigate a company
that is going public by issuing web searches and reading pages. Available tools:
  search("<query>")  — web search, returns titles/urls/snippets
  fetch("<url>")     — read a page as text

Decide what to look up next. Respond ONLY with JSON, either:
{"action": "search", "query": "..."}
{"action": "fetch", "url": "..."}
{"action": "done"}

Run at most 3 tool calls total. Prioritize: what the company does, its financials,
the IPO terms (price range / valuation / amount raised), and analyst commentary."""

SYNTH_SYSTEM = """You are the Sunrise IPO research analyst. Using the gathered research,
produce a structured due-diligence brief for retail readers.

STRICT RULES:
- Distinguish verified facts (from articles/research) from your interpretation.
- NEVER recommend buying or not buying. Frame outcomes as "considerations".
- If information is missing, say so explicitly rather than inventing it.
- Respond ONLY with JSON:
{
  "company_name": "...", "ticker": "...", "exchange": "...", "sector": "...",
  "company_overview": "what the company actually does, 2-4 sentences",
  "business_model": "how it makes money",
  "key_financials": ["revenue: ...", "growth: ...", "profitability: ..."],
  "ipo_terms": ["price range", "valuation", "amount raised", "lead underwriters"],
  "strengths": ["..."],
  "risks": ["..."],
  "valuation_notes": "how the IPO is priced relative to peers/comps, as far as known",
  "use_of_proceeds": "what the company says it will do with the money",
  "considerations": ["questions and factors a reader should weigh, not advice"],
  "research_confidence": 0-100,
  "sources_used": ["url or 'article corpus' or 'model knowledge (unverified)'"]
}"""


async def _llm_with_retry(llm, schema, system: str, user: str, max_tokens: int, attempts: int = 3):
    """LLM call with backoff — the stealth upstream rate-limits intermittently."""
    import asyncio as _asyncio

    for attempt in range(attempts):
        try:
            return await llm.structured(schema, system, user, max_tokens=max_tokens)
        except LLMError as exc:
            if attempt == attempts - 1:
                raise
            wait = 15 * (attempt + 1)
            log.warn("ipo.llm_retry", attempt=attempt + 1, wait=wait, error=str(exc)[:120])
            await _asyncio.sleep(wait)


async def run_ipo_research(session: AsyncSession, event_id: int) -> dict | None:
    """Full agentic pipeline for one event. Returns and persists IPIOResearch."""
    llm = get_llm()
    if not llm.configured:
        log.warn("ipo.no_llm", event=event_id)
        return None

    result = await session.execute(
        select(MarketEvent)
        .options(selectinload(MarketEvent.articles))
        .where(MarketEvent.id == event_id)
    )
    event = result.unique().scalar_one_or_none()
    if event is None:
        return None

    # ---- step 1: extract
    corpus = "\n\n".join(
        f"TITLE: {a.title}\nSUMMARY: {a.summary or ''}" for a in event.articles[:5]
    )[:6000]
    extraction = await _llm_with_retry(
        llm,
        IPOExtraction,
        EXTRACT_SYSTEM,
        f"ARTICLES:\n{corpus}\n\nHEADLINE: {event.headline}",
        max_tokens=800,
    )
    if not extraction.is_ipo_event or not extraction.company_name:
        log.info("ipo.not_ipo", event=event_id)
        return None

    log.info("ipo.extracted", event=event_id, company=extraction.company_name)

    # ---- step 2: agentic research (tool loop)
    research_notes: list[str] = []
    sources_used: list[str] = []
    has_tools = tools_available()

    if has_tools:
        conversation = [
            f"COMPANY: {extraction.company_name}",
            f"TICKER: {extraction.ticker or 'unknown'}",
            f"EXCHANGE: {extraction.exchange or 'unknown'}",
            f"IPO TERMS FROM NEWS: {extraction.ipo_terms or 'none mentioned'}",
            f"NEWS CONTEXT: {corpus[:1500]}",
        ]
        for _ in range(3):
            try:
                decision = await _llm_with_retry(
                    llm,
                    ResearchDecision,
                    RESEARCH_SYSTEM,
                    "\n".join(conversation[-6:]),
                    max_tokens=300,
                    attempts=2,
                )
            except LLMError:
                # rate limited mid-research — synthesize with what we have
                log.warn("ipo.decision_bailout", event=event_id)
                break
            if decision.action == "done":
                break
            if decision.action == "search" and decision.query:
                conversation.append(f"> search({decision.query!r})")
                results = _tool_search(decision.query)
                for r in results[:5]:
                    conversation.append(f"RESULT: {r['title']} — {r['snippet'][:200]} ({r['url']})")
                    sources_used.append(r["url"])
                if not results:
                    conversation.append("RESULT: no results")
            elif decision.action == "fetch" and decision.url:
                conversation.append(f"> fetch({decision.url[:80]!r})")
                page = _tool_fetch(decision.url)
                conversation.append(f"PAGE TEXT: {page[:2500] or '(empty)'}")
                if decision.url not in sources_used:
                    sources_used.append(decision.url)
        research_notes = [c for c in conversation if c.startswith(("RESULT:", "PAGE TEXT:"))]
        log.info("ipo.researched", event=event_id, tool_calls=len(research_notes))
    else:
        research_notes = ["(web tools unavailable — using model knowledge, UNVERIFIED)"]

    # ---- step 3: synthesize
    synthesis_input = (
        f"COMPANY: {extraction.company_name} ({extraction.ticker or 'ticker unknown'}, "
        f"{extraction.exchange or 'exchange unknown'})\n"
        f"IPO TERMS FROM NEWS: {extraction.ipo_terms}\n\n"
        f"RESEARCH NOTES:\n" + "\n".join(research_notes)[:9000] +
        (f"\n\nNOTE: web research tools were unavailable; mark model-knowledge claims as unverified."
         if not has_tools else "")
    )
    research = await _llm_with_retry(
        llm, IPIOResearch, SYNTH_SYSTEM, synthesis_input, max_tokens=3000
    )
    if not sources_used:
        sources_used = ["article corpus", "model knowledge (unverified)"]
    research.sources_used = sources_used[:8]
    research.researched_at = datetime.now(timezone.utc).isoformat()

    event.ipo_research = research.model_dump()
    event.last_updated_at = utcnow()
    await session.commit()

    settings = get_settings()
    await publish(
        get_redis(settings.redis_url),
        CHANNELS["new_event"],
        {"event_id": event.id, "headline": event.headline[:200],
         "ipo_research": True, "urgency": event.urgency},
    )
    log.info("ipo.completed", event=event_id, company=research.company_name,
             confidence=research.research_confidence)
    return research.model_dump()
