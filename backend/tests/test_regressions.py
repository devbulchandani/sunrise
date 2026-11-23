"""Regression tests for the issues fixed in the 0.2.0 hardening pass."""

import pytest
from fastapi import HTTPException

from app.api.routes import SSE_EVENT_NAMES
from app.core.auth import require_admin
from app.core.config import get_settings
from app.services.analysis.clustering import similarity_components, title_similarity
from app.services.notifications.telegram import format_event_message


class TestSseEventNames:
    def test_channels_map_to_dashboard_event_names(self):
        assert SSE_EVENT_NAMES["sunrise:events:new"] == "new"
        assert SSE_EVENT_NAMES["sunrise:alerts:critical"] == "alerts"
        assert SSE_EVENT_NAMES["sunrise:scrapers:failure"] == "scraper_failure"
        assert SSE_EVENT_NAMES["sunrise:scrapers:healed"] == "healed"

    def test_healed_and_failure_are_distinct(self):
        # These used to collapse to the same "scrapers" event name.
        assert (
            SSE_EVENT_NAMES["sunrise:scrapers:failure"]
            != SSE_EVENT_NAMES["sunrise:scrapers:healed"]
        )


class TestTelegramMessage:
    EVENT = {
        "level": "HIGH",
        "headline": "Oil prices fall amid equity selloff",
        "urgency": 70,
        "confidence": 60,
        "sentiment": "BEARISH",
        "reason": "This could weigh on energy equities.",
        "markets": ["US Equities", "Energy Markets"],
        "assets": [{"symbol": "OIL", "impact": "negative"}],
        "source_names": ["Reuters"],
        "url": "https://example.com/story",
    }

    def test_markets_block_rendered_once(self):
        text = format_event_message(self.EVENT)
        assert text.count("MARKETS MENTIONED") == 1
        assert "US Equities" in text

    def test_sections_separate_fact_from_ai(self):
        text = format_event_message(self.EVENT)
        assert "WHAT HAPPENED" in text
        assert "WHY IT MAY MATTER (AI interpretation, not a forecast)" in text
        assert "🟢" not in text  # negative asset must not look like a tailwind

    def test_no_prediction_language(self):
        lowered = format_event_message(self.EVENT).lower()
        for forbidden in ("will rise", "will fall", "guaranteed"):
            assert forbidden not in lowered


class TestClusteringQuality:
    def test_paraphrased_same_story_clusters(self):
        a = "Gold Silver Rates Live Updates: Gold rebounds from 14-month low as US inflation data looms"
        b = "Gold recovers from 14-month low; focus turns to US inflation data"
        score, _fuzzy, jaccard = similarity_components(a, b)
        assert score >= get_settings().clustering_similarity_threshold
        assert jaccard >= get_settings().clustering_jaccard_floor

    def test_template_headlines_for_different_companies_do_not_cluster(self):
        a = "IndusInd Bank Share Price Live Updates: Grant Of Stock Options Under ESOS"
        b = "ICICI Bank Share Price Live Updates: ICICI Bank Bonus Updates"
        score, _fuzzy, jaccard = similarity_components(a, b)
        assert score < get_settings().clustering_similarity_threshold
        assert jaccard < get_settings().clustering_jaccard_floor

    def test_unrelated_stories_are_far_apart(self):
        assert title_similarity(
            "Fed holds rates steady, signals two cuts this year",
            "ECB keeps rates unchanged, warns on growth",
        ) < 55


class TestAdminAuthorization:
    async def test_token_path(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "admin_token", "top-secret")
        monkeypatch.setattr(settings, "admin_emails", "")
        await require_admin(x_admin_token="top-secret", credentials=None)
        with pytest.raises(HTTPException) as exc:
            await require_admin(x_admin_token="wrong", credentials=None)
        assert exc.value.status_code == 403

    async def test_missing_credentials_rejected_when_configured(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "admin_token", "top-secret")
        monkeypatch.setattr(settings, "admin_emails", "")
        with pytest.raises(HTTPException) as exc:
            await require_admin(x_admin_token=None, credentials=None)
        assert exc.value.status_code == 403

    async def test_open_in_development(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "admin_token", "")
        monkeypatch.setattr(settings, "admin_emails", "")
        assert await require_admin(x_admin_token=None, credentials=None) is None
