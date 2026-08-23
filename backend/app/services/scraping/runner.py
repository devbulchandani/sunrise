"""Scraper runner: orchestrates one run of a source.

fetch -> extract -> normalize -> dedupe -> persist -> health check
                                              ↘ failure classification -> healing
"""

import hashlib
from datetime import datetime, timezone

import httpx
from dateutil import parser as date_parser
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import publish, get_redis, CHANNELS
from app.models.models import (
    Article,
    HealthStatus,
    RawSnapshot,
    RunStatus,
    ScrapingRun,
    ScrapingStrategy,
    Source,
    utcnow,
)
from app.services.scraping.extractor import extract_articles, extract_rss_entries
from app.services.deduplication.dedup import content_fingerprint, normalize_url
from app.services.scraping.fetcher import classify_http_error, fetch
from app.services.scraping.health import compute_metrics, detect_anomalies

log = get_logger("scraper.run")


class ScrapeOutcome:
    def __init__(self):
        self.status = RunStatus.FAILED.value
        self.new_articles = 0
        self.articles_found = 0
        self.error_type = None
        self.error_message = None
        self.should_heal = False


async def _save_snapshot(session: AsyncSession, source: Source, url: str, html: str) -> None:
    settings = get_settings()
    content_hash = hashlib.sha256(html.encode()).hexdigest()
    session.add(
        RawSnapshot(
            source_id=source.id,
            url=url,
            content_hash=content_hash,
            html=html[:2_000_000],
        )
    )
    # retention: keep only the newest N snapshots per source
    ids = (
        select(RawSnapshot.id)
        .where(RawSnapshot.source_id == source.id)
        .order_by(RawSnapshot.created_at.desc())
        .limit(settings.snapshot_retention_per_source)
    ).subquery()
    await session.execute(
        delete(RawSnapshot).where(
            RawSnapshot.source_id == source.id, RawSnapshot.id.not_in(select(ids.c.id))
        )
    )


async def _get_active_strategy(session: AsyncSession, source: Source) -> ScrapingStrategy | None:
    result = await session.execute(
        select(ScrapingStrategy)
        .where(ScrapingStrategy.source_id == source.id, ScrapingStrategy.is_active.is_(True))
        .order_by(ScrapingStrategy.version.desc())
    )
    return result.scalar_one_or_none()


def _normalize_entry(entry: dict, source: Source) -> dict | None:
    title = (entry.get("title") or "").strip()
    url = (entry.get("url") or "").strip()
    if not title or not url:
        return None
    published_at = entry.get("published_at")
    if isinstance(published_at, str):
        try:
            published_at = date_parser.parse(published_at)
        except (ValueError, OverflowError):
            published_at = None
    return {
        "source_id": source.id,
        "url": url,
        "canonical_url": normalize_url(url),
        "title": title[:2000],
        "summary": (entry.get("summary") or "").strip()[:5000] or None,
        "author": (entry.get("author") or "").strip()[:512] or None,
        "image_url": entry.get("image_url"),
        "published_at": published_at,
    }


async def _persist_articles(session: AsyncSession, source: Source, entries: list[dict]) -> tuple[int, float]:
    """Insert new articles. Returns (new_count, duplicate_ratio)."""
    urls = [e.get("url") for e in entries]
    existing_result = await session.execute(
        select(Article.url, Article.content_hash).where(Article.source_id == source.id, Article.url.in_(urls))
    )
    seen_urls = {row[0] for row in existing_result}

    dupes = 0
    new_rows: list[Article] = []
    for entry in entries:
        normalized = _normalize_entry(entry, source)
        if normalized is None:
            continue
        if normalized["url"] in seen_urls:
            dupes += 1
            continue
        fingerprint = content_fingerprint(normalized["title"], normalized["summary"])
        normalized["content_hash"] = fingerprint
        article = Article(**normalized)
        session.add(article)
        new_rows.append(article)

    await session.flush()
    for a in new_rows:
        log.info("article.saved", source=source.slug, title=a.title[:80])
    total = len(entries) or 1
    return len(new_rows), round(dupes / total, 3)


