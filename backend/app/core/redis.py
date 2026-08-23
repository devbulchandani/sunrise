import json
from typing import Any

from redis import asyncio as aioredis

CHANNELS = {
    "new_event": "sunrise:events:new",
    "critical_alert": "sunrise:alerts:critical",
    "scraper_failure": "sunrise:scrapers:failure",
    "scraper_healed": "sunrise:scrapers:healed",
}

_pool: aioredis.Redis | None = None


def get_redis(url: str) -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(url, decode_responses=True)
    return _pool


async def publish(redis: aioredis.Redis, channel: str, payload: dict[str, Any]) -> None:
    await redis.publish(channel, json.dumps(payload, default=str))
