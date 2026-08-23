"""Polite HTTP fetching: per-source rate limiting, timeouts, robots.txt."""

import asyncio
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("scraper.fetch")

_robots_cache: dict[str, tuple[str, RobotFileParser | None]] = {}
_last_request_at: dict[str, float] = {}
_locks: dict[str, asyncio.Lock] = {}

USER_AGENT = "SunriseBot/1.0 (+https://github.com/sunrise/financial-intelligence; research demo)"


class FetchResult:
    def __init__(self, status_code: int, html: str, elapsed_ms: int):
        self.status_code = status_code
        self.html = html
        self.elapsed_ms = elapsed_ms


def _host_key(url: str) -> str:
    return urlparse(url).netloc


async def _robots_allows(client: httpx.AsyncClient, url: str) -> bool:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    cached = _robots_cache.get(base)
    if cached and cached[0]:
        rp = cached[1]
    elif cached:
        rp = None
    else:
        try:
            resp = await client.get(f"{base}/robots.txt")
            if resp.status_code == 200:
                rp = RobotFileParser()
                rp.parse(resp.text.splitlines())
            else:
                rp = None
        except httpx.HTTPError:
            rp = None
        _robots_cache[base] = (True, rp)
    if rp is None:
        return True
    return rp.can_fetch(USER_AGENT, url) or rp.can_fetch("*", url)


async def fetch(session_http: httpx.AsyncClient, url: str) -> FetchResult:
    """Fetch a URL politely: robots.txt + per-host rate limit."""
    settings = get_settings()
    host = _host_key(url)
    lock = _locks.setdefault(host, asyncio.Lock())
    async with lock:
        last = _last_request_at.get(host)
        wait = settings.min_request_interval_seconds - (time.monotonic() - last) if last else 0
        if wait > 0:
            await asyncio.sleep(wait)

        allowed = await _robots_allows(session_http, url)
        if not allowed:
            raise PermissionError(f"robots.txt disallows {url}")

        start = time.monotonic()
        resp = await session_http.get(
            url,
            timeout=settings.request_timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        _last_request_at[host] = time.monotonic()
        return FetchResult(
            status_code=resp.status_code,
            html=resp.text,
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )


def classify_http_error(status_code: int) -> str | None:
    if status_code == 429:
        return "RATE_LIMIT"
    if status_code >= 500:
        return "SERVER_ERROR"
    if status_code >= 400:
        return "NETWORK_FAILURE"
    return None
