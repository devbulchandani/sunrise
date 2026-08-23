"""One-shot maintenance: cluster unclustered articles + analyze pending events.

Run with: python -m app.maintenance
"""

import asyncio

from sqlalchemy import select, text

from app.core.logging import setup_logging
from app.db.session import get_session_factory
from app.models.models import Article, MarketEvent
from app.services.analysis.analyzer import analyze_event
from app.services.analysis.clustering import find_or_create_event
from app.services.notifications.dispatcher import dispatch_event_notifications

setup_logging()


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
    sent_total = 0
    for eid in pending:
        async with factory() as session:
            try:
                ev = await analyze_event(session, eid)
                if ev and ev.analysis_status == "DONE":
                    n = await dispatch_event_notifications(session, eid)
                    sent_total += n
            except Exception as exc:
                print(f"  event {eid} failed: {type(exc).__name__}: {str(exc)[:120]}")
    print(f"[maintenance] done; notifications sent: {sent_total}")


if __name__ == "__main__":
    asyncio.run(main())
