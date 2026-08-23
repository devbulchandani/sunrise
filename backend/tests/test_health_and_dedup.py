import pytest

from app.services.scraping.health import compute_metrics, detect_anomalies
from app.services.deduplication.dedup import content_fingerprint, normalize_url, titles_match


def entry(title="t", url="u", published="2026-08-21", summary="s"):
    return {"title": title, "url": url, "published_at": published, "summary": summary}


class TestMetrics:
    def test_full_coverage(self):
        m = compute_metrics([entry() for _ in range(4)])
        assert m.articles_found == 4
        assert m.title_coverage == 1.0
        assert m.url_coverage == 1.0
        assert m.timestamp_coverage == 1.0
        assert m.empty_field_ratio == 0.0

    def test_empty_result(self):
        m = compute_metrics([])
        assert m.articles_found == 0
        assert m.title_coverage == 0.0

    def test_duplicate_ratio(self):
        entries = [entry(url="same") for _ in range(5)]
        m = compute_metrics(entries, seen_urls={"same"})
        assert m.duplicate_ratio == 1.0


class TestAnomalies:
    def test_zero_articles_is_failure(self):
        verdict = detect_anomalies(compute_metrics([]), http_status=200, historical_counts=[15, 18, 20])
        assert not verdict.healthy
        assert verdict.error_type == "EMPTY_RESULT"

    def test_low_coverage_is_structure_change(self):
        metrics = compute_metrics(
            [{"title": "t", "url": ""} for _ in range(10)]  # urls all missing
        )
        verdict = detect_anomalies(metrics, 200, historical_counts=[10])
        assert not verdict.healthy
        assert verdict.error_type == "STRUCTURE_CHANGE"

    def test_healthy_run(self):
        metrics = compute_metrics([entry(f"t{i}", f"u{i}") for i in range(20)])
        verdict = detect_anomalies(metrics, 200, historical_counts=[19, 20, 21])
        assert verdict.healthy

    def test_http_error_classified(self):
        verdict = detect_anomalies(compute_metrics([]), 503, historical_counts=[10])
        assert not verdict.healthy
        assert verdict.error_type == "SERVER_ERROR"


class TestDedup:
    def test_fingerprint_stable(self):
        a = content_fingerprint("Fed Cuts Rates!", "The decision was unanimous.")
        b = content_fingerprint("fed cuts rates", "the decision was unanimous.")
        assert a == b

    def test_titles_match_fuzzy(self):
        assert titles_match(
            "Federal Reserve cuts interest rates by 25bps",
            "Fed cuts interest rates 25 basis points",
            threshold=60,
        )

    def test_normalize_url(self):
        assert normalize_url("https://WWW.Example.com/path/?utm_source=x&id=2") == "example.com/path?id=2"
