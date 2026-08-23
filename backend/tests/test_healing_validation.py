import pytest

from app.llm.schemas import ExtractionStrategy
from app.services.healing.validation import static_safety_checks, validate_candidate

GOOD_HTML = """
<html><body><div class="feed">
  <article><h2><a href="/a1">Alpha headline one about markets</a></h2><p>sum</p><time datetime="2026-08-21T10:00:00Z"></time></article>
  <article><h2><a href="/a2">Beta headline two about banks</a></h2><p>sum</p></article>
  <article><h2><a href="/a3">Gamma headline three about oil</a></h2><p>sum</p></article>
  <article><h2><a href="/a4">Delta headline four about bonds</a></h2><p>sum</p></article>
  <article><h2><a href="/a5">Epsilon headline five about gold</a></h2><p>sum</p></article>
  <article><h2><a href="/a6">Zeta headline six about tech</a></h2><p>sum</p></article>
</div></body></html>
"""

GOOD_STRATEGY = {
    "list_selector": {"method": "css", "selector": "article"},
    "fields": {
        "title": {"method": "css", "selector": "h2 a", "attribute": "text"},
        "url": {"method": "css", "selector": "h2 a", "attribute": "href"},
        "published_at": {"method": "semantic"},
        "summary": {"method": "css", "selector": "p"},
    },
}


def parse(strategy_dict) -> ExtractionStrategy:
    return ExtractionStrategy.model_validate(strategy_dict)


class TestSafety:
    def test_clean_strategy_passes(self):
        assert static_safety_checks(parse(GOOD_STRATEGY)) == []

    def test_forbidden_content_rejected(self):
        bad = parse(
            {
                "list_selector": {"method": "css", "selector": "javascript:alert(1)"},
                "fields": GOOD_STRATEGY["fields"],
            }
        )
        problems = static_safety_checks(bad)
        assert problems

    def test_oversized_selector_rejected(self):
        bad = parse(
            {
                "list_selector": {"method": "css", "selector": "div" * 300},
                "fields": GOOD_STRATEGY["fields"],
            }
        )
        assert static_safety_checks(bad)


class TestValidation:
    def test_good_strategy_accepted(self):
        result = validate_candidate(parse(GOOD_STRATEGY), GOOD_HTML, base_url="https://x.com", historical_counts=[6, 7])
        assert result.accepted, result.reasons
        assert result.articles_found == 6
        assert result.score > 70

    def test_zero_article_strategy_rejected(self):
        empty = parse(
            {
                "list_selector": {"method": "css", "selector": ".nonexistent"},
                "fields": GOOD_STRATEGY["fields"],
            }
        )
        result = validate_candidate(empty, GOOD_HTML, "https://x.com", [10, 12])
        assert not result.accepted
        assert not result.articles_found

    def test_partial_coverage_rejected(self):
        broken = parse(
            {
                "list_selector": {"method": "css", "selector": "article"},
                "fields": {
                    "title": {"method": "css", "selector": "h9 a"},
                    "url": {"method": "css", "selector": "h2 a", "attribute": "href"},
                },
            }
        )
        result = validate_candidate(broken, GOOD_HTML, "https://x.com", [10])
        assert not result.accepted

    def test_low_volume_vs_history_rejected(self):
        # strategy that only finds 1 article when history says 20
        narrow = parse(
            {
                "list_selector": {"method": "css", "selector": "article:first-child"},
                "fields": GOOD_STRATEGY["fields"],
            }
        )
        result = validate_candidate(narrow, GOOD_HTML, "https://x.com", [20, 22, 19])
        assert not result.accepted
