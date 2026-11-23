"""API schemas for the paper-trading desk."""

from typing import Literal

from pydantic import BaseModel, Field


class InstrumentOut(BaseModel):
    symbol: str
    name: str
    exchange: str
    sector: str
    base_price: float


class QuoteOut(BaseModel):
    symbol: str
    name: str
    price: float
    currency: str
    source: str
    as_of: str


class RiskCheckOut(BaseModel):
    name: str
    ok: bool
    detail: str


class ProposalIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    side: Literal["BUY", "SELL"]
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    quantity: int = Field(ge=1, le=1_000_000)
    limit_price: float | None = Field(default=None, gt=0)
    event_id: int | None = None
    rationale: str | None = Field(default=None, max_length=1000)


class ProposalOut(BaseModel):
    id: int
    event_id: int | None
    symbol: str
    name: str
    side: str
    order_type: str
    quantity: int
    limit_price: float | None
    quote: QuoteOut
    estimated_notional: float
    estimated_fee: float
    checks: list[RiskCheckOut]
    approved: bool
    status: str
    expires_at: str
    expired: bool
    rationale: str | None
    created_at: str | None


class OrderOut(BaseModel):
    id: int
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: int
    limit_price: float | None
    status: str
    filled_quantity: int
    average_fill_price: float | None
    quote_price: float | None
    quote_source: str
    notional: float | None
    fee: float
    realized_pnl: float
    rejection_reason: str | None
    created_at: str | None
    filled_at: str | None
    cancelled_at: str | None


class PositionOut(BaseModel):
    symbol: str
    name: str
    quantity: int
    average_price: float
    last_price: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    currency: str
    quote_source: str


class AccountOut(BaseModel):
    currency: str
    starting_cash: float
    cash: float
    positions_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    buying_power: float
    position_count: int
    mode: str
    quote_source: str


class ConfirmOut(BaseModel):
    order: OrderOut
    account: AccountOut
    idempotent: bool


class AuditOut(BaseModel):
    id: int
    action: str
    entity_type: str
    entity_id: str | None
    payload: dict
    created_at: str | None


class TradingConfigOut(BaseModel):
    paper_enabled: bool
    frozen: bool
    live_enabled: bool
    currency: str
    starting_cash: float
    order_notional_limit: float
    position_notional_limit: float
    gross_exposure_limit: float
    daily_order_limit: int
    daily_loss_limit: float
    order_fee: float
    proposal_ttl_seconds: int
    market_hours_enforced: bool
    instruments: list[InstrumentOut]
    disclaimer: str
