"""API response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    url: str
    type: str
    schedule: str
    category: str
    credibility: float
    active: bool
    health_status: str
    current_strategy_version: int
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None


class AssetOut(BaseModel):
    symbol: str
    impact: str
    confidence: int


class EventListItem(BaseModel):
    id: int
    affected_markets: list[str] = []
    headline: str
    summary: str | None = None
    ai_summary: str | None = None
    category: str
    sentiment: str | None = None
    market_impact: str | None = None
    urgency: int
    confidence: int | None = None
    analysis_status: str
    first_detected_at: datetime
    last_updated_at: datetime
    article_count: int = 0


class EventDetail(EventListItem):
    reason: str | None = None
    affected_assets: list[AssetOut] = []
    sources: list[SourceOut] = []
    articles: list["EventArticleOut"] = []


class EventArticleOut(BaseModel):
    id: int
    title: str
    url: str
    published_at: datetime | None = None
    scraped_at: datetime
    source_name: str | None = None


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    completed_at: datetime | None = None
    status: str
    http_status: int | None = None
    response_time_ms: int | None = None
    articles_found: int
    new_articles: int
    title_coverage: float
    url_coverage: float
    timestamp_coverage: float
    duplicate_ratio: float
    error_type: str | None = None
    error_message: str | None = None


class HealingTimelineStep(BaseModel):
    at: datetime | str
    stage: str
    detail: str = ""


class HealingEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    old_strategy_version: int | None = None
    new_strategy_version: int | None = None
    failure_reason: str
    failure_type: str | None = None
    candidate_count: int
    candidate_scores: list = []
    validation_score: float | None = None
    status: str
    timeline: list = []
    articles_recovered: int | None = None
    error: str | None = None
    created_at: datetime


class ScraperHealth(BaseModel):
    source_id: int
    slug: str
    name: str
    health_status: str
    strategy_version: int
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error_type: str | None = None
    last_articles_found: int | None = None
    success_rate_24h: float | None = None
    healing_attempts_total: int
    active_healing_event_id: int | None = None


class StrategyOut(BaseModel):
    id: int
    version: int
    strategy_json: dict
    validation_score: float | None = None
    is_active: bool
    created_by: str
    created_at: datetime


class StatsOut(BaseModel):
    jobs_processed: int
    jobs_pending: int
    jobs_failed: int
    articles_scraped: int
    events_detected: int
    alerts_sent: int
    scraper_failures: int
    scraper_healings: int
    llm_calls: int


class PreferencesIn(BaseModel):
    email: str | None = Field(default=None, max_length=320)
    telegram_chat_id: str | None = Field(default=None, max_length=64)
    minimum_urgency: int = Field(ge=0, le=100, default=60)
    asset_preferences: list[str] = []
    category_preferences: list[str] = []
    email_enabled: bool = True
    telegram_enabled: bool = True


class PreferencesOut(PreferencesIn):
    user_id: int


EventDetail.model_rebuild()
