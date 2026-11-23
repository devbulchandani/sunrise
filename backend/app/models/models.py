import enum
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Numeric,
    Index,
    Integer,
    String,
    Text,
    text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class HealthStatus(str, enum.Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    HEALING = "HEALING"


class ErrorType(str, enum.Enum):
    NETWORK_FAILURE = "NETWORK_FAILURE"
    RATE_LIMIT = "RATE_LIMIT"
    SERVER_ERROR = "SERVER_ERROR"
    PARSING_FAILURE = "PARSING_FAILURE"
    STRUCTURE_CHANGE = "STRUCTURE_CHANGE"
    EMPTY_RESULT = "EMPTY_RESULT"


class RunStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


# ---------------------------------------------------------------- users


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    cognito_sub: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    minimum_urgency: Mapped[int] = mapped_column(Integer, default=60)
    asset_preferences: Mapped[list] = mapped_column(JSON, default=list)
    category_preferences: Mapped[list] = mapped_column(JSON, default=list)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------- scrapers


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(2048))
    type: Mapped[str] = mapped_column(String(16))  # html | rss
    schedule: Mapped[str] = mapped_column(String(64), default="*/5 * * * *")
    category: Mapped[str] = mapped_column(String(64), default="OTHER")
    credibility: Mapped[float] = mapped_column(Float, default=0.5)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    health_status: Mapped[str] = mapped_column(
        String(16), default=HealthStatus.HEALTHY.value
    )
    current_strategy_version: Mapped[int] = mapped_column(Integer, default=1)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScrapingStrategy(Base):
    __tablename__ = "scraper_strategies"
    __table_args__ = (UniqueConstraint("source_id", "version", name="uq_source_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    strategy_json: Mapped[dict] = mapped_column(JSON)
    validation_score: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(32), default="seed")  # seed | human | healing_agent
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScrapingRun(Base):
    __tablename__ = "scraper_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default=RunStatus.FAILED.value)
    http_status: Mapped[int | None] = mapped_column(Integer)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    articles_found: Mapped[int] = mapped_column(Integer, default=0)
    new_articles: Mapped[int] = mapped_column(Integer, default=0)
    titles_found: Mapped[int] = mapped_column(Integer, default=0)
    urls_found: Mapped[int] = mapped_column(Integer, default=0)
    timestamps_found: Mapped[int] = mapped_column(Integer, default=0)
    title_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    url_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    duplicate_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    empty_field_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    error_type: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(Text)


class RawSnapshot(Base):
    __tablename__ = "raw_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(2048))
    content_hash: Mapped[str] = mapped_column(String(64))
    html: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


Index("ix_raw_snapshots_source_created", RawSnapshot.source_id, RawSnapshot.created_at)


class HealingEvent(Base):
    __tablename__ = "healing_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    old_strategy_version: Mapped[int | None] = mapped_column(Integer)
    new_strategy_version: Mapped[int | None] = mapped_column(Integer)
    failure_reason: Mapped[str] = mapped_column(Text)
    failure_type: Mapped[str | None] = mapped_column(String(32))
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    candidate_scores: Mapped[list] = mapped_column(JSON, default=list)
    validation_score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24), default="PENDING")  # PENDING|RUNNING|SUCCESS|REJECTED|ERROR
    timeline: Mapped[list] = mapped_column(JSON, default=list)  # [{at, stage, detail}]
    articles_recovered: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- content


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        Index("ix_articles_content_hash", "content_hash"),
        UniqueConstraint("source_id", "url", name="uq_articles_source_url"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(2048))
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(512))
    image_url: Mapped[str | None] = mapped_column(String(2048))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    content_hash: Mapped[str] = mapped_column(String(64))

    source: Mapped["Source"] = relationship(viewonly=True)


class MarketEvent(Base):
    __tablename__ = "market_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    headline: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), default="OTHER")
    sentiment: Mapped[str | None] = mapped_column(String(12))  # BULLISH|BEARISH|NEUTRAL
    market_impact: Mapped[str | None] = mapped_column(String(12))  # LOW|MEDIUM|HIGH|CRITICAL
    urgency: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text)
    affected_markets: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["US Equities", "Crypto"]
    ipo_research: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # agentic IPO deep-dive
    market_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # live research context
    analysis_status: Mapped[str] = mapped_column(String(16), default="PENDING")  # PENDING|DONE|FAILED
    analysis_attempts: Mapped[int] = mapped_column(Integer, default=0)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    articles: Mapped[list["Article"]] = relationship(
        secondary="event_articles", lazy="selectin", viewonly=True
    )


class EventArticle(Base):
    __tablename__ = "event_articles"
    __table_args__ = (UniqueConstraint("event_id", "article_id", name="uq_event_article"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("market_events.id", ondelete="CASCADE"))
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))


class EventAsset(Base):
    __tablename__ = "event_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("market_events.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(16))
    impact: Mapped[str] = mapped_column(String(12))  # positive|negative|neutral
    confidence: Mapped[int] = mapped_column(Integer, default=50)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "uq_notifications_once",
            "event_id",
            "channel",
            text("COALESCE(user_id, -1)"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_id: Mapped[int] = mapped_column(ForeignKey("market_events.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(16))  # telegram | email
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")  # QUEUED|SENT|SKIPPED|FAILED
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------- metrics


class MetricCounter(Base):
    """Durable counters for metrics that cannot be derived from row counts."""

    __tablename__ = "metric_counters"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------- paper trading


class PaperAccount(Base):
    __tablename__ = "paper_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    starting_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (
        UniqueConstraint("account_id", "symbol", name="uq_paper_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE")
    )
    symbol: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    average_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0")
    )
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TradeProposal(Base):
    __tablename__ = "trade_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("market_events.id", ondelete="SET NULL")
    )
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(8))  # BUY | SELL
    order_type: Mapped[str] = mapped_column(String(12))  # MARKET | LIMIT
    quantity: Mapped[int] = mapped_column(Integer)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), default="DRAFT"
    )  # DRAFT | CONFIRMED | EXECUTED | REJECTED | EXPIRED
    quote_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    quote_source: Mapped[str] = mapped_column(String(24), default="simulated")
    risk_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaperOrder(Base):
    __tablename__ = "paper_orders"
    __table_args__ = (
        UniqueConstraint("account_id", "client_order_id", name="uq_paper_client_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE")
    )
    proposal_id: Mapped[int | None] = mapped_column(
        ForeignKey("trade_proposals.id", ondelete="SET NULL"), unique=True
    )
    client_order_id: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(8))
    order_type: Mapped[str] = mapped_column(String(12))
    quantity: Mapped[int] = mapped_column(Integer)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    status: Mapped[str] = mapped_column(
        String(20), default="SUBMITTED"
    )  # SUBMITTED | OPEN | FILLED | CANCELLED | REJECTED
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    average_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    quote_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    quote_source: Mapped[str] = mapped_column(String(24), default="simulated")
    notional: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    fee: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    risk_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaperLedgerEntry(Base):
    __tablename__ = "paper_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE")
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("paper_orders.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(16))  # DEPOSIT | TRADE | FEE
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_actor_created", "actor_sub", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_sub: Mapped[str] = mapped_column(String(128))
    actor_email: Mapped[str | None] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
