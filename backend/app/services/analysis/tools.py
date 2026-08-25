"""Shared research tools for the agentic analysis pipelines (Bright Data CLI)."""

import json
import shutil
import subprocess

from app.core.logging import get_logger

log = get_logger("analysis.tools")


def _binary() -> str | None:
    return shutil.which("bdata") or shutil.which("brightdata")


def tools_available() -> bool:
    return _binary() is not None


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Bright Data SERP search. Returns [{title, url, snippet}]."""
    binary = _binary()
    if not binary:
        return []
    try:
        result = subprocess.run(
            [binary, "search", query, "--format", "json"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
        items = data if isinstance(data, list) else data.get("results") or data.get("organic") or []
        out = []
        for item in items[:max_results]:
            if isinstance(item, dict) and item.get("url"):
                out.append({
                    "title": str(item.get("title") or "")[:200],
                    "url": str(item.get("url") or "")[:500],
                    "snippet": str(item.get("description") or item.get("snippet") or "")[:400],
                })
        return out
    except Exception as exc:
        log.warn("tools.search_failed", error=str(exc)[:150])
        return []


def fetch_page(url: str, max_chars: int = 6000) -> str:
    """Fetch a page as markdown via Bright Data Web Unlocker."""
    binary = _binary()
    if not binary:
        return ""
    try:
        result = subprocess.run(
            [binary, "scrape", url, "--format", "markdown"],
            capture_output=True, text=True, timeout=90,
        )
        if result.returncode != 0:
            return ""
        return result.stdout[:max_chars]
    except Exception as exc:
        log.warn("tools.fetch_failed", url=url[:80], error=str(exc)[:150])
        return ""
