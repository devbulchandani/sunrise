"""Sunrise-owned paper broker.

The broker is deliberately small and deterministic: a proposal is reviewed, the
user confirms it, and the order is filled against a simulated quote or left
open as a limit order. Cash, positions, fills, and audit events are written in
one transaction. No live broker is contacted and no credentials exist here.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.models import (
    AuditEvent,
    MarketEvent,
    PaperAccount,
    PaperLedgerEntry,
    PaperOrder,
    PaperPosition,
    TradeProposal,
    User,
)
from app.services.trading.accounts import (
    account_summary,
    daily_order_count,
    daily_realized_loss,
    get_or_create_account,
    gross_exposure,
    load_positions,
    money,
    position_quantities,
)
from app.services.trading.instruments import get_instrument
from app.services.trading.quotes import Quote, get_quote
from app.services.trading.risk import evaluate_order

log = get_logger("trading.broker")

_CENTS = Decimal("0.01")
_FOUR = Decimal("0.0001")


class TradingError(Exception):
    def __init__(self, message: str, status_code: int = 400, checks: list | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.checks = checks or []


def _aware(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes even for timezone-aware columns."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _payload(checks) -> list[dict]:
    return [check.as_dict() if hasattr(check, "as_dict") else check for check in checks]


async def audit(
    session: AsyncSession,
    claims: dict,
    action: str,
    entity_type: str,
    entity_id: str | int | None,
    payload: dict | None = None,
) -> None:
    session.add(
        AuditEvent(
            actor_sub=str(claims.get("sub") or "unknown"),
            actor_email=str(claims.get("email") or "") or None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            payload=payload or {},
        )
    )


def _quote_dict(proposal: TradeProposal) -> dict:
    instrument = get_instrument(proposal.symbol)
    return {
        "symbol": proposal.symbol,
        "name": instrument.name if instrument else proposal.symbol,
        "price": float(proposal.quote_price or 0),
        "currency": "INR",
        "source": proposal.quote_source or "simulated",
        "as_of": proposal.created_at.isoformat() if proposal.created_at else None,
    }


def proposal_view(proposal: TradeProposal) -> dict:
    checks = proposal.risk_snapshot or []
    price = proposal.limit_price if proposal.order_type == "LIMIT" and proposal.limit_price else proposal.quote_price
    estimated = money((price or Decimal("0")) * Decimal(proposal.quantity))
    return {
        "id": proposal.id,
        "event_id": proposal.event_id,
        "symbol": proposal.symbol,
        "name": (get_instrument(proposal.symbol).name if get_instrument(proposal.symbol) else proposal.symbol),
        "side": proposal.side,
        "order_type": proposal.order_type,
        "quantity": proposal.quantity,
        "limit_price": float(proposal.limit_price) if proposal.limit_price is not None else None,
        "quote": _quote_dict(proposal),
        "estimated_notional": float(estimated),
        "estimated_fee": float(get_settings().paper_fee_per_order),
        "checks": checks,
        "approved": all(bool(check.get("ok")) for check in checks),
        "status": proposal.status,
        "expires_at": proposal.expires_at.isoformat(),
        "expired": bool(_aware(proposal.expires_at) and _aware(proposal.expires_at) <= datetime.now(timezone.utc)),
        "rationale": proposal.rationale,
        "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
    }


def order_view(order: PaperOrder) -> dict:
    return {
        "id": order.id,
        "client_order_id": order.client_order_id,
        "symbol": order.symbol,
        "side": order.side,
        "order_type": order.order_type,
        "quantity": order.quantity,
        "limit_price": float(order.limit_price) if order.limit_price is not None else None,
        "status": order.status,
        "filled_quantity": order.filled_quantity,
        "average_fill_price": float(order.average_fill_price) if order.average_fill_price is not None else None,
        "quote_price": float(order.quote_price) if order.quote_price is not None else None,
        "quote_source": order.quote_source,
        "notional": float(order.notional) if order.notional is not None else None,
        "fee": float(order.fee),
        "realized_pnl": float(order.realized_pnl),
        "rejection_reason": order.rejection_reason,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "filled_at": order.filled_at.isoformat() if order.filled_at else None,
        "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
    }


async def _risk_for(
    session: AsyncSession,
    account: PaperAccount,
    *,
    side: str,
    order_type: str,
    quantity: int,
    limit_price: Decimal | None,
    quote: Quote,
):
    positions = await load_positions(session, account)
    quantities = position_quantities(positions)
    settings = get_settings()
    return evaluate_order(
        side=side,
        order_type=order_type,
        quantity=quantity,
        limit_price=limit_price,
        quote=quote,
        cash=account.cash,
        position_quantity=quantities.get(quote.symbol, 0),
        gross_exposure=gross_exposure(positions),
        daily_orders=await daily_order_count(session, account),
        daily_realized_loss=await daily_realized_loss(session, account),
        settings=settings,
    )


async def create_proposal(
    session: AsyncSession,
    user: User,
    claims: dict,
    *,
    symbol: str,
    side: str,
    order_type: str,
    quantity: int,
    limit_price=None,
    event_id: int | None = None,
    rationale: str | None = None,
) -> TradeProposal:
    symbol = (symbol or "").strip().upper()
    side = (side or "").strip().upper()
    order_type = (order_type or "").strip().upper()
    limit = _decimal(limit_price)
    quantity = int(quantity)

    if get_instrument(symbol) is None:
        raise TradingError(f"{symbol or 'That symbol'} is not in the paper universe.", 400)
    if side not in {"BUY", "SELL"}:
        raise TradingError("Side must be BUY or SELL.", 400)
    if order_type not in {"MARKET", "LIMIT"}:
        raise TradingError("Order type must be MARKET or LIMIT.", 400)
    if quantity < 1 or quantity > 1_000_000:
        raise TradingError("Quantity must be between 1 and 1,000,000.", 400)
    if order_type == "LIMIT" and (limit is None or limit <= 0):
        raise TradingError("A limit order needs a positive limit price.", 400)

    if event_id is not None:
        linked = (
            await session.execute(
                select(MarketEvent.id).where(MarketEvent.id == event_id)
            )
        ).scalar_one_or_none()
        if linked is None:
            event_id = None

    account = await get_or_create_account(session, user)
    quote = get_quote(symbol)
    if quote is None:
        raise TradingError("No simulated quote is available for that symbol.", 400)

    risk = await _risk_for(
        session,
        account,
        side=side,
        order_type=order_type,
        quantity=quantity,
        limit_price=limit,
        quote=quote,
    )
    settings = get_settings()
    proposal = TradeProposal(
        user_id=user.id,
        event_id=event_id,
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        limit_price=limit,
        rationale=(rationale or "").strip()[:1000] or None,
        status="DRAFT",
        quote_price=quote.price,
        quote_source=quote.source,
        risk_snapshot=_payload(risk.checks),
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=settings.paper_proposal_ttl_seconds),
    )
    session.add(proposal)
    await session.flush()
    await audit(
        session,
        claims,
        "proposal.created",
        "trade_proposal",
        proposal.id,
        {
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "limit_price": str(limit) if limit is not None else None,
            "approved": risk.approved,
        },
    )
    await session.commit()
    return proposal


async def confirm_proposal(
    session: AsyncSession,
    user: User,
    claims: dict,
    proposal_id: int,
) -> tuple[PaperOrder, PaperAccount, bool]:
    """Confirm a proposal and execute it. Returns (order, account, idempotent)."""
    proposal = (
        await session.execute(
            select(TradeProposal)
            .where(TradeProposal.id == proposal_id, TradeProposal.user_id == user.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if proposal is None:
        raise TradingError("Proposal not found.", 404)
    if proposal.status not in {"DRAFT"}:
        existing = (
            await session.execute(
                select(PaperOrder).where(PaperOrder.proposal_id == proposal.id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            account = await get_or_create_account(session, user)
            return existing, account, True
        raise TradingError(f"Proposal is already {proposal.status.lower()}.", 409)
    if _aware(proposal.expires_at) is not None and _aware(proposal.expires_at) <= datetime.now(timezone.utc):
        proposal.status = "EXPIRED"
        await session.commit()
        raise TradingError("Proposal expired. Review the order again.", 409)

    existing = (
        await session.execute(
            select(PaperOrder).where(PaperOrder.proposal_id == proposal.id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        account = await get_or_create_account(session, user)
        return existing, account, True

    account = (
        await session.execute(
            select(PaperAccount)
            .where(PaperAccount.user_id == user.id)
            .with_for_update()
        )
    ).scalar_one()
    quote = get_quote(proposal.symbol)
    if quote is None:
        raise TradingError("No simulated quote is available for that symbol.", 400)

    risk = await _risk_for(
        session,
        account,
        side=proposal.side,
        order_type=proposal.order_type,
        quantity=proposal.quantity,
        limit_price=proposal.limit_price,
        quote=quote,
    )
    proposal.risk_snapshot = _payload(risk.checks)
    if not risk.approved:
        proposal.status = "REJECTED"
        await audit(
            session,
            claims,
            "proposal.rejected",
            "trade_proposal",
            proposal.id,
            {"checks": proposal.risk_snapshot},
        )
        await session.commit()
        raise TradingError("Risk checks failed; the order was not submitted.", 409, risk.checks)

    now = datetime.now(timezone.utc)
    order = PaperOrder(
        account_id=account.id,
        proposal_id=proposal.id,
        client_order_id=f"proposal-{proposal.id}",
        symbol=proposal.symbol,
        side=proposal.side,
        order_type=proposal.order_type,
        quantity=proposal.quantity,
        limit_price=proposal.limit_price,
        status="SUBMITTED",
        quote_price=quote.price,
        quote_source=quote.source,
        risk_snapshot=proposal.risk_snapshot,
        submitted_at=now,
    )
    session.add(order)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = (
            await session.execute(
                select(PaperOrder).where(PaperOrder.proposal_id == proposal_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        account = await get_or_create_account(session, user)
        return existing, account, True

    await _apply_order(session, account, order, quote)
    proposal.confirmed_at = now
    if order.status == "REJECTED":
        proposal.status = "REJECTED"
        await audit(
            session,
            claims,
            "order.rejected",
            "paper_order",
            order.id,
            {
                "symbol": order.symbol,
                "reason": order.rejection_reason,
            },
        )
        await session.commit()
        raise TradingError(
            order.rejection_reason or "Order was rejected at fill time.", 409
        )
    proposal.status = "EXECUTED" if order.status == "FILLED" else "CONFIRMED"
    await audit(
        session,
        claims,
        "order.filled" if order.status == "FILLED" else "order.opened",
        "paper_order",
        order.id,
        {
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "status": order.status,
            "fill_price": float(order.average_fill_price) if order.average_fill_price else None,
            "notional": float(order.notional) if order.notional else None,
        },
    )
    await session.commit()
    log.info(
        "trading.order",
        order_id=order.id,
        symbol=order.symbol,
        side=order.side,
        status=order.status,
    )
    return order, account, False


async def _apply_order(
    session: AsyncSession, account: PaperAccount, order: PaperOrder, quote: Quote
) -> None:
    """Fill a market order or a crossed limit order; otherwise leave it OPEN."""
    settings = get_settings()
    if order.order_type == "LIMIT" and order.limit_price is not None:
        crosses = (
            quote.price <= order.limit_price
            if order.side == "BUY"
            else quote.price >= order.limit_price
        )
        if not crosses:
            order.status = "OPEN"
            return

    slip = Decimal(str(settings.paper_slippage_bps)) / Decimal("10000")
    if order.side == "BUY":
        fill_price = quote.price * (Decimal("1") + slip)
        if order.limit_price is not None:
            fill_price = min(fill_price, order.limit_price)
    else:
        fill_price = quote.price * (Decimal("1") - slip)
        if order.limit_price is not None:
            fill_price = max(fill_price, order.limit_price)
    fill_price = fill_price.quantize(_FOUR, rounding=ROUND_HALF_UP)

    notional = money(fill_price * Decimal(order.quantity))
    fee = money(settings.paper_fee_per_order)
    realized = Decimal("0.00")

    position = (
        await session.execute(
            select(PaperPosition)
            .where(
                PaperPosition.account_id == account.id,
                PaperPosition.symbol == order.symbol,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if position is None:
        position = PaperPosition(
            account_id=account.id,
            symbol=order.symbol,
            quantity=0,
            average_price=Decimal("0"),
        )
        session.add(position)
        await session.flush()

    if order.side == "BUY":
        total = notional + fee
        if account.cash < total:
            order.status = "REJECTED"
            order.rejection_reason = "Insufficient cash at fill time."
            return
        account.cash = money(account.cash - total)
        new_quantity = position.quantity + order.quantity
        position.average_price = (
            (position.average_price * Decimal(position.quantity) + fill_price * Decimal(order.quantity))
            / Decimal(new_quantity)
        ).quantize(_FOUR, rounding=ROUND_HALF_UP)
        position.quantity = new_quantity
        ledger_amount = -total
    else:
        if position.quantity < order.quantity:
            order.status = "REJECTED"
            order.rejection_reason = "Insufficient position at fill time."
            return
        realized = money((fill_price - position.average_price) * Decimal(order.quantity))
        account.realized_pnl = money(account.realized_pnl + realized)
        position.realized_pnl = money(position.realized_pnl + realized)
        position.quantity -= order.quantity
        if position.quantity == 0:
            position.average_price = Decimal("0")
        account.cash = money(account.cash + notional - fee)
        ledger_amount = notional - fee

    order.status = "FILLED"
    order.filled_quantity = order.quantity
    order.average_fill_price = fill_price
    order.notional = notional
    order.fee = fee
    order.realized_pnl = realized
    order.filled_at = datetime.now(timezone.utc)
    session.add(
        PaperLedgerEntry(
            account_id=account.id,
            order_id=order.id,
            kind="TRADE",
            amount=money(ledger_amount),
            balance_after=account.cash,
            note=f"{order.side} {order.quantity} {order.symbol} @ {fill_price}",
        )
    )


async def reject_proposal(
    session: AsyncSession, user: User, claims: dict, proposal_id: int
) -> TradeProposal:
    """Reject a draft proposal. Owner-scoped and single-use."""
    proposal = (
        await session.execute(
            select(TradeProposal)
            .where(TradeProposal.id == proposal_id, TradeProposal.user_id == user.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if proposal is None:
        raise TradingError("Proposal not found.", 404)
    if proposal.status != "DRAFT":
        raise TradingError(f"Proposal is already {proposal.status.lower()}.", 409)
    proposal.status = "REJECTED"
    await audit(
        session,
        claims,
        "proposal.rejected",
        "trade_proposal",
        proposal.id,
        {"manual": True},
    )
    await session.commit()
    return proposal


async def cancel_order(
    session: AsyncSession, user: User, claims: dict, order_id: int
) -> PaperOrder:
    order = (
        await session.execute(
            select(PaperOrder)
            .join(PaperAccount, PaperOrder.account_id == PaperAccount.id)
            .where(PaperOrder.id == order_id, PaperAccount.user_id == user.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if order is None:
        raise TradingError("Order not found.", 404)
    if order.status != "OPEN":
        raise TradingError(f"Only open orders can be cancelled (status: {order.status}).", 409)
    order.status = "CANCELLED"
    order.cancelled_at = datetime.now(timezone.utc)
    await audit(session, claims, "order.cancelled", "paper_order", order.id, {"symbol": order.symbol})
    await session.commit()
    return order


async def list_orders(
    session: AsyncSession, user: User, status: str | None = None, limit: int = 100
) -> list[PaperOrder]:
    query = (
        select(PaperOrder)
        .join(PaperAccount, PaperOrder.account_id == PaperAccount.id)
        .where(PaperAccount.user_id == user.id)
        .order_by(PaperOrder.created_at.desc())
        .limit(min(max(limit, 1), 200))
    )
    if status:
        query = query.where(PaperOrder.status == status.upper())
    return list((await session.execute(query)).scalars())


async def list_audit(session: AsyncSession, claims: dict, limit: int = 50) -> list[AuditEvent]:
    return list(
        (
            await session.execute(
                select(AuditEvent)
                .where(AuditEvent.actor_sub == str(claims.get("sub") or "unknown"))
                .order_by(AuditEvent.created_at.desc())
                .limit(min(max(limit, 1), 200))
            )
        ).scalars()
    )


async def fill_open_orders(session: AsyncSession) -> int:
    """Fill crossed limit orders; called by the scheduler every minute."""
    settings = get_settings()
    if not settings.paper_trading_enabled or settings.paper_trading_frozen:
        return 0
    orders = list(
        (
            await session.execute(select(PaperOrder).where(PaperOrder.status == "OPEN"))
        ).scalars()
    )
    filled = 0
    for order in orders:
        quote = get_quote(order.symbol)
        if quote is None:
            continue
        if order.order_type != "LIMIT" or order.limit_price is None:
            continue
        crosses = (
            quote.price <= order.limit_price
            if order.side == "BUY"
            else quote.price >= order.limit_price
        )
        if not crosses:
            continue
        account = (
            await session.execute(
                select(PaperAccount)
                .where(PaperAccount.id == order.account_id)
                .with_for_update()
            )
        ).scalar_one()
        await _apply_order(session, account, order, quote)
        if order.status == "FILLED":
            filled += 1
            session.add(
                AuditEvent(
                    actor_sub="system",
                    actor_email=None,
                    action="order.filled",
                    entity_type="paper_order",
                    entity_id=str(order.id),
                    payload={"symbol": order.symbol, "source": "scheduler"},
                )
            )
        await session.commit()
    return filled


async def reconcile_account(session: AsyncSession, account: PaperAccount) -> dict:
    orders = list(
        (
            await session.execute(
                select(PaperOrder).where(
                    PaperOrder.account_id == account.id,
                    PaperOrder.status == "FILLED",
                )
            )
        ).scalars()
    )
    expected_qty: dict[str, int] = defaultdict(int)
    expected_cash = account.starting_cash
    for order in orders:
        if order.side == "BUY":
            expected_qty[order.symbol] += order.filled_quantity
            expected_cash -= (order.notional or Decimal("0")) + order.fee
        else:
            expected_qty[order.symbol] -= order.filled_quantity
            expected_cash += (order.notional or Decimal("0")) - order.fee
    positions = await load_positions(session, account)
    actual_qty = {position.symbol: position.quantity for position in positions}
    discrepancies = []
    for symbol in sorted(set(expected_qty) | set(actual_qty)):
        if expected_qty.get(symbol, 0) != actual_qty.get(symbol, 0):
            discrepancies.append(
                {
                    "kind": "position",
                    "symbol": symbol,
                    "expected": expected_qty.get(symbol, 0),
                    "actual": actual_qty.get(symbol, 0),
                }
            )
    if abs(money(expected_cash) - money(account.cash)) > Decimal("0.01"):
        discrepancies.append(
            {
                "kind": "cash",
                "expected": float(money(expected_cash)),
                "actual": float(money(account.cash)),
            }
        )
    return {
        "ok": not discrepancies,
        "account_id": account.id,
        "filled_orders": len(orders),
        "discrepancies": discrepancies,
    }


async def reconcile_all(session: AsyncSession) -> list[dict]:
    accounts = list((await session.execute(select(PaperAccount))).scalars())
    return [await reconcile_account(session, account) for account in accounts]
