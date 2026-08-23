"""Health metric computation and anomaly detection for scraper runs."""

from dataclasses import dataclass, field


@dataclass
class RunMetrics:
    articles_found: int = 0
    titles_found: int = 0
    urls_found: int = 0
    timestamps_found: int = 0
    title_coverage: float = 0.0
    url_coverage: float = 0.0
    timestamp_coverage: float = 0.0
    duplicate_ratio: float = 0.0
    empty_field_ratio: float = 0.0


def compute_metrics(entries: list[dict], seen_urls: set[str] | None = None) -> RunMetrics:
    total = len(entries)
    m = RunMetrics(articles_found=total)
    if total == 0:
        return m

    titles = sum(1 for e in entries if (e.get("title") or "").strip())
    urls = sum(1 for e in entries if (e.get("url") or "").strip())
    stamps = sum(1 for e in entries if e.get("published_at"))
    summaries = sum(1 for e in entries if (e.get("summary") or "").strip())

    m.titles_found = titles
    m.urls_found = urls
    m.timestamps_found = stamps
    m.title_coverage = round(titles / total, 3)
    m.url_coverage = round(urls / total, 3)
    m.timestamp_coverage = round(stamps / total, 3)
    m.empty_field_ratio = round(1 - ((titles + urls + stamps + summaries) / (4 * total)), 3)

    if seen_urls:
        dupes = sum(1 for e in entries if e.get("url") in seen_urls)
        m.duplicate_ratio = round(dupes / total, 3)

    return m


@dataclass
class AnomalyVerdict:
    healthy: bool
    error_type: str | None = None
    detail: str = ""
    degraded: bool = False


def detect_anomalies(
    metrics: RunMetrics,
    http_status: int,
    historical_counts: list[int],
    min_articles_floor: int = 1,
) -> AnomalyVerdict:
    """Decide whether a run looks like a structure change vs transient noise."""
    if http_status == 429:
        return AnomalyVerdict(False, "RATE_LIMIT", "HTTP 429 rate limited")
    if http_status >= 500:
        return AnomalyVerdict(False, "SERVER_ERROR", f"HTTP {http_status}")
    if http_status >= 400:
        return AnomalyVerdict(False, "NETWORK_FAILURE", f"HTTP {http_status}")

    if metrics.articles_found == 0:
        expected = historical_counts[-10:]
        avg_hist = int(sum(expected) / len(expected)) if expected else min_articles_floor * 5
        return AnomalyVerdict(
            False,
            "EMPTY_RESULT",
            f"Expected ~{avg_hist} articles based on history, found 0",
        )

    # coverage checks — extraction partially working means layout shifted
    if metrics.title_coverage < 0.9 or metrics.url_coverage < 0.9:
        return AnomalyVerdict(
            False,
            "STRUCTURE_CHANGE",
            f"title_coverage={metrics.title_coverage} url_coverage={metrics.url_coverage}",
        )

    # sudden drop vs history
    recent = [c for c in historical_counts[-10:] if c > 0]
    if recent:
        median_count = sorted(recent)[len(recent) // 2]
        if median_count >= 5 and metrics.articles_found < median_count * 0.5:
            return AnomalyVerdict(
                False,
                "EMPTY_RESULT",
                f"Sudden drop: {metrics.articles_found} vs median {median_count}",
                degraded=True,
            )

    if metrics.duplicate_ratio > 0.9:
        return AnomalyVerdict(True, detail="mostly duplicates", degraded=False)

    return AnomalyVerdict(True)
