"""Urgency scoring: deterministic blend of AI assessment + system signals.

final_urgency =
    0.55 * ai_urgency
  + 0.15 * source_credibility * 100          (best source in the cluster)
  + 0.10 * category_weight * 100             (e.g. MONETARY_POLICY > OTHER)
  + 0.10 * novelty                           (100 for first report, decays with duplicates)
  + 0.10 * breadth                           (how many assets are affected)

Normalized to 0-100 and mapped to levels.
"""

from app.llm.schemas import CATEGORY_WEIGHTS

LEVELS = [
    (0, 20, "LOW"),
    (21, 40, "MODERATE"),
    (41, 60, "RELEVANT"),
    (61, 80, "HIGH"),
    (81, 100, "CRITICAL"),
]

IMPACT_MAP = {"LOW": 25, "MEDIUM": 50, "HIGH": 75, "CRITICAL": 95}


def urgency_level(score: int) -> str:
    for low, high, name in LEVELS:
        if low <= score <= high:
            return name
    return "CRITICAL" if score > 100 else "LOW"


def compute_urgency(
    ai_urgency: int,
    source_credibility: float,
    category: str,
    article_count: int,
    affected_asset_count: int,
    market_impact: str | None = None,
) -> int:
    novelty = max(0.0, 1.0 - 0.15 * max(0, article_count - 1)) * 100
    breadth = min(affected_asset_count / 5.0, 1.0) * 100
    category_weight = CATEGORY_WEIGHTS.get(category, 0.4) * 100

    score = (
        0.55 * ai_urgency
        + 0.15 * source_credibility * 100
        + 0.10 * category_weight
        + 0.10 * novelty
        + 0.10 * breadth
    )
    # market impact from AI nudges but never dominates
    if market_impact and market_impact in IMPACT_MAP:
        score = 0.9 * score + 0.1 * IMPACT_MAP[market_impact]

    return int(round(max(0, min(100, score))))
