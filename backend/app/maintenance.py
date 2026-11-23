"""One-shot maintenance: cluster unclustered articles + analyze pending events.

Run with: python -m app.maintenance
"""

import asyncio

from sqlalchemy import select, text

from app.core.logging import get_logger, setup_logging
from app.db.session import get_session_factory
from app.models.models import Article, MarketEvent
from app.services.analysis.clustering import find_or_create_event
from app.services.pipeline import finalize_event

setup_logging()
log = get_logger("maintenance")


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT a.id FROM articles a "
                    "LEFT JOIN event_articles ea ON ea.article_id = a.id "
                    "WHERE ea.id IS NULL ORDER BY a.scraped_at DESC LIMIT 500"
                )
            )
        ).scalars().all()
        event_ids = set()
        for aid in rows:
            art = await session.get(Article, aid)
            if art:
                ev = await find_or_create_event(session, art)
                event_ids.add(ev.id)
        await session.commit()
        print(f"[maintenance] clustered {len(rows)} articles -> {len(event_ids)} events")

    async with factory() as session:
        pending = (
            await session.execute(
                select(MarketEvent.id).where(MarketEvent.analysis_status != "DONE")
            )
        ).scalars().all()
    print(f"[maintenance] analyzing {len(pending)} pending events")
    done = 0
    for eid in pending:
        async with factory() as session:
            try:
                ev = await finalize_event(session, eid)
                if ev and ev.analysis_status == "DONE":
                    done += 1
            except Exception as exc:
                log.warn("maintenance.event_failed", event=eid, error=str(exc)[:150])
    print(f"[maintenance] done; events completed: {done}")


if __name__ == "__main__":
    asyncio.run(main())
