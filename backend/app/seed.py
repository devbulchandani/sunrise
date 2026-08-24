"""Seed script: registers sources with initial strategies, creates demo user.

Run with: python -m app.seed
"""

import asyncio

from sqlalchemy import select

from app.core.logging import setup_logging
from app.db.session import get_engine, get_session_factory
from app.models.models import Source, ScrapingStrategy, User, UserPreference

setup_logging()

SEED_SOURCES = [
    {
        "slug": "fed",
        "name": "Federal Reserve",
        "url": "https://www.federalreserve.gov/newsevents/pressreleases.htm",
        "type": "html",
        "schedule": "*/10 * * * *",
        "category": "MONETARY_POLICY",
        "credibility": 1.0,
        "strategy": {
            "list_selector": {"method": "css", "selector": "ul.panel-body__list li"},
            "fields": {
                "title": {"method": "css", "selector": "a", "attribute": "text"},
                "url": {"method": "css", "selector": "a", "attribute": "href"},
                "published_at": {"method": "semantic"},
                "summary": {"method": "css", "selector": "p"},
            },
        },
    },
    {
        "slug": "ecb",
        "name": "European Central Bank",
        "url": "https://www.ecb.europa.eu/rss/press.html",
        "type": "rss",
        "schedule": "*/15 * * * *",
        "category": "MONETARY_POLICY",
        "credibility": 1.0,
        "strategy": {"fields": {}},
    },
    {
        "slug": "boe",
        "name": "Bank of England",
        "url": "https://www.bankofengland.co.uk/rss/news",
        "type": "rss",
        "schedule": "*/30 * * * *",
        "category": "BANKING",
        "credibility": 0.95,
        "strategy": {"fields": {}},
    },
    {
        "slug": "cointelegraph",
        "name": "Cointelegraph",
        "url": "https://cointelegraph.com/rss",
        "type": "rss",
        "schedule": "*/5 * * * *",
        "category": "CRYPTO",
        "credibility": 0.75,
        "strategy": {
            "fields": {
                "title": {"method": "jsonld", "path": "headline"},
                "url": {"method": "jsonld", "path": "url"},
                "published_at": {"method": "jsonld", "path": "datePublished"},
                "summary": {"method": "jsonld", "path": "description"},
            }
        },
    },
    {
        "slug": "coindesk",
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "type": "rss",
        "schedule": "*/10 * * * *",
        "category": "CRYPTO",
        "credibility": 0.8,
        "strategy": {"fields": {}},
    },
    {
        "slug": "yahoo_finance",
        "name": "Yahoo Finance",
        "url": "https://finance.yahoo.com/news/rssindex",
        "type": "rss",
        "schedule": "*/5 * * * *",
        "category": "MARKET_MOVEMENT",
        "credibility": 0.85,
        "strategy": {"fields": {}},
    },
    {
        "slug": "reuters_brightdata",
        "name": "MarketWatch via Bright Data",
        "url": "https://www.marketwatch.com/latest-news",
        "type": "brightdata",
        "schedule": "*/20 * * * *",
        "category": "MARKET_MOVEMENT",
        "credibility": 0.9,
        "strategy": {"fields": {}},
    },
    {
        "slug": "et_markets",
        "name": "Economic Times Markets (India)",
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "type": "rss",
        "schedule": "*/10 * * * *",
        "category": "MARKET_MOVEMENT",
        "credibility": 0.85,
        "strategy": {"fields": {}},
    },
    {
        "slug": "livemint_markets",
        "name": "LiveMint Markets (India)",
        "url": "https://www.livemint.com/rss/markets",
        "type": "rss",
        "schedule": "*/10 * * * *",
        "category": "MARKET_MOVEMENT",
        "credibility": 0.85,
        "strategy": {"fields": {}},
    },
    {
        "slug": "investing_commodities",
        "name": "Investing.com Commodities",
        "url": "https://www.investing.com/rss/news_11.rss",
        "type": "rss",
        "schedule": "*/10 * * * *",
        "category": "COMMODITIES",
        "credibility": 0.8,
        "strategy": {"fields": {}},
    },
]


async def seed() -> None:
    # create tables
    from app.models.models import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as session:
        for spec in SEED_SOURCES:
            existing = (
                await session.execute(select(Source).where(Source.slug == spec["slug"]))
            ).scalar_one_or_none()
            if existing is not None:
                continue
            source = Source(
                slug=spec["slug"],
                name=spec["name"],
                url=spec["url"],
                type=spec["type"],
                schedule=spec["schedule"],
                category=spec["category"],
                credibility=spec["credibility"],
            )
            session.add(source)
            await session.flush()
            session.add(
                ScrapingStrategy(
                    source_id=source.id,
                    version=1,
                    strategy_json=spec["strategy"],
                    is_active=True,
                    created_by="seed",
                )
            )
            print(f"[seed] source registered: {source.slug} ({source.type})")

        demo_user = (
            await session.execute(select(User).where(User.email == "demo@sunrise.local"))
        ).scalar_one_or_none()
        if demo_user is None:
            demo_user = User(email="demo@sunrise.local")
            session.add(demo_user)
            await session.flush()
            session.add(
                UserPreference(
                    user_id=demo_user.id,
                    minimum_urgency=60,
                    asset_preferences=["BTC", "ETH", "SPY", "QQQ", "GOLD", "OIL"],
                    category_preferences=["crypto", "macro", "stocks", "geopolitics", "commodities"],
                )
            )
            print("[seed] demo user created")

        await session.commit()
    print("[seed] done")


if __name__ == "__main__":
    asyncio.run(seed())
