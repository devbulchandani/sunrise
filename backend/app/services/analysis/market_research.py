"""Live market-context research for event analysis.

After the first-pass LLM analysis, this module gathers CURRENT market state —
index levels, trends, positions, sentiment — via web tools, then a second LLM
pass refines the analysis with that context. This grounds deductions in what
the market is actually doing right now, not just the article's claims.

Flow:
  event -> generate 2-3 targeted search queries (LLM)
        -> run searches (Bright Data SERP) [+ optional page fetch]
        -> REFINE pass: LLM re-issues the analysis with market context
        -> store refined analysis + context block on the event
"""

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.llm.client import LLMError, get_llm
from app.services.analysis.tools import fetch_page, tools_available, web_search

log = get_logger("analysis.context")

QUERY_SYSTEM = """You generate web search queries to establish the CURRENT market
state relevant to a financial news event. Queries should target: current index/asset
levels, recent trend direction, and market positioning/sentiment around the affected
assets. Use recency wording ("today", "this week"). Respond only with JSON:
{"queries": ["...", "...", "..."]} (max 3 queries)"""

REFINE_SYSTEM = """You are a senior financial markets analyst for Sunrise. You already
produced a first-pass analysis of a news event. You are now given FRESH web research
about the current market state (index levels, trends, positioning). Refine your
analysis using this context:

- Adjust urgency/sentiment if the market context confirms or contradicts the article's
  framing (e.g. the article claims panic, but indices are flat -> lower urgency).
- Keep affected assets/sectors accurate; add or remove based on what markets are
  actually moving.
- Write `market_context_note`: 2-3 sentences describing the CURRENT market state you
  verified (levels, trends, positioning) and how it shaped your refined assessment.
  Clearly frame as verified-from-search where applicable.

Respond ONLY with the same JSON schema as the first pass, plus "market_context_note":
{ ...analysis fields..., "market_context_note": "..." }"""


class ContextQueries(BaseModel):
    queries: list[str] = Field(default_factory=list, max_length=3)


async def gather_market_context(headline: str, affected_assets: list[str], category: str) -> dict | None:
    """Run the research step. Returns {'queries', 'results'} or None."""
    if not tools_available():
        log.info("context.no_tools")
        return None
    llm = get_llm()
    if not llm.configured:
        return None

    try:
        q = await llm.structured(
            ContextQueries,
            QUERY_SYSTEM,
            f"EVENT: {headline}\nCATEGORY: {category}\nAFFECTED ASSETS: {affected_assets or 'unknown'}",
            max_tokens=300,
        )
    except LLMError as exc:
        log.warn("context.queries_failed", error=str(exc)[:150])
        return None
    if not q.queries:
        return None

    results: list[dict] = []
    for query in q.queries:
        for r in web_search(query, max_results=4):
            results.append({"query": query, **r})

    # if snippets are thin, fetch the most promising page once
    if results and sum(len(r.get("snippet", "")) for r in results) < 400:
        top = results[0]["url"]
        page = fetch_page(top, max_chars=3000)
        if page:
            results.append({"query": "fetched page", "title": top, "url": top, "snippet": page[:1500]})

    log.info("context.gathered", queries=q.queries, results=len(results))
    return {"queries": q.queries, "results": results[:12]}


async def refine_with_context(analysis, context: dict):
    """Second LLM pass: refine a MarketAnalysis with fresh market context."""
    llm = get_llm()
    research_block = "\n".join(
        f"- [{r['query']}] {r['title']}: {r['snippet'][:250]} ({r['url'][:100]})"
        for r in context["results"]
    )
    refined = await llm.structured(
        type(analysis),
        REFINE_SYSTEM,
        f"FIRST-PASS ANALYSIS JSON:\n{analysis.model_dump_json()}\n\n"
        f"FRESH MARKET RESEARCH:\n{research_block[:6000]}",
        max_tokens=3000,
    )
    return refined