async def run_source(session: AsyncSession, source: Source, http_client: httpx.AsyncClient | None = None) -> ScrapeOutcome:
    """Execute one scrape of a source with full health accounting."""
    outcome = ScrapeOutcome()
    run = ScrapingRun(source_id=source.id, started_at=utcnow())
    strategy = await _get_active_strategy(session, source)

    own_client = http_client is None
    client = http_client or httpx.AsyncClient()

    entries: list[dict] = []
    try:
        result = await fetch(client, source.url)
        run.http_status = result.status_code
        run.response_time_ms = result.elapsed_ms

        http_error = classify_http_error(result.status_code)
        if http_error:
            raise FetchHttpError(http_error, f"HTTP {result.status_code} from {source.url}")

        if source.type == "rss":
            import feedparser

            parsed_feed = feedparser.parse(result.html)
            entries = extract_rss_entries(parsed_feed)
        elif source.type == "brightdata":
            from app.services.scraping.brightdata_adapter import run_brightdata_source

            entries = await run_brightdata_source(source)
        else:
            if strategy is None:
                raise RuntimeError("no active extraction strategy")
            from app.llm.schemas import ExtractionStrategy

            parsed_strategy = ExtractionStrategy.model_validate(strategy.strategy_json)
            entries = extract_articles(result.html, parsed_strategy, base_url=source.url)

        await _save_snapshot(session, source, source.url, result.html)

        # historical context for anomaly detection
        counts_result = await session.execute(
            select(ScrapingRun.articles_found)
            .where(
                ScrapingRun.source_id == source.id,
                ScrapingRun.status == RunStatus.SUCCESS.value,
                ScrapingRun.articles_found > 0,
            )
            .order_by(ScrapingRun.started_at.desc())
            .limit(10)
        )
        historical = list(counts_result.scalars())

        metrics = compute_metrics(entries)
        verdict = detect_anomalies(metrics, result.status_code, historical)

        new_count, dup_ratio = await _persist_articles(session, source, entries)

        run.articles_found = metrics.articles_found
        run.titles_found = metrics.titles_found
        run.urls_found = metrics.urls_found
        run.timestamps_found = metrics.timestamps_found
        run.title_coverage = metrics.title_coverage
        run.url_coverage = metrics.url_coverage
        run.timestamp_coverage = metrics.timestamp_coverage
        run.duplicate_ratio = dup_ratio
        run.empty_field_ratio = metrics.empty_field_ratio
        run.new_articles = new_count

        if not verdict.healthy and not (metrics.articles_found > 0 and dup_ratio >= 0.99):
            outcome.error_type = verdict.error_type
            outcome.error_message = verdict.detail
            outcome.status = RunStatus.FAILED.value
            consecutive = (source.consecutive_failures or 0) + 1
            source.consecutive_failures = consecutive
            settings = get_settings()
            outcome.should_heal = (
                verdict.error_type in ("EMPTY_RESULT", "STRUCTURE_CHANGE", "PARSING_FAILURE")
                and consecutive >= settings.heal_after_consecutive_failures
            ) or (verdict.degraded is False and verdict.error_type == "STRUCTURE_CHANGE" and consecutive >= 1 and metrics.articles_found == 0)
            log.warn(
                "scraper.failure",
                source=source.slug,
                error_type=outcome.error_type,
                detail=outcome.error_message,
                consecutive=consecutive,
            )
        else:
            outcome.status = RunStatus.SUCCESS.value
            outcome.articles_found = metrics.articles_found
            outcome.new_articles = new_count
            source.consecutive_failures = 0
            source.last_success_at = datetime.now(timezone.utc)
            if source.health_status not in (HealthStatus.HEALING.value,):
                source.health_status = HealthStatus.HEALTHY.value
            log.info(
                "scraper.success",
                source=source.slug,
                articles=metrics.articles_found,
                new=new_count,
                dup_ratio=dup_ratio,
            )

    except FetchHttpError as exc:
        outcome.error_type = exc.error_type
        outcome.error_message = exc.message
        source.consecutive_failures += 1
        log.warn("scraper.failure", source=source.slug, error_type=exc.error_type, detail=exc.message)
    except PermissionError as exc:
        outcome.error_type = "NETWORK_FAILURE"
        outcome.error_message = str(exc)
        source.consecutive_failures += 1
        log.warn("scraper.failure", source=source.slug, error_type="ROBOTS_DISALLOWED")
    except Exception as exc:  # parsing errors, unexpected bugs
        outcome.error_type = "PARSING_FAILURE"
        outcome.error_message = f"{type(exc).__name__}: {exc}"[:1000]
        source.consecutive_failures += 1
        log.warn("scraper.failure", source=source.slug, error_type=outcome.error_type, detail=str(exc)[:300])
    finally:
        if own_client:
            await client.aclose()

        run.completed_at = utcnow()
        run.status = outcome.status
        run.new_articles = outcome.new_articles
        run.articles_found = run.articles_found or 0
        run.error_type = outcome.error_type
        run.error_message = outcome.error_message
        session.add(run)

        if outcome.status == RunStatus.FAILED.value:
            source.last_failure_at = utcnow()
            if source.health_status != HealthStatus.HEALING.value:
                source.health_status = HealthStatus.DEGRADED.value
            await publish(
                get_redis(get_settings().redis_url),
                CHANNELS["scraper_failure"],
                {"source_id": source.id, "slug": source.slug, "error": outcome.error_message},
            )
        elif source.health_status != HealthStatus.HEALING.value:
            source.health_status = HealthStatus.HEALTHY.value

        await session.commit()

    return outcome


class FetchHttpError(Exception):
    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
