"""Redis-backed per-source run lock.

Both the scheduler and the arq worker can scrape the same source. Without a
distributed lock those runs race: duplicate inserts, duplicate analysis, and
duplicate notifications. The lock is best-effort: if Redis is unavailable we
fall back to running (availability over strictness) and log it.
"""

import uuid

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis

log = get_logger("scraper.lock")

UNLOCKED = "unlocked"


def _key(source_id: int) -> str:
    return f"sunrise:lock:source:{source_id}"


async def acquire_source_lock(source_id: int) -> str | None:
    """Return a token when acquired, None when another run holds it."""
    settings = get_settings()
    token = uuid.uuid4().hex
    try:
        redis = get_redis(settings.redis_url)
        acquired = await redis.set(
            _key(source_id), token, nx=True, ex=settings.source_lock_seconds
        )
        return token if acquired else None
    except Exception as exc:  # pragma: no cover - depends on Redis availability
        log.warn("scraper.lock_unavailable", source_id=source_id, error=str(exc)[:150])
        return UNLOCKED


async def release_source_lock(source_id: int, token: str | None) -> None:
    if not token or token == UNLOCKED:
        return
    try:
        redis = get_redis(get_settings().redis_url)
        await redis.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] "
            "then return redis.call('del', KEYS[1]) else return 0 end",
            1,
            _key(source_id),
            token,
        )
    except Exception as exc:  # pragma: no cover
        log.warn("scraper.unlock_failed", source_id=source_id, error=str(exc)[:150])
