"""Paper account lifecycle, balances, positions, and daily counters."""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.models import (
    PaperAccount,
    PaperLedgerEntry,
    PaperOrder,
    PaperPosition,
    User,
)
from app.services.trading.quotes import get_quote

log = get_logger("trading.accounts")
_CENTS = Decimal("0.01")


def money(value: Decimal | float | int | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(_CENTS, rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP)


async def get_or_create_user(session: AsyncSession, claims: dict) -> User:
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise ValueError("verified identity is missing a subject")
    email = str(claims.get("email") or "").strip().lower()

    user = (
        await session.execute(select(User).where(User.cognito_sub == sub))
    ).scalar_one_or_none()
    if user is not None:
        return user

    if email:
        by_email = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if by_email is not None:
            if not by_email.cognito_sub:
                by_email.cognito_sub = sub
                await session.commit()
                return by_email
            # Another identity already owns this email; isolate the new one.
            email = f"{sub}@cognito.local"

    user = User(
        email=email or f"{sub}@cognito.local",
        cognito_sub=sub,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        user = (
            await session.execute(select(User).where(User.cognito_sub == sub))
        ).scalar_one()
    return user


async def get_or_create_account(session: AsyncSession, user: User) -> PaperAccount:
    account = (
        await session.execute(
            select(PaperAccount).where(PaperAccount.user_id == user.id)
        )
    ).scalar_one_or_none()
    if account is not None:
        return account

    settings = get_settings()
    starting = money(settings.paper_starting_cash)
    account = PaperAccount(
        user_id=user.id,
        currency=settings.paper_currency,
        starting_cash=starting,
        cash=starting,
        realized_pnl=Decimal("0.00"),
    )
    session.add(account)
    await session.flush()
    session.add(
        PaperLedgerEntry(
            account_id=account.id,
            kind="DEPOSIT",
            amount=starting,
            balance_after=starting,
            note="Paper account opening balance",
        )
    )
    await session.commit()
    log.info("trading.account_created", user_id=user.id, cash=str(starting))
    return account


async def load_positions(session: AsyncSession, account: PaperAccount) -> list[PaperPosition]:
    return list(
        (
            await session.execute(
                select(PaperPosition)
                .where(PaperPosition.account_id == account.id)
                .order_by(PaperPosition.symbol)
            )
        ).scalars()
    )


def position_quantities(positions: list[PaperPosition]) -> dict[str, int]:
    return {position.symbol: position.quantity for position in positions}


def gross_exposure(positions: list[PaperPosition]) -> Decimal:
    total = Decimal("0.00")
    for position in positions:
        if position.quantity <= 0:
            continue
        quote = get_quote(position.symbol)
        if quote:
            total += quote.price * Decimal(position.quantity)
    return money(total)


async def position_rows(
    session: AsyncSession, account: PaperAccount
) -> list[dict]:
    positions = await load_positions(session, account)
    rows = []
    for position in positions:
        if position.quantity <= 0:
            continue
        quote = get_quote(position.symbol)
        price = quote.price if quote else position.average_price
        market_value = money(price * Decimal(position.quantity))
        unrealized = money((price - position.average_price) * Decimal(position.quantity))
        rows.append(
            {
                "symbol": position.symbol,
                "name": quote.instrument.name if quote else position.symbol,
                "quantity": position.quantity,
                "average_price": float(money(position.average_price)),
                "last_price": float(money(price)),
                "market_value": float(market_value),
                "unrealized_pnl": float(unrealized),
                "realized_pnl": float(money(position.realized_pnl)),
                "currency": account.currency,
                "quote_source": quote.source if quote else "simulated",
            }
        )
    return rows


async def account_summary(session: AsyncSession, account: PaperAccount) -> dict:
    positions = await load_positions(session, account)
    positions_value = Decimal("0.00")
    unrealized = Decimal("0.00")
    for position in positions:
        if position.quantity <= 0:
            continue
        quote = get_quote(position.symbol)
        if quote is None:
            continue
        positions_value += quote.price * Decimal(position.quantity)
        unrealized += (quote.price - position.average_price) * Decimal(position.quantity)
    positions_value = money(positions_value)
    unrealized = money(unrealized)
    cash = money(account.cash)
    return {
        "currency": account.currency,
        "starting_cash": float(money(account.starting_cash)),
        "cash": float(cash),
        "positions_value": float(positions_value),
        "equity": float(money(cash + positions_value)),
        "realized_pnl": float(money(account.realized_pnl)),
        "unrealized_pnl": float(unrealized),
        "buying_power": float(cash),
        "position_count": sum(1 for position in positions if position.quantity > 0),
        "mode": "paper",
        "quote_source": "simulated",
    }


def _pct(value: Decimal, base: Decimal) -> float:
    if base <= 0:
        return 0.0
    result = (value / base * Decimal("100")).quantize(_CENTS, rounding=ROUND_HALF_UP)
    # Avoid rendering "-0.00%".
    return 0.0 if result == 0 else float(result)


async def portfolio_snapshot(session: AsyncSession, account: PaperAccount) -> dict:
    """Account totals plus every held stock, weighted and marked to the quote.

    This is the single read the paper desk uses for the portfolio: cash, equity,
    each position's cost basis, market value, unrealised P&L, and its weight in
    the book.
    """
    summary = await account_summary(session, account)
    equity = Decimal(str(summary["equity"]))
    starting = Decimal(str(summary["starting_cash"]))
    positions = await load_positions(session, account)

    rows: list[dict] = []
    invested = Decimal("0.00")
    for position in positions:
        if position.quantity <= 0:
            continue
        quote = get_quote(position.symbol)
        price = quote.price if quote else position.average_price
        cost_basis = money(position.average_price * Decimal(position.quantity))
        market_value = money(price * Decimal(position.quantity))
        unrealized = money((price - position.average_price) * Decimal(position.quantity))
        invested += cost_basis
        rows.append(
            {
                "symbol": position.symbol,
                "name": quote.instrument.name if quote else position.symbol,
                "quantity": position.quantity,
                "average_price": float(money(position.average_price)),
                "last_price": float(money(price)),
                "cost_basis": float(cost_basis),
                "market_value": float(market_value),
                "unrealized_pnl": float(unrealized),
                "unrealized_pnl_pct": _pct(unrealized, cost_basis),
                "realized_pnl": float(money(position.realized_pnl)),
                "weight_pct": _pct(market_value, equity),
                "currency": account.currency,
                "quote_source": quote.source if quote else "simulated",
            }
        )

    rows.sort(key=lambda row: row["market_value"], reverse=True)
    cash = Decimal(str(summary["cash"]))
    return {
        "account": summary,
        "positions": rows,
        "invested": float(money(invested)),
        "cash_weight_pct": _pct(cash, equity),
        "total_return_pct": _pct(equity - starting, starting),
        "position_count": len(rows),
        "mode": "paper",
    }


def _utc_day_start() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime.combine(now.date(), time.min, tzinfo=timezone.utc)


async def daily_order_count(session: AsyncSession, account: PaperAccount) -> int:
    start = _utc_day_start()
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(PaperOrder)
                .where(
                    PaperOrder.account_id == account.id,
                    PaperOrder.created_at >= start,
                )
            )
        ).scalar()
        or 0
    )


async def daily_realized_loss(session: AsyncSession, account: PaperAccount) -> Decimal:
    start = _utc_day_start()
    value = (
        await session.execute(
            select(func.coalesce(func.sum(PaperOrder.realized_pnl), 0)).where(
                PaperOrder.account_id == account.id,
                PaperOrder.status == "FILLED",
                PaperOrder.filled_at >= start,
                PaperOrder.realized_pnl < 0,
            )
        )
    ).scalar()
    return money(abs(Decimal(str(value or 0))))
