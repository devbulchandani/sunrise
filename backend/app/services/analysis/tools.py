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


_ROW_RE = None  # compiled lazily


def _parse_search_table(output: str) -> list[dict]:
    """Parse the bdata search table (rank | title | url | description)."""
    import re

    rows: list[dict] = []
    started = False
    for line in output.splitlines():
        if set(line.strip()) <= {"-", "+", " "} and "-" in line and "+" in line:
            started = True
            continue
        if not started:
            continue
        match = re.match(r"^\s*(\d+)\s+\|(.*?)\|(.*?)\|(.*)$", line)
        if match:
            rows.append({
                "rank": int(match.group(1)),
                "title": match.group(2).strip(),
                "url": match.group(3).strip(),
                "snippet": match.group(4).strip(),
            })
        elif rows and line.strip() and not line.strip().startswith("Searching"):
            cont = line.strip().lstrip("|").strip()
            if cont:
                rows[-1]["snippet"] += " " + cont
    return rows


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Bright Data SERP search via bdata CLI. Returns [{title, url, snippet}].

    Note: the CLI's search subcommand emits a human-readable table (the --json
    flag is rejected server-side), so we parse the table. Individual queries
    can fail (redirect/zone rejections) — failures return [] and the caller
    treats search as best-effort.
    """
    binary = _binary()
    if not binary:
        return []
    try:
        result = subprocess.run(
            [binary, "search", query],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log.warn("tools.search_failed", query=query[:60], error=result.stderr[:120] or result.stdout[:120])
            return []
        rows = _parse_search_table(result.stdout)
        return [
            {"title": r["title"][:200], "url": r["url"][:500], "snippet": r["snippet"][:400]}
            for r in rows[:max_results]
            if r["url"]
        ]
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
