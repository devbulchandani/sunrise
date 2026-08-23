"""Bright Data CLI adapter — auxiliary scraping service for bot-protected sites.

Sunrise's core pipeline is owned infrastructure (httpx + own self-healing).
This module is an opt-in source type ("brightdata") used for targets where
direct scraping is impractical (heavy anti-bot). It shells out to the locally
installed `bdata` CLI (npm i -g @brightdata/cli; authenticate with `bdata login`
or set BRIGHTDATA_API_KEY).

Flow: bdata scrape <url> --format json|markdown  ->  normalized entry dicts
that feed the same dedup -> clustering -> AI analysis pipeline as every other
source.
"""

import asyncio
import json
import os
import re
import shutil
from functools import lru_cache

from app.core.logging import get_logger

log = get_logger("scraper.brightdata")


class BrightDataError(Exception):
    pass


@lru_cache
def cli_available() -> bool:
    return shutil.which("bdata") is not None or bool(shutil.which("brightdata"))


def _base_command() -> list[str]:
    binary = shutil.which("bdata") or shutil.which("brightdata") or "bdata"
    key = os.environ.get("BRIGHTDATA_API_KEY", "")
    cmd = [binary]
    if key:
        cmd += ["-k", key]
    return cmd


def _run_cli(args: list[str], timeout: int = 180) -> str:
    import subprocess

    result = subprocess.run(
        [*_base_command(), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise BrightDataError(f"bdata {' '.join(args[:2])} failed: {result.stderr[:300]}")
    return result.stdout


def scrape_markdown(url: str, country: str | None = None) -> str:
    """Fetch page content through Web Unlocker as markdown."""
    args = ["scrape", url, "--format", "markdown"]
    if country:
        args += ["--country", country]
    return _run_cli(args)


def scrape_json(url: str, country: str | None = None) -> dict | list:
    """Fetch page through Web Unlocker requesting JSON metadata."""
    args = ["scrape", url, "--format", "json"]
    if country:
        args += ["--country", country]
    out = _run_cli(args)
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"text": out}


_MD_LINK = re.compile(
    r"^#{0,4}\s*\*{0,2}\s*\[([^\]\n]{25,220})\]\((https?://[^)\s]+)\)", re.MULTILINE
)


_BOILERPLATE = re.compile(
    r"logo|sign in|sign up|subscribe|homepage|calendar|newsletter|trending tickers|"
    r"upgrades? & downgrades?|watchlist|sponsored|advertisement|cookie|privacy|"
    r"terms of (use|service)|about us|contact us|help center",
    re.I,
)


def _is_article(url: str, title: str) -> bool:
    if _BOILERPLATE.search(title):
        return False
    # real articles live under content paths on most news sites
    return bool(re.search(r"/(story|article|news|us|business|markets|investing)/", url)) or "/20" in url


def entries_from_markdown(md: str, base_url: str = "") -> list[dict]:
    """Parse headline-like markdown links into raw article entries."""
    entries = []
    seen: set[str] = set()
    for title, url in _MD_LINK.findall(md or ""):
        title_clean = re.sub(r"\s+", " ", title).strip()
        if not title_clean or url in seen:
            continue
        if not _is_article(url, title_clean):
            continue
        # skip nav/boilerplate-ish short fragments already filtered by length
        seen.add(url)
        entries.append(
            {
                "title": title_clean[:2000],
                "url": url,
                "summary": None,
                "published_at": None,
            }
        )
    return entries


async def run_brightdata_source(source) -> list[dict]:
    """Adapter entry point matching the scraper framework contract."""
    md = await asyncio.to_thread(scrape_markdown, source.url)
    entries = entries_from_markdown(md)
    log.info(
        "brightdata.scraped",
        source=source.slug,
        articles=len(entries),
        bytes=len(md),
    )
    return entries
