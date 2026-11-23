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
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.models import (
    PaperAccount,
    PaperPosition,
    TelegramLinkCode,
    TelegramTradeIntent,
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
from app.services.trading.instruments import get_instrument, list_instruments
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


# ---------------------------------------------------------------- sized tickets


def _force_reply(placeholder: str) -> dict:
    """Telegram reply prompt: the user's next message becomes the order size."""
    return {
        "force_reply": True,
        "input_field_placeholder": placeholder[:64],
        "selective": False,
    }


def quick_ticket_quantity(quote: Quote) -> int:
    """Suggested size from the default ticket budget, capped by order limits."""
    settings = get_settings()
    if quote.price <= 0:
        return 1
    budget = Decimal(str(settings.paper_telegram_ticket_notional))
    cap = Decimal(str(settings.paper_max_order_notional))
    quantity = int(min(budget, cap) / quote.price)
    return max(1, min(quantity, 1_000_000))


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


async def start_intent(
    session: AsyncSession,
    user: User,
    chat_id: str,
    *,
    symbol: str,
    side: str,
    event_id: int | None,
) -> TelegramTradeIntent:
    """Create (or replace) the chat's pending Buy/Sell size prompt."""
    existing = list(
        (
            await session.execute(
                select(TelegramTradeIntent).where(
                    TelegramTradeIntent.chat_id == str(chat_id)
                )
            )
        ).scalars()
    )
    for row in existing:
        await session.delete(row)
    settings = get_settings()
    intent = TelegramTradeIntent(
        chat_id=str(chat_id),
        user_id=user.id,
        symbol=symbol,
        side=side,
        event_id=event_id,
        expires_at=_now()
        + timedelta(seconds=settings.paper_telegram_intent_ttl_seconds),
    )
    session.add(intent)
    await session.commit()
    return intent


async def get_intent(
    session: AsyncSession, chat_id: str
) -> TelegramTradeIntent | None:
    return (
        await session.execute(
            select(TelegramTradeIntent).where(
                TelegramTradeIntent.chat_id == str(chat_id)
            )
        )
    ).scalar_one_or_none()


async def clear_intent(session: AsyncSession, chat_id: str) -> bool:
    intent = await get_intent(session, chat_id)
    if intent is None:
        return False
    await session.delete(intent)
    await session.commit()
    return True


def quantity_prompt(
    intent: TelegramTradeIntent,
    quote: Quote,
    *,
    held: int,
    cash: Decimal,
) -> tuple[str, dict]:
    settings = get_settings()
    default_qty = quick_ticket_quantity(quote)
    if intent.side == "BUY":
        capacity = (
            f"Buying power ₹{float(cash):,.2f} · a "
            f"₹{settings.paper_telegram_ticket_notional:,.0f} ticket is about "
            f"{default_qty} shares."
        )
    else:
        capacity = f"You hold {held:,} shares."
    text = (
        f"💬 {intent.side} {intent.symbol} — enter the size\n\n"
        f"Simulated quote ₹{float(quote.price):,.2f}\n"
        f"{capacity}\n\n"
        "Reply with a share quantity (e.g. 10) or a rupee amount (e.g. ₹25000).\n"
        "Your next message sets the order size. Send /cancel to abort."
    )
    return text, _force_reply(f"{intent.symbol} shares or ₹ amount")


def parse_size(
    text: str,
    *,
    price: Decimal,
    side: str,
    held: int,
    cash: Decimal,
    fee: Decimal,
    max_order_notional: Decimal,
) -> tuple[int | None, str | None]:
    """Parse a typed size: ``10`` = shares, ``₹25000``/``25000 rs`` = notional."""
    raw = (text or "").strip().lower().replace(",", "").replace("_", " ")
    if not raw:
        return None, "Send a share quantity (e.g. 10) or a rupee amount (e.g. ₹25000)."

    is_amount = (
        "₹" in raw
        or raw.startswith("rs")
        or raw.startswith("inr")
        or raw.endswith("rs")
        or "rupee" in raw
    )
    for token in ("₹", "rupees", "rupee", "inr", "rs", "shares", "share", "qty", "quantity", "x"):
        raw = raw.replace(token, " ")
    raw = " ".join(raw.split())
    if not raw:
        return None, "Send a number, e.g. 10 or ₹25000."

    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None, "I couldn't read that size. Send 10 for shares or ₹25000 for an amount."

    if value <= 0:
        return None, "The size must be greater than zero."

    if is_amount:
        if price <= 0:
            return None, "No simulated quote is available right now."
        quantity = int(value / price)
        if quantity < 1:
            return None, f"₹{value:,.0f} is below one share at ₹{float(price):,.2f}."
    else:
        if value != value.to_integral_value():
            return None, "Share quantity must be a whole number."
        quantity = int(value)

    if quantity > 1_000_000:
        return None, "That is larger than the paper desk allows (1,000,000 shares)."

    if side == "SELL":
        if quantity > held:
            if held <= 0:
                return None, "You do not hold this stock in the paper account."
            return None, f"You hold {held:,} shares. Enter {held:,} or fewer."
    else:
        if price > 0:
            affordable = int((cash - fee) / price)
            if quantity > affordable:
                return None, (
                    f"You can afford at most {max(affordable, 0):,} shares at the "
                    f"current quote (including the ₹{float(fee):,.2f} fee)."
                )
            notional = price * Decimal(quantity)
            if notional > max_order_notional:
                cap = int(max_order_notional / price)
                return None, (
                    f"The per-order cap is ₹{float(max_order_notional):,.2f} — "
                    f"about {max(cap, 1):,} shares at this quote."
                )
    return quantity, None


PAPER_MENU_PAGE_SIZE = 4


def _desk_url(event_id: int | None) -> str:
    base = f"{get_settings().public_dashboard_url.rstrip('/')}/trading"
    return f"{base}?event={event_id}" if event_id else base


def instrument_menu(page: int, event_id: int | None) -> tuple[str, dict]:
    """Paginated Buy/Sell menu for the whole paper universe.

    Used under alerts whose impacted names are outside the curated NSE universe,
    so every alert still has a path to a simulated trade.
    """
    items = list_instruments()
    pages = max(1, (len(items) + PAPER_MENU_PAGE_SIZE - 1) // PAPER_MENU_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    chunk = items[page * PAPER_MENU_PAGE_SIZE : (page + 1) * PAPER_MENU_PAGE_SIZE]

    keyboard: list[list[dict]] = []
    for item in chunk:
        keyboard.append(
            [
                {
                    "text": f"🟢 Buy {item.symbol}",
                    "callback_data": f"pt:{event_id or 0}:{item.symbol}:B",
                },
                {
                    "text": f"🔻 Sell {item.symbol}",
                    "callback_data": f"pt:{event_id or 0}:{item.symbol}:S",
                },
            ]
        )

    navigation: list[dict] = []
    if page > 0:
        navigation.append(
            {
                "text": "⬅️ Back",
                "callback_data": f"pm:{page - 1}:{event_id or 0}",
            }
        )
    if page < pages - 1:
        navigation.append(
            {
                "text": "More ➡️",
                "callback_data": f"pm:{page + 1}:{event_id or 0}",
            }
        )
    if navigation:
        keyboard.append(navigation)
    keyboard.append(
        [{"text": "📊 Open paper desk", "url": _desk_url(event_id)}]
    )

    text = (
        "📈 PAPER UNIVERSE — choose a stock\n"
        f"Page {page + 1}/{pages} · {len(items)} simulated NSE names\n\n"
        "Tap Buy or Sell, then reply with a share quantity or ₹ amount. "
        "/cancel aborts."
    )
    return text, {"inline_keyboard": keyboard}


def trade_keyboard(
    user: User,
    event_id: int | None,
    assets: list[dict],
) -> dict | None:
    """Trade controls under every alert.

    Linked chats get Buy/Sell for impacted paper-universe names plus a browse
    entry for the rest of the universe. The impacted assets are often global
    tickers outside the NSE paper universe, so the alert must never end up with
    no trade button at all.
    """
    if not user.telegram_chat_id or not paper_ready():
        return None
    if not user.cognito_sub:
        return {
            "inline_keyboard": [
                [
                    {
                        "text": "🔗 Connect paper trading",
                        "url": f"{get_settings().public_dashboard_url.rstrip('/')}/trading#telegram",
                    }
                ]
            ]
        }

    settings = get_settings()
    keyboard: list[list[dict]] = []
    seen: set[str] = set()

    for asset in assets or []:
        symbol = str(asset.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen or get_instrument(symbol) is None:
            continue
        seen.add(symbol)
        keyboard.append(
            [
                {
                    "text": f"{_impact_icon(asset.get('impact'))} Buy {symbol}",
                    "callback_data": f"pt:{event_id or 0}:{symbol}:B",
                },
                {
                    "text": f"🔻 Sell {symbol}",
                    "callback_data": f"pt:{event_id or 0}:{symbol}:S",
                },
            ]
        )
        if len(keyboard) >= max(1, settings.paper_telegram_max_symbols):
            break

    keyboard.append(
        [
            {
                "text": "📈 Browse paper stocks",
                "callback_data": f"pm:0:{event_id or 0}",
            }
        ]
    )
    keyboard.append([{"text": "📊 Open paper desk", "url": _desk_url(event_id)}])
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


def confirm_markup(proposal: TradeProposal) -> dict:
    return {
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
    }


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


async def handle_text(
    session: AsyncSession, chat_id: str, text: str
) -> tuple[str, dict | None] | None:
    """Consume a typed size for the chat's pending Buy/Sell intent.

    Returns ``None`` when the message is not part of a trade flow so the bot can
    keep ignoring ordinary chatter.
    """
    user = await get_user_by_chat(session, chat_id)
    if user is None or not user.cognito_sub:
        return None
    intent = await get_intent(session, chat_id)
    if intent is None:
        return None
    if _aware(intent.expires_at) <= _now():
        await clear_intent(session, chat_id)
        return "⌛ That trade request expired. Tap Buy or Sell on an alert again.", None

    settings = get_settings()
    if not settings.paper_trading_enabled or settings.paper_trading_frozen:
        await clear_intent(session, chat_id)
        return "🔒 The paper desk is currently closed. No order was placed.", None
    if not settings.paper_telegram_enabled:
        await clear_intent(session, chat_id)
        return (
            "🔒 Telegram trading is turned off. Use the paper desk in the browser.",
            None,
        )

    quote = get_quote(intent.symbol)
    if quote is None:
        await clear_intent(session, chat_id)
        return "⚠️ That symbol is no longer in the paper universe.", None

    account = await get_or_create_account(session, user)
    summary = await account_summary(session, account)
    cash = Decimal(str(summary["cash"]))
    held = await position_quantity(session, user, intent.symbol)

    quantity, error = parse_size(
        text,
        price=quote.price,
        side=intent.side,
        held=held,
        cash=cash,
        fee=Decimal(str(settings.paper_fee_per_order)),
        max_order_notional=Decimal(str(settings.paper_max_order_notional)),
    )
    if error:
        prompt, markup = quantity_prompt(intent, quote, held=held, cash=cash)
        return f"⚠️ {error}\n\n{prompt}", markup

    assert quantity is not None
    rationale = (
        f"Telegram sized ticket · {quantity} {intent.symbol}"
        f"{' · event #' + str(intent.event_id) if intent.event_id else ''}"
    )
    try:
        proposal = await broker.create_proposal(
            session,
            user,
            claims_for(user),
            symbol=intent.symbol,
            side=intent.side,
            order_type="MARKET",
            quantity=quantity,
            limit_price=None,
            event_id=intent.event_id,
            rationale=rationale,
        )
    except broker.TradingError as exc:
        prompt, markup = quantity_prompt(intent, quote, held=held, cash=cash)
        return f"⚠️ {exc.message}\n\n{prompt}", markup

    await clear_intent(session, chat_id)
    return (
        proposal_prompt(proposal, quote_price=float(quote.price), fee=settings.paper_fee_per_order),
        confirm_markup(proposal),
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

    if parts[0] == "pm" and len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        return instrument_menu(int(parts[1]), int(parts[2]) or None)

    if parts[0] == "pt" and len(parts) == 4 and parts[1].isdigit():
        _, raw_event, raw_symbol, raw_side = parts
        symbol = raw_symbol.upper()
        if raw_side.upper() not in {"B", "S"}:
            return "Unknown trade action.", None
        side = "BUY" if raw_side.upper() == "B" else "SELL"
        quote = get_quote(symbol)
        if quote is None:
            return f"⚠️ {symbol or 'That symbol'} is not in the paper universe.", None
        held = await position_quantity(session, user, symbol)
        if side == "SELL" and held <= 0:
            return (
                f"⚠️ You do not hold {symbol} in the paper account. "
                "Sell works only for stocks in your book.",
                None,
            )
        account = await get_or_create_account(session, user)
        summary = await account_summary(session, account)
        intent = await start_intent(
            session,
            user,
            chat_id,
            symbol=symbol,
            side=side,
            event_id=int(raw_event) or None,
        )
        return quantity_prompt(
            intent, quote, held=held, cash=Decimal(str(summary["cash"]))
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
