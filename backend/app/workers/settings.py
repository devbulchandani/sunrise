"""arq worker settings. Run with: `arq app.workers.settings.WorkerSettings`"""

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.workers.tasks import (
    analyze_event_task,
    heal_source_job,
    scrape_source,
    send_startup_ping,
)

# env-driven so it works locally (localhost) and inside compose (redis service)
_redis_settings = RedisSettings.from_dsn(get_settings().redis_url)


async def startup(ctx):
    from redis.asyncio import Redis
    from arq import create_pool

    settings = get_settings()
    ctx["redis"] = Redis.from_url(settings.redis_url, decode_responses=True)
    ctx["enqueue"] = await create_pool(RedisSettings.from_dsn(settings.redis_url))


async def shutdown(ctx):
    if "redis" in ctx:
        await ctx["redis"].aclose()
    if "enqueue" in ctx:
        await ctx["enqueue"].aclose()


class WorkerSettings:
    # arq consumes jobs through this pool
    redis_settings = _redis_settings
    functions = [scrape_source, analyze_event_task, heal_source_job, send_startup_ping]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 600
    max_tries = 4
