"""TradingView news extractor.

TradingView's news pages are client-rendered, but the article list is embedded
in the HTML as JSON inside <script type="application/prs.init-data+json"> tags.
This extractor walks every init-data script, locates the news items array and
normalizes it into the standard raw-entry shape.
"""

import json
from datetime import datetime

from dateutil import parser as date_parser
from selectolax.parser import HTMLParser

from app.core.logging import get_logger

log = get_logger("scraper.tradingview")


def _find_items(obj, depth: int = 0):
    """Recursively locate the news items list (dicts containing 'title')."""
    if depth > 10:
        return None
    if isinstance(obj, dict):
        items = obj.get("items")
        if (
            isinstance(items, list)
            and items
            and isinstance(items[0], dict)
            and "title" in items[0]
        ):
            return items
        for value in obj.values():
            found = _find_items(value, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj[:10]:
            found = _find_items(value, depth + 1)
            if found:
                return found
    return None


def _parse_published(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # unix seconds vs milliseconds
        ts = value / 1000.0 if value > 10_000_000_000 else float(value)
        try:
            return datetime.utcfromtimestamp(ts).isoformat()
        except (OSError, ValueError, OverflowError):
            return None
    if isinstance(value, str):
        try:
            return date_parser.parse(value).isoformat()
        except (ValueError, OverflowError):
            return None
    return None


def extract_init_data_articles(html: str, base_url: str = "https://www.tradingview.com") -> list[dict]:
    """Parse embedded init-data JSON into raw article entries."""
    tree = HTMLParser(html)
    scripts = tree.css('script[type="application/prs.init-data+json"]')

    entries: list[dict] = []
    seen: set[str] = set()

    for script in scripts:
        raw = script.text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = _find_items(data)
        if not items:
            continue

        for item in items:
            title = str(item.get("title") or "").strip()
            link = str(item.get("link") or "").strip()
            story_path = str(item.get("storyPath") or "").strip()
            if not title:
                continue
            url = link + story_path if link and story_path else (link or story_path)
            if not url:
                continue
            if not url.startswith("http"):
                from urllib.parse import urljoin

                url = urljoin(base_url, url)
            if url in seen:
                continue
            seen.add(url)
            entries.append(
                {
                    "title": title[:2000],
                    "url": url,
                    "summary": str(item.get("description") or "").strip()[:5000] or None,
                    "published_at": _parse_published(item.get("published")),
                    "source_provider": str(item.get("source", {}).get("title", ""))[:100]
                    if isinstance(item.get("source"), dict)
                    else None,
                }
            )

    log.info("tradingview.extracted", articles=len(entries))
    return entries
