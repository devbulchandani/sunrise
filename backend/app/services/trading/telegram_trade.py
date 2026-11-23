"""Telegram bridge for the paper desk.

A Telegram subscriber cannot trade until their chat is explicitly linked to a
Cognito identity. Linking is a two-step handshake:

1. The signed-in user generates a short-lived code on the paper desk.
2. The user sends ``/link <code>`` to the bot from the chat they want to use.

Every trade still follows the paper-desk invariants: an alert button only
creates a *proposal*, the user must tap Confirm, the server re-runs risk with a
fresh simulated quote, and proposals expire quickly. Free text is never parsed
into an order payload — callbacks carry a symbol from the paper universe and
the server validates it again.
"""

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.models import (
    PaperAccount,
    PaperPosition,
    TelegramLinkCode,
    TradeProposal,
    User,
    UserPreference,
)
from app.services.trading import broker
from app.services.trading.accounts import (
    account_summary,
    get_or_create_account,
    portfolio_snapshot,
)
from app.services.trading.instruments import get_instrument
from app.services.trading.quotes import Quote, get_quote

log = get_logger("trading.telegram")

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LINK_REQUIRED = (
    "🔗 This Telegram chat is not linked to a Sunrise account yet.\n\n"
    "1. Open the paper desk → Telegram trading\n"
    "2. Generate a link code\n"
    "3. Send /link CODE here\n\n"
    "Market alerts stay free. Linking only unlocks the simulated paper desk."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _impact_icon(impact: str | None) -> str:
    return {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}.get(
        (impact or "").lower(), "⚪"
    )


def claims_for(user: User) -> dict:
    if not user.cognito_sub:
        raise broker.TradingError(
            "This chat is not linked to a verified Sunrise account.", 403
        )
    return {"sub": user.cognito_sub, "email": user.email or "", "via": "telegram"}


def paper_ready() -> bool:
    """Global kill switches for every Telegram trading action."""
    settings = get_settings()
    return bool(
        settings.paper_trading_enabled
        and not settings.paper_trading_frozen
        and settings.paper_telegram_enabled
    )


def bot_username() -> str:
    return (get_settings().telegram_bot_username or "").lstrip("@")


def bot_deep_link() -> str:
    name = bot_username()
    return f"https://t.me/{name}" if name else ""


async def get_user_by_chat(session: AsyncSession, chat_id: str) -> User | None:
    if not chat_id:
        return None
    return (
        await session.execute(select(User).where(User.telegram_chat_id == str(chat_id)))
    ).scalar_one_or_none()


def link_view(user: User) -> dict:
    chat = user.telegram_chat_id or ""
    return {
        "linked": bool(chat and user.cognito_sub),
        "chat": f"…{chat[-4:]}" if len(chat) > 4 else chat,
        "bot_username": bot_username(),
        "bot_url": bot_deep_link(),
        "trading_enabled": paper_ready(),
    }


# ---------------------------------------------------------------- linking


async def issue_link_code(session: AsyncSession, user: User) -> tuple[str, datetime]:
    """Create a fresh single-use link code, invalidating earlier ones."""
    if not user.cognito_sub:
        raise broker.TradingError("A verified account is required to link Telegram.", 403)
    settings = get_settings()
    now = _now()
    previous = list(
        (
            await session.execute(
                select(TelegramLinkCode).where(
                    TelegramLinkCode.user_id == user.id,
                    TelegramLinkCode.consumed_at.is_(None),
                )
            )
        ).scalars()
    )
    for row in previous:
        row.consumed_at = now

    code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
    expires_at = now + timedelta(seconds=settings.paper_telegram_link_ttl_seconds)
    session.add(TelegramLinkCode(user_id=user.id, code=code, expires_at=expires_at))
    await session.commit()
    log.info("telegram.link_code_issued", user_id=user.id)
    return code, expires_at


async def consume_link_code(
    session: AsyncSession, raw_code: str, chat_id: str
) -> tuple[User | None, str]:
    """Bind ``chat_id`` to the user who generated the code."""
    code = (raw_code or "").strip().upper()
    if not code:
        return None, "Usage: /link CODE — generate a code on the paper desk first."

    row = (
        await session.execute(
            select(TelegramLinkCode)
            .where(TelegramLinkCode.code == code)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or row.consumed_at is not None:
        return None, "That link code is invalid or already used. Generate a new one."
    if _aware(row.expires_at) is not None and _aware(row.expires_at) <= _now():
        return None, "That link code expired. Generate a new one on the paper desk."

    user = (
        await session.execute(select(User).where(User.id == row.user_id))
    ).scalar_one_or_none()
    if user is None or not user.cognito_sub:
        return None, "That account cannot be linked. Sign in to Sunrise and try again."

    # One chat maps to one account: detach any stale subscriber row first and
    # carry its alert filters over instead of silently resetting them.
    others = list(
        (
            await session.execute(
                select(User).where(
                    User.telegram_chat_id == str(chat_id), User.id != user.id
                )
            )
        ).scalars()
    )
    carried = None
    for other in others:
        if carried is None:
            carried = (
                await session.execute(
                    select(UserPreference).where(UserPreference.user_id == other.id)
                )
            ).scalar_one_or_none()
        other.telegram_chat_id = None

    user.telegram_chat_id = str(chat_id)
    row.consumed_at = _now()

    pref = (
        await session.execute(
            select(UserPreference).where(UserPreference.user_id == user.id)
        )
    ).scalar_one_or_none()
    if pref is None:
        session.add(
            UserPreference(
                user_id=user.id,
                minimum_urgency=carried.minimum_urgency if carried else 60,
                asset_preferences=list(carried.asset_preferences or []) if carried else [],
                category_preferences=(
                    list(carried.category_preferences or []) if carried else []
                ),
                email_enabled=False,
                telegram_enabled=True,
            )
        )
    else:
        pref.telegram_enabled = True

    await broker.audit(
        session,
        claims_for(user),
        "telegram.linked",
        "user",
        user.id,
        {"chat_suffix": str(chat_id)[-4:]},
    )
    await session.commit()
    log.info("telegram.linked", user_id=user.id)
    return user, ""


async def unlink_chat(session: AsyncSession, chat_id: str) -> User | None:
    user = await get_user_by_chat(session, chat_id)
    if user is None:
        return None
    suffix = str(chat_id)[-4:]
    user.telegram_chat_id = None
    if user.cognito_sub:
        await broker.audit(
            session,
            claims_for(user),
            "telegram.unlinked",
            "user",
            user.id,
            {"chat_suffix": suffix},
        )
    await session.commit()
    log.info("telegram.unlinked", user_id=user.id)
    return user


# ---------------------------------------------------------------- trading


def quick_ticket_quantity(quote: Quote) -> int:
    """Default size from a small notional budget, capped by the order limit."""
    settings = get_settings()
    if quote.price <= 0:
        return 1
    budget = Decimal(str(settings.paper_telegram_ticket_notional))
    cap = Decimal(str(settings.paper_max_order_notional))
    quantity = int(min(budget, cap) / quote.price)
    return max(1, min(quantity, 1_000_000))


async def held_symbols(session: AsyncSession, user: User) -> set[str]:
    rows = await session.execute(
        select(PaperPosition.symbol)
        .join(PaperAccount, PaperPosition.account_id == PaperAccount.id)
        .where(PaperAccount.user_id == user.id, PaperPosition.quantity > 0)
    )
    return {symbol for (symbol,) in rows.all()}


async def position_quantity(session: AsyncSession, user: User, symbol: str) -> int:
    value = (
        await session.execute(
            select(PaperPosition.quantity)
            .join(PaperAccount, PaperPosition.account_id == PaperAccount.id)
            .where(
                PaperAccount.user_id == user.id,
                PaperPosition.symbol == symbol,
                PaperPosition.quantity > 0,
            )
        )
    ).scalar_one_or_none()
    return int(value or 0)


async def trade_keyboard(
    session: AsyncSession,
    user: User,
    event_id: int | None,
    assets: list[dict],
) -> dict | None:
    """Inline keyboard of paper-trade actions for an impact alert."""
    if not paper_ready() or not user.cognito_sub or not user.telegram_chat_id:
        return None
    if not assets:
        return None
    settings = get_settings()
    held = await held_symbols(session, user)
    keyboard: list[list[dict]] = []
    seen: set[str] = set()

    for asset in assets:
        symbol = str(asset.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen or get_instrument(symbol) is None:
            continue
        seen.add(symbol)
        row = [
            {
                "text": f"{_impact_icon(asset.get('impact'))} Buy {symbol}",
                "callback_data": f"pt:{event_id or 0}:{symbol}:B",
            }
        ]
        if symbol in held:
            row.append(
                {
                    "text": f"🔻 Sell {symbol}",
                    "callback_data": f"pt:{event_id or 0}:{symbol}:S",
                }
            )
        keyboard.append(row)
        if len(keyboard) >= max(1, settings.paper_telegram_max_symbols):
            break

    if not keyboard:
        return None
    if event_id:
        keyboard.append(
            [
                {
                    "text": "📊 Open paper desk",
                    "url": f"{settings.public_dashboard_url.rstrip('/')}/trading?event={event_id}",
                }
            ]
        )
    return {"inline_keyboard": keyboard}


def proposal_prompt(proposal: TradeProposal, quote_price: float, fee: float) -> str:
    price = float(proposal.quote_price or quote_price)
    lines = [
        "🧾 REVIEW PAPER ORDER",
        "",
        f"{proposal.side} {proposal.quantity} {proposal.symbol} — "
        f"{get_instrument(proposal.symbol).name if get_instrument(proposal.symbol) else proposal.symbol}",
        f"{proposal.order_type.title()} order · simulated quote ₹{price:,.2f}",
        f"Estimated notional ₹{float(proposal.quantity) * price:,.2f} · fee ₹{fee:,.2f}",
    ]
    checks = proposal.risk_snapshot or []
    passed = sum(1 for check in checks if check.get("ok"))
    if checks:
        lines.append(f"Risk checks: {passed}/{len(checks)} passing")
        for check in [c for c in checks if not c.get("ok")][:3]:
            lines.append(f"⚠️ {check.get('detail')}")
    if proposal.event_id:
        lines.append(f"Linked signal: event #{proposal.event_id}")
    lines.extend(
        [
            "",
            "Nothing is submitted until you tap Confirm. This proposal expires soon.",
            "Paper simulator · no real order will be placed.",
        ]
    )
    return "\n".join(lines)


def _order_result_text(order, cash: float) -> str:
    status = order.status
    if status == "FILLED":
        head = "✅ PAPER ORDER FILLED"
        detail = (
            f"{order.side} {order.filled_quantity} {order.symbol} @ "
            f"₹{float(order.average_fill_price or 0):,.2f}"
        )
    elif status == "OPEN":
        head = "⏳ LIMIT ORDER RESTING"
        detail = (
            f"{order.side} {order.quantity} {order.symbol} at "
            f"₹{float(order.limit_price or 0):,.2f}"
        )
    else:
        head = f"ℹ️ ORDER {status}"
        detail = f"{order.side} {order.quantity} {order.symbol}"
    lines = [
        head,
        "",
        detail,
        f"Fee ₹{float(order.fee or 0):,.2f}",
        f"Cash left ₹{cash:,.2f}",
        "Simulated paper ledger · no broker order was sent.",
    ]
    if order.rejection_reason:
        lines.insert(1, f"Reason: {order.rejection_reason}")
    return "\n".join(lines)


async def create_quick_proposal(
    session: AsyncSession,
    user: User,
    *,
    symbol: str,
    side: str,
    event_id: int | None,
) -> TradeProposal:
    quote = get_quote(symbol)
    if quote is None:
        raise broker.TradingError(
            f"{symbol or 'That symbol'} is not in the paper universe.", 400
        )
    quantity = quick_ticket_quantity(quote)
    if side == "SELL":
        held = await position_quantity(session, user, symbol)
        if held <= 0:
            raise broker.TradingError(
                f"You do not hold {symbol} in the paper account.", 400
            )
        quantity = min(quantity, held)
    rationale = f"Telegram quick trade{' · event #' + str(event_id) if event_id else ''}"
    return await broker.create_proposal(
        session,
        user,
        claims_for(user),
        symbol=symbol,
        side=side,
        order_type="MARKET",
        quantity=quantity,
        limit_price=None,
        event_id=event_id,
        rationale=rationale,
    )


async def handle_callback(
    session: AsyncSession, chat_id: str, data: str
) -> tuple[str, dict | None]:
    """Handle one inline-keyboard tap from Telegram.

    Returns ``(reply_text, reply_markup)``. No HTTP happens here so the bot
    poller owns transport and tests can exercise the logic directly.
    """
    user = await get_user_by_chat(session, chat_id)
    if user is None or not user.cognito_sub:
        return LINK_REQUIRED, None
    settings = get_settings()
    if not settings.paper_trading_enabled or settings.paper_trading_frozen:
        return (
            "🔒 The paper desk is currently closed. No order was placed.",
            None,
        )
    if not settings.paper_telegram_enabled:
        return (
            "🔒 Telegram trading is turned off. Use the paper desk in the browser.",
            None,
        )

    parts = [part.strip() for part in (data or "").split(":")]

    if parts[0] == "pt" and len(parts) == 4 and parts[1].isdigit():
        _, raw_event, raw_symbol, raw_side = parts
        symbol = raw_symbol.upper()
        if raw_side.upper() not in {"B", "S"}:
            return "Unknown trade action.", None
        side = "BUY" if raw_side.upper() == "B" else "SELL"
        event_id = int(raw_event) or None
        try:
            proposal = await create_quick_proposal(
                session, user, symbol=symbol, side=side, event_id=event_id
            )
        except broker.TradingError as exc:
            return f"⚠️ {exc.message}", None
        quote = get_quote(symbol)
        return (
            proposal_prompt(
                proposal,
                quote_price=float(quote.price) if quote else 0.0,
                fee=settings.paper_fee_per_order,
            ),
            {
                "inline_keyboard": [
                    [
                        {
                            "text": f"✅ Confirm {proposal.side} {proposal.quantity} {proposal.symbol}",
                            "callback_data": f"pc:{proposal.id}",
                        }
                    ],
                    [
                        {
                            "text": "✖️ Cancel",
                            "callback_data": f"px:{proposal.id}",
                        }
                    ],
                ]
            },
        )

    if parts[0] in {"pc", "px"} and len(parts) == 2 and parts[1].isdigit():
        proposal_id = int(parts[1])
        try:
            if parts[0] == "pc":
                order, account, idempotent = await broker.confirm_proposal(
                    session, user, claims_for(user), proposal_id
                )
                summary = await account_summary(session, account)
                text = _order_result_text(order, summary["cash"])
                if idempotent:
                    text += "\n(Already confirmed earlier — no duplicate order.)"
                return text, None
            proposal = await broker.reject_proposal(
                session, user, claims_for(user), proposal_id
            )
            return (
                f"✖️ Paper order cancelled — proposal #{proposal.id} was not submitted.",
                None,
            )
        except broker.TradingError as exc:
            return f"⚠️ {exc.message}", None

    return "Unknown action. Send /help to see the paper desk commands.", None


async def format_portfolio(session: AsyncSession, user: User) -> str:
    account = await get_or_create_account(session, user)
    snapshot = await portfolio_snapshot(session, account)
    summary = snapshot["account"]
    lines = [
        "📊 PAPER PORTFOLIO (simulated)",
        "",
        f"Equity ₹{summary['equity']:,.2f}",
        f"Cash ₹{summary['cash']:,.2f}",
        f"Invested ₹{snapshot['invested']:,.2f}",
        f"Unrealised ₹{summary['unrealized_pnl']:,.2f} · "
        f"Realised ₹{summary['realized_pnl']:,.2f}",
        f"Total return {snapshot['total_return_pct']:+.2f}%",
    ]
    positions = snapshot["positions"]
    if not positions:
        lines.extend(
            [
                "",
                "No holdings yet. Tap a Buy button on an impact alert, or open the paper desk.",
            ]
        )
    else:
        lines.extend(["", "HOLDINGS"])
        for row in positions[:12]:
            lines.append(
                f"• {row['symbol']} · {row['quantity']} @ ₹{row['average_price']:,.2f} "
                f"→ ₹{row['last_price']:,.2f} "
                f"({row['unrealized_pnl_pct']:+.2f}%) · {row['weight_pct']:.1f}% of book"
            )
    lines.extend(
        [
            "",
            f"Open the desk → {get_settings().public_dashboard_url.rstrip('/')}/trading",
            "Paper simulator. Not investment advice.",
        ]
    )
    return "\n".join(lines)
