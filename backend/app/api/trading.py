"""Authenticated paper-trading API.

No route here contacts a broker. The paper desk is a Sunrise-owned simulator;
live trading is represented only as an explicit disabled flag.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin, require_paper_trader
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.trading import (
    AccountOut,
    AuditOut,
    ConfirmOut,
    InstrumentOut,
    OrderOut,
    PortfolioOut,
    PositionOut,
    ProposalIn,
    ProposalOut,
    QuoteOut,
    TelegramLinkCodeOut,
    TelegramLinkOut,
    TradingConfigOut,
)
from app.services.trading import broker, telegram_trade
from app.services.trading.accounts import (
    account_summary,
    get_or_create_account,
    get_or_create_user,
    portfolio_snapshot,
    position_rows,
)
from app.services.trading.instruments import list_instruments
from app.services.trading.quotes import get_quote

router = APIRouter(prefix="/api/trading", tags=["paper-trading"])

DISCLAIMER = (
    "Paper trading simulator. Quotes are simulated, no real orders are sent, "
    "and nothing here is investment advice. Live trading is disabled."
)


def _trading_error(exc: broker.TradingError) -> HTTPException:
    checks = []
    for check in exc.checks:
        checks.append(check.as_dict() if hasattr(check, "as_dict") else check)
    return HTTPException(
        status_code=exc.status_code,
        detail={"message": exc.message, "checks": checks},
    )


def _config() -> TradingConfigOut:
    settings = get_settings()
    return TradingConfigOut(
        paper_enabled=settings.paper_trading_enabled,
        frozen=settings.paper_trading_frozen,
        live_enabled=False,
        currency=settings.paper_currency,
        starting_cash=settings.paper_starting_cash,
        order_notional_limit=settings.paper_max_order_notional,
        position_notional_limit=settings.paper_max_position_notional,
        gross_exposure_limit=settings.paper_max_gross_exposure,
        daily_order_limit=settings.paper_max_daily_orders,
        daily_loss_limit=settings.paper_max_daily_loss,
        order_fee=settings.paper_fee_per_order,
        proposal_ttl_seconds=settings.paper_proposal_ttl_seconds,
        market_hours_enforced=settings.paper_enforce_market_hours,
        instruments=[
            InstrumentOut(
                symbol=item.symbol,
                name=item.name,
                exchange=item.exchange,
                sector=item.sector,
                base_price=float(item.base_price),
            )
            for item in list_instruments()
        ],
        disclaimer=DISCLAIMER,
    )


@router.get("/config", response_model=TradingConfigOut)
async def trading_config():
    """Public mode disclosure; no account data is exposed."""
    return _config()


@router.get("/instruments", response_model=list[InstrumentOut])
async def instruments():
    return _config().instruments


@router.get("/quote/{symbol}", response_model=QuoteOut)
async def quote(symbol: str, claims: dict = Depends(require_paper_trader)):
    found = get_quote(symbol)
    if found is None:
        raise HTTPException(status_code=404, detail="unsupported paper symbol")
    instrument = found.instrument
    return QuoteOut(
        symbol=found.symbol,
        name=instrument.name,
        price=float(found.price),
        currency=found.currency,
        source=found.source,
        as_of=found.as_of.isoformat(),
    )


@router.get("/account", response_model=AccountOut)
async def account(
    claims: dict = Depends(require_paper_trader), db: AsyncSession = Depends(get_db)
):
    user = await get_or_create_user(db, claims)
    paper = await get_or_create_account(db, user)
    return await account_summary(db, paper)


@router.get("/positions", response_model=list[PositionOut])
async def positions(
    claims: dict = Depends(require_paper_trader), db: AsyncSession = Depends(get_db)
):
    user = await get_or_create_user(db, claims)
    paper = await get_or_create_account(db, user)
    return await position_rows(db, paper)


@router.get("/portfolio", response_model=PortfolioOut)
async def portfolio(
    claims: dict = Depends(require_paper_trader), db: AsyncSession = Depends(get_db)
):
    """Account totals plus every holding, weighted and marked to quote."""
    user = await get_or_create_user(db, claims)
    paper = await get_or_create_account(db, user)
    return await portfolio_snapshot(db, paper)


@router.get("/telegram", response_model=TelegramLinkOut)
async def telegram_status(
    claims: dict = Depends(require_paper_trader), db: AsyncSession = Depends(get_db)
):
    user = await get_or_create_user(db, claims)
    return telegram_trade.link_view(user)


@router.post("/telegram/link-code", response_model=TelegramLinkCodeOut, status_code=201)
async def telegram_link_code(
    claims: dict = Depends(require_paper_trader), db: AsyncSession = Depends(get_db)
):
    """Create a single-use code the user sends to the bot as /link CODE."""
    user = await get_or_create_user(db, claims)
    try:
        code, expires_at = await telegram_trade.issue_link_code(db, user)
    except broker.TradingError as exc:
        raise _trading_error(exc) from exc
    bot = telegram_trade.bot_username()
    view = telegram_trade.link_view(user)
    return TelegramLinkCodeOut(
        linked=view["linked"],
        chat=view["chat"],
        code=code,
        expires_at=expires_at.isoformat(),
        bot_username=bot,
        bot_url=telegram_trade.bot_deep_link(),
        trading_enabled=telegram_trade.paper_ready(),
        instructions=(
            f"Open Telegram, message @{bot}, and send /link {code}. "
            "The code expires in a few minutes and can be used once."
        ),
    )


@router.delete("/telegram", response_model=TelegramLinkOut)
async def telegram_unlink(
    claims: dict = Depends(require_paper_trader), db: AsyncSession = Depends(get_db)
):
    user = await get_or_create_user(db, claims)
    if user.telegram_chat_id:
        await telegram_trade.unlink_chat(db, user.telegram_chat_id)
    return telegram_trade.link_view(user)


@router.get("/orders", response_model=list[OrderOut])
async def orders(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    claims: dict = Depends(require_paper_trader),
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_user(db, claims)
    rows = await broker.list_orders(db, user, status=status, limit=limit)
    return [broker.order_view(order) for order in rows]


@router.get("/audit", response_model=list[AuditOut])
async def audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    claims: dict = Depends(require_paper_trader),
    db: AsyncSession = Depends(get_db),
):
    events = await broker.list_audit(db, claims, limit=limit)
    return [
        AuditOut(
            id=event.id,
            action=event.action,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            payload=event.payload or {},
            created_at=event.created_at.isoformat() if event.created_at else None,
        )
        for event in events
    ]


@router.post("/proposals", response_model=ProposalOut, status_code=201)
async def create_proposal(
    body: ProposalIn,
    claims: dict = Depends(require_paper_trader),
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_user(db, claims)
    try:
        proposal = await broker.create_proposal(
            db,
            user,
            claims,
            symbol=body.symbol,
            side=body.side,
            order_type=body.order_type,
            quantity=body.quantity,
            limit_price=body.limit_price,
            event_id=body.event_id,
            rationale=body.rationale,
        )
    except broker.TradingError as exc:
        raise _trading_error(exc) from exc
    return broker.proposal_view(proposal)


@router.post("/proposals/{proposal_id}/confirm", response_model=ConfirmOut)
async def confirm_proposal(
    proposal_id: int,
    claims: dict = Depends(require_paper_trader),
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_user(db, claims)
    try:
        order, paper, idempotent = await broker.confirm_proposal(
            db, user, claims, proposal_id
        )
    except broker.TradingError as exc:
        raise _trading_error(exc) from exc
    return ConfirmOut(
        order=broker.order_view(order),
        account=await account_summary(db, paper),
        idempotent=idempotent,
    )


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalOut)
async def reject_proposal(
    proposal_id: int,
    claims: dict = Depends(require_paper_trader),
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_user(db, claims)
    try:
        proposal = await broker.reject_proposal(db, user, claims, proposal_id)
    except broker.TradingError as exc:
        raise _trading_error(exc) from exc
    return broker.proposal_view(proposal)


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(
    order_id: int,
    claims: dict = Depends(require_paper_trader),
    db: AsyncSession = Depends(get_db),
):
    user = await get_or_create_user(db, claims)
    try:
        order = await broker.cancel_order(db, user, claims, order_id)
    except broker.TradingError as exc:
        raise _trading_error(exc) from exc
    return broker.order_view(order)


@router.post("/reconcile")
async def reconcile(
    _: None = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    return {"accounts": await broker.reconcile_all(db)}
