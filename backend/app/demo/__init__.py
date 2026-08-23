"""Demo mode utilities.

DEMO_MODE=true enables deliberately breaking a scraper to demonstrate the
self-healing pipeline end to end:

    python -m app.demo.break_scraper fed     # sabotage the active strategy
    python -m app.demo.trigger_healing fed   # run the healing agent now
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import get_session_factory
from app.models.models import ScrapingStrategy, Source


def _assert_demo_mode():
    if not get_settings().demo_mode:
        print("DEMO_MODE is not enabled. Set DEMO_MODE=true in .env")
        sys.exit(1)


async def _get_source(slug_or_id: str):
    factory = get_session_factory()
    async with factory() as session:
        if slug_or_id.isdigit():
            result = await session.execute(select(Source).where(Source.id == int(slug_or_id)))
        else:
            result = await session.execute(select(Source).where(Source.slug == slug_or_id))
        return result.scalar_one_or_none(), session


async def break_scraper(slug: str) -> None:
    """Sabotage the active strategy so the next run extracts 0 articles."""
    source, session = await _get_source(slug)
    if source is None:
        print(f"source '{slug}' not found")
        sys.exit(1)
    strategy_result = await session.execute(
        select(ScrapingStrategy).where(
            ScrapingStrategy.source_id == source.id, ScrapingStrategy.is_active.is_(True)
        )
    )
    strategy = strategy_result.scalar_one_or_none()
    if strategy is None:
        print("no active strategy")
        sys.exit(1)

    broken = {
        **strategy.strategy_json,
        "list_selector": {**strategy.strategy_json.get("list_selector", {}), "selector": ".__sunrise_demo_broken__"},
        "fields": {
            "title": {"method": "css", "selector": ".__sunrise_demo_broken_title__"},
            "url": {"method": "css", "selector": ".__sunrise_demo_broken_link__", "attribute": "href"},
            **{k: v for k, v in strategy.strategy_json.get("fields", {}).items() if k not in ("title", "url")},
        },
    }
    strategy.strategy_json = broken
    source.health_status = "DEGRADED"
    await session.commit()
    print(f"[demo] sabotaged strategy v{strategy.version} for '{source.slug}'")
    print(f"[demo] next run will fail extraction -> healing pipeline will trigger")


async def trigger_healing(slug: str) -> None:
    from app.services.healing.agent import heal_source

    _assert_demo_mode()
    source, _session = await _get_source(slug)
    if source is None:
        print(f"source '{slug}' not found")
        sys.exit(1)
    factory = get_session_factory()
    async with factory() as session:
        event = await heal_source(session, source.id, manual=True)
        print(f"[demo] healing status : {event.status}")
        print(f"[demo] validation     : {event.validation_score}")
        print(f"[demo] old -> new     : v{event.old_strategy_version} -> v{event.new_strategy_version}")
        print(f"[demo] articles recov.: {event.articles_recovered}")
        for step in event.timeline:
            print(f"  {step['at'][:19]}  {step['stage']:<28} {step['detail'][:80]}")


async def restore_scraper(slug: str) -> None:
    """Undo a demo break by re-running healing (or manual fix)."""
    await trigger_healing(slug)
