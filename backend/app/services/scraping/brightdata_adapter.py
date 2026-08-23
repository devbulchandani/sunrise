"""Optional Bright Data CLI adapter — a SEPARATE fallback scraping service.

Sunrise's core pipeline is 100% owned infrastructure (httpx + own healing).
This module is an opt-in auxiliary source type ("brightdata") for sites that
are impractical to scrape directly. It shells out to the locally installed
`bdata` CLI (npm i -g @brightdata/cli) — no SDK, no core dependency.

Usage:
    bdata login                      # once, OAuth
    # or set BRIGHTDATA_API_KEY in .env

Then register a source with type="brightdata"; the scheduler/worker will use
this adapter instead of direct HTTP.
"""

import json
import os
import shutil
from functools import lru_cache

from app.core.logging import get_logger

log = get_logger("scraper.brightdata")


class BrightDataError(Exception):
    pass


@lru_cache
def cli_available() -> bool:
    return shutil.which("bdata") is not None


def _base_command() -> list[str]:
    key = os.environ.get("BRIGHTDATA_API_KEY", "")
    cmd = ["bdata"]
    if key:
        cmd += ["-k", key]
    return cmd


def scrape_url(url: str, timeout: int = 120) -> dict:
    """Fetch a URL through Bright Data Web Unlocker; returns parsed JSON/text."""
    if not cli_available():
        raise BrightDataError("bdata CLI not installed (npm i -g @brightdata/cli)")
    import subprocess

    result = subprocess.run(
        [*_base_command(), "scrape", url, "--format", "json"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise BrightDataError(f"bdata scrape failed: {result.stderr[:300]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"text": result.stdout}


def extract_markdown(url: str, timeout: int = 120) -> str:
    """Fetch a URL as markdown via Web Unlocker."""
    if not cli_available():
        raise BrightDataError("bdata CLI not installed")
    import subprocess

    result = subprocess.run(
        [*_base_command(), "scrape", url, "--format", "markdown"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise BrightDataError(f"bdata scrape failed: {result.stderr[:300]}")
    return result.stdout


async def run_brightdata_source(source) -> list[dict]:
    """Adapter entry point matching the scraper framework contract:
    returns a list of raw entry dicts {title, url, summary, published_at}."""
    payload = await __import__("asyncio").to_thread(scrape_url, source.url)
    entries = []
    items = payload if isinstance(payload, list) else payload.get("data") or payload.get("results") or []
    for item in items[:100] if isinstance(items, list) else []:
        if isinstance(item, dict):
            title = item.get("title") or item.get("headline") or ""
            url_ = item.get("url") or item.get("link") or ""
            if title and url_:
                entries.append(
                    {
                        "title": str(title)[:2000],
                        "url": str(url_),
                        "summary": str(item.get("description") or item.get("summary") or "")[:5000],
                        "published_at": item.get("datePublished") or item.get("published_at"),
                    }
                )
    log.info("brightdata.scraped", source=source.slug, articles=len(entries))
    return entries
