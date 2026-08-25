"""Pydantic schemas for LLM outputs. The LLM never produces executable code —
only structured JSON that must validate against these models."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

EVENT_CATEGORIES = [
    "MONETARY_POLICY", "INFLATION", "EMPLOYMENT", "GDP", "REGULATION",
    "CRYPTO", "EARNINGS", "MERGERS_ACQUISITIONS", "GEOPOLITICS",
    "COMMODITIES", "MARKET_MOVEMENT", "BANKING", "TECHNOLOGY", "AI",
    "ENERGY", "IPO", "OTHER",
]

CATEGORY_WEIGHTS = {
    "MONETARY_POLICY": 1.0,
    "INFLATION": 0.95,
    "EMPLOYMENT": 0.9,
    "GDP": 0.85,
    "REGULATION": 0.8,
    "CRYPTO": 0.7,
    "IPO": 0.8,
    "EARNINGS": 0.75,
    "MERGERS_ACQUISITIONS": 0.8,
    "GEOPOLITICS": 0.85,
    "COMMODITIES": 0.75,
    "MARKET_MOVEMENT": 0.6,
    "BANKING": 0.8,
    "TECHNOLOGY": 0.65,
    "AI": 0.65,
    "ENERGY": 0.75,
    "OTHER": 0.4,
}


class AssetImpact(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    impact: Literal["positive", "negative", "neutral"]
    confidence: int = Field(ge=0, le=100)


class MarketAnalysis(BaseModel):
    summary: str = Field(min_length=10, max_length=2000)
    category: str
    sentiment: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    market_impact: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    urgency: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    affected_assets: list[AssetImpact] = Field(default_factory=list, max_length=12)
    affected_sectors: list[str] = Field(default_factory=list, max_length=10)
    affected_regions: list[str] = Field(default_factory=list, max_length=10)
    affected_markets: list[str] = Field(default_factory=list, max_length=8)
    reason: str = Field(min_length=5, max_length=3000)
    market_context_note: str = Field(default="", max_length=1500)

    @field_validator("category")
    @classmethod
    def valid_category(cls, v: str) -> str:
        v = v.upper().strip()
        return v if v in EVENT_CATEGORIES else "OTHER"


class ExtractionField(BaseModel):
    method: Literal["css", "xpath", "jsonld", "og", "semantic"]
    selector: str = ""
    attribute: str = "text"
    path: str = ""  # jsonld dotted path e.g. "NewsArticle.headline"


class ListSelector(BaseModel):
    method: Literal["css", "xpath"] = "css"
    selector: str


class ExtractionStrategy(BaseModel):
    """Declarative extraction strategy. Safe by construction: it can only
    select elements and read text/attributes from parsed HTML."""

    list_selector: ListSelector | None = None
    fields: dict[str, ExtractionField]

    @field_validator("fields")
    @classmethod
    def required_fields_present(cls, v: dict[str, ExtractionField]) -> dict[str, ExtractionField]:
        if "title" not in v or "url" not in v:
            raise ValueError("strategy must define at least 'title' and 'url' fields")
        return v


class HealingCandidate(BaseModel):
    """What we ask the healing LLM to return."""

    strategy: ExtractionStrategy
    reasoning: str = ""


class AnalysisResult(BaseModel):
    analysis: MarketAnalysis
