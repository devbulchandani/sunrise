from app.services.analysis.urgency import compute_urgency, urgency_level
from app.services.notifications.telegram import format_event_message
from app.services.analysis.clustering import title_similarity


class TestUrgency:
    def test_critical_blend(self):
        score = compute_urgency(
            ai_urgency=95,
            source_credibility=1.0,
            category="MONETARY_POLICY",
            article_count=3,
            affected_asset_count=5,
            market_impact="CRITICAL",
        )
        assert 80 <= score <= 100

    def test_irrelevant_event_low(self):
        score = compute_urgency(
            ai_urgency=10,
            source_credibility=0.5,
            category="OTHER",
            article_count=1,
            affected_asset_count=0,
        )
        assert score <= 30

    def test_bounds(self):
        for ai in (0, 100):
            for cred in (0.0, 1.0):
                s = compute_urgency(ai, cred, "OTHER", 1, 0)
                assert 0 <= s <= 100

    def test_levels(self):
        assert urgency_level(10) == "LOW"
        assert urgency_level(50) == "RELEVANT"
        assert urgency_level(70) == "HIGH"
        assert urgency_level(95) == "CRITICAL"


class TestTelegramFormatting:
    EVENT = {
        "level": "CRITICAL",
        "headline": "Fed signals unexpected policy shift",
        "urgency": 94,
        "confidence": 88,
        "sentiment": "BULLISH",
        "category": "MONETARY_POLICY",
        "reason": "This could materially change rate expectations.",
        "assets": [{"symbol": "SPY", "impact": "positive"}, {"symbol": "BTC", "impact": "positive"}],
        "source_names": ["Federal Reserve"],
        "url": "https://example.gov/x",
    }

    def test_contains_key_sections(self):
        text = format_event_message(self.EVENT)
        assert "CRITICAL" in text
        assert self.EVENT["headline"] in text
        assert "94/100" in text
        assert "interpretation" in text.lower()
        assert "SPY" in text and "BTC" in text
        assert "Federal Reserve" in text

    def test_no_price_predictions_language(self):
        text = format_event_message(self.EVENT).lower()
        for forbidden in ("will rise", "will fall", "guaranteed"):
            assert forbidden not in text


class TestClustering:
    def test_same_story_similar_titles(self):
        a = "Federal Reserve cuts interest rates by 25 basis points"
        b = "Fed cuts interest rates by 25 bps in surprise move"
        assert title_similarity(a, b) >= 55

    def test_different_stories_not_similar(self):
        assert title_similarity(
            "Oil prices surge after pipeline explosion",
            "Apple announces new iPhone with AI chip",
        ) < 55
