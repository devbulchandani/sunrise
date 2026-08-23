"""Validation pipeline for candidate extraction strategies.

Never trust an LLM-generated strategy blindly:
schema -> safety checks -> execute against real HTML -> quality scoring ->
compare against history -> accept/reject.
"""

import re
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.services.scraping.extractor import extract_articles
from app.llm.schemas import ExtractionStrategy


@dataclass
class ValidationResult:
    accepted: bool
    score: float
    articles_found: int = 0
    title_coverage: float = 0.0
    url_coverage: float = 0.0
    timestamp_coverage: float = 0.0
    duplicate_ratio: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "accepted": self.accepted,
            "score": round(self.score, 1),
            "articles_found": self.articles_found,
            "title_coverage": self.title_coverage,
            "url_coverage": self.url_coverage,
            "timestamp_coverage": self.timestamp_coverage,
            "reasons": self.reasons,
        }


def static_safety_checks(strategy: ExtractionStrategy) -> list[str]:
    """Reject strategies with suspicious content before execution.
    Strategies are declarative data, but we still sanity-check inputs."""
    problems = []

    def check_selector(value: str | None, where: str):
        if value is None:
            return
        if len(value) > 500:
            problems.append(f"{where}: selector too long")
        if re.search(r"javascript:|<script|eval\(|import\s+", value, re.I):
            problems.append(f"{where}: forbidden content in selector")

    if strategy.list_selector:
        check_selector(strategy.list_selector.selector, "list_selector")
        if not strategy.list_selector.selector.strip():
            problems.append("list_selector: empty selector")
    for name, f in strategy.fields.items():
        check_selector(f.selector, f"field.{name}")
        check_selector(f.path, f"field.{name}")
    return problems


def _volume_score(articles_found: int, historical_counts: list[int]) -> float:
    recent = [c for c in historical_counts[-10:] if c > 0]
    if recent:
        expected = sorted(recent)[len(recent) // 2]
        ratio = min(articles_found / max(expected, 1), 1.25)
        return min(ratio / 1.25, 1.0)
    # no history: reward any meaningful volume
    return min(articles_found / 8.0, 1.0)


def validate_candidate(
    candidate: ExtractionStrategy,
    html_sample: str,
    base_url: str,
    historical_counts: list[int],
) -> ValidationResult:
    settings = get_settings()

    safety = static_safety_checks(candidate)
    if safety:
        return ValidationResult(False, 0.0, reasons=safety)

    try:
        entries = extract_articles(html_sample, candidate, base_url=base_url)
    except Exception as exc:
        return ValidationResult(False, 0.0, reasons=[f"extraction crashed: {type(exc).__name__}: {exc}"[:200]])

    total = len(entries)
    if total == 0:
        return ValidationResult(False, 0.0, reasons=["extracted 0 articles"])

    titles = sum(1 for e in entries if (e.get("title") or "").strip())
    urls = sum(1 for e in entries if (e.get("url") or "").strip())
    stamps = sum(1 for e in entries if e.get("published_at"))
    summaries = sum(1 for e in entries if (e.get("summary") or "").strip())

    title_cov = titles / total
    url_cov = urls / total
    ts_cov = stamps / total
    sum_cov = summaries / total

    seen = set()
    dupes = 0
    for e in entries:
        u = e.get("url")
        if u in seen:
            dupes += 1
        seen.add(u)
    dup_ratio = dupes / total

    volume = _volume_score(total, historical_counts)

    score = (
        30 * title_cov
        + 30 * url_cov
        + 15 * ts_cov
        + 10 * sum_cov
        + 15 * volume
        - 20 * dup_ratio
        - (15 if total == 1 else 0)
    )
    score = max(0.0, min(100.0, score))

    reasons = []
    accepted = True
    positive_history = [c for c in historical_counts[-10:] if c > 0]
    if positive_history:
        median_count = sorted(positive_history)[len(positive_history) // 2]
        floor = max(3, int(0.3 * median_count))
    else:
        floor = 3
    if title_cov < 0.9:
        accepted = False
        reasons.append(f"title coverage {title_cov:.0%} < 90%")
    if url_cov < 0.9:
        accepted = False
        reasons.append(f"url coverage {url_cov:.0%} < 90%")
    if total < floor:
        accepted = False
        reasons.append(f"only {total} article(s), need >= {floor}")
    if score < settings.min_healing_score:
        accepted = False
        reasons.append(f"score {score:.0f} < {settings.min_healing_score:.0f}")

    if accepted:
        reasons.append("candidate validated")

    return ValidationResult(
        accepted=accepted,
        score=score,
        articles_found=total,
        title_coverage=round(title_cov, 3),
        url_coverage=round(url_cov, 3),
        timestamp_coverage=round(ts_cov, 3),
        duplicate_ratio=round(dup_ratio, 3),
        reasons=reasons,
    )
