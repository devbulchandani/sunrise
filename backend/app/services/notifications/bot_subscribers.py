"""Telegram subscriber bot: alerts, filters, and the paper-trading bridge.

Long-polls getUpdates (works from NAT'd hosts, no webhook needed) and
registers each new chat as a User + default UserPreference. The notification
dispatcher then fans out to every subscriber with per-user preference
filtering.

Supported commands:
  /start            subscribe (default: urgency >= 60)
  /stop             unsubscribe
  /urgency <0-100>  minimum urgency threshold
  /assets BTC,SPY   only receive events touching these assets
  /categories crypto,macro   filter by category groups
  /status           show current settings
  /link CODE        link this chat to a Sunrise account (paper trading)
  /unlink           disconnect this chat from paper trading
  /portfolio        show simulated paper holdings

Trading uses inline buttons only: an alert button creates a proposal, and a
second tap confirms it. Free text is never parsed into an order.

Run inside the scheduler process so exactly one instance polls.
"""

import asyncio

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.models.models import MetricCounter, User, UserPreference
from app.services.trading import telegram_trade

log = get_logger("notify.bot")

API = "https://api.telegram.org"

HELP_TEXT = (
    "☀️ Welcome to Sunrise — autonomous market intelligence.\n\n"
    "You're subscribed to market events rated HIGH or CRITICAL. Every alert "
    "separates WHAT HAPPENED from the AI's interpretation.\n\n"
    "Commands:\n"
    "/urgency 80 — only events at this urgency or above (0-100)\n"
    "/assets BTC,SPY — only events touching these symbols (empty = all)\n"
    "/categories crypto,macro — filter: crypto, macro, stocks, geopolitics, commodities\n"
    "/status — your current settings\n"
    "/portfolio — your simulated paper holdings\n"
    "/link CODE — connect this chat to your Sunrise account\n"
    "/unlink — disconnect Telegram from your account\n"
    "/stop — unsubscribe from alerts\n\n"
    "Paper trading: link your account, then tap Buy or Sell under an alert "
    "and confirm. Every order is simulated.\n\n"
    "Not financial advice. AI output is interpretation, never prediction."
)


# Update offsets live in Postgres, not /tmp: a container restart must not
# replay yesterday's commands (or trade callbacks) to subscribers.
OFFSET_KEY = "telegram_update_offset"


async def _load_offset(session: AsyncSession) -> int:
    row = await session.get(MetricCounter, OFFSET_KEY)
    return int(row.value) if row is not None else 0


async def _save_offset(session: AsyncSession, offset: int) -> None:
    row = await session.get(MetricCounter, OFFSET_KEY)
    if row is None:
        session.add(MetricCounter(name=OFFSET_KEY, value=offset))
    else:
        row.value = offset
    await session.commit()


async def _tg_call(client: httpx.AsyncClient, method: str, payload: dict | None = None) -> dict | None:
    settings = get_settings()
    try:
        resp = await client.post(
            f"{API}/bot{settings.telegram_bot_token}/{method}",
            json=payload or {},
            timeout=60,
        )
        data = resp.json()
        return data if data.get("ok") else None
    except Exception as exc:
        log.warn(
            "bot.api_error",
            method=method,
            error=f"{type(exc).__name__}: {exc}"[:150],
        )
        return None


async def _get_or_create_user(session: AsyncSession, chat_id: str) -> tuple[User, UserPreference, bool]:
    user = (
        await session.execute(select(User).where(User.telegram_chat_id == chat_id))
    ).scalar_one_or_none()
    created = False
    if user is None:
        user = User(
            email=f"telegram-{chat_id}@subscribers.sunrise.local",
            telegram_chat_id=chat_id,
        )
        session.add(user)
        await session.flush()
        created = True
    pref = (
        await session.execute(select(UserPreference).where(UserPreference.user_id == user.id))
    ).scalar_one_or_none()
    if pref is None:
        pref = UserPreference(
            user_id=user.id,
            minimum_urgency=60,
            asset_preferences=[],
            category_preferences=[],
            email_enabled=False,
            telegram_enabled=True,
        )
        session.add(pref)
        await session.flush()
    return user, pref, created


async def _send(chat_id: str, text: str, reply_markup: dict | None = None) -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        payload: dict = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        await _tg_call(client, "sendMessage", payload)


async def _handle_callback(session: AsyncSession, callback: dict) -> None:
    chat = (callback.get("message") or {}).get("chat", {}) or {}
    chat_id = str(chat.get("id", "")).strip()
    data = str(callback.get("data") or "")
    if not chat_id or not data:
        return

    # A group chat must never place or approve an order: one linked member
    # would otherwise expose every member's paper account actions.
    if chat.get("type") != "private":
        text, reply_markup = (
            "🔒 Paper trading only works in a private chat with this bot. "
            "Direct-message me and send /link CODE.",
            None,
        )
    else:
        text, reply_markup = await telegram_trade.handle_callback(session, chat_id, data)

    async with httpx.AsyncClient(timeout=20) as client:
        await _tg_call(
            client,
            "answerCallbackQuery",
            {"callback_query_id": callback.get("id"), "text": ""},
        )
        payload: dict = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        await _tg_call(client, "sendMessage", payload)
    log.info("bot.callback", chat=chat_id, data=data[:40])


async def handle_update(session: AsyncSession, update: dict) -> None:
    callback = update.get("callback_query")
    if callback:
        await _handle_callback(session, callback)
        return

    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", "")).strip()
    text = (message.get("text") or "").strip()
    if not chat_id or not text.startswith("/"):
        return

    command, _, arg = text.partition(" ")
    command = command.split("@")[0].lower()

    # Linking is handled before creating a subscriber row: the chat is moving
    # to an existing Cognito-backed user, not signing up as a new subscriber.
    chat_type = (message.get("chat") or {}).get("type", "private")
    if command == "/link":
        if chat_type != "private":
            await _send(
                chat_id,
                "🔒 For safety, link your account from a private chat with this bot.",
            )
            return
        linked, error = await telegram_trade.consume_link_code(session, arg, chat_id)
        if linked is None:
            reply = f"⚠️ {error}"
        else:
            reply = (
                "✅ Linked to your Sunrise account.\n\n"
                "You'll now get paper-trade buttons on impact alerts. Tap a stock, "
                "review the order, then confirm. Every trade is simulated — no broker "
                "is contacted and live trading stays disabled.\n\n"
                "Try /portfolio to see your holdings."
            )
        await _send(chat_id, reply)
        return

    if command == "/unlink":
        unlinked = await telegram_trade.unlink_chat(session, chat_id)
        reply = (
            "🔓 Telegram trading disconnected. You'll keep receiving market alerts."
            if unlinked
            else "This chat was not linked to a Sunrise account."
        )
        await _send(chat_id, reply)
        return

    user, pref, created = await _get_or_create_user(session, chat_id)
    linked_hint = (
        "\n\n📊 Paper trading is linked to your account. Tap a Buy/Sell button on "
        "an alert to review a simulated order."
        if user.cognito_sub and pref.telegram_enabled and telegram_trade.paper_ready()
        else f"\n\nPaper trading: send /link CODE to connect this chat "
        f"(generate the code at {get_settings().public_dashboard_url.rstrip('/')}/trading)."
    )

    if command == "/start":
        pref.telegram_enabled = True
        await session.commit()
        reply = (HELP_TEXT if created else "Welcome back — subscription re-activated.") + linked_hint
    elif command == "/stop":
        pref.telegram_enabled = False
        reply = "Unsubscribed. Send /start anytime to resubscribe."
    elif command == "/urgency":
        try:
            value = max(0, min(100, int(arg.strip())))
            pref.minimum_urgency = value
            reply = f"Minimum urgency set to {value}."
        except ValueError:
            reply = "Usage: /urgency 80"
    elif command == "/assets":
        symbols = [a.upper().strip()[:16] for a in arg.split(",") if a.strip()]
        pref.asset_preferences = symbols
        reply = (
            f"Now filtering to: {', '.join(symbols)}"
            if symbols
            else "Asset filter cleared — you'll receive everything above your urgency threshold."
        )
    elif command == "/categories":
        cats = [c.lower().strip()[:32] for c in arg.split(",") if c.strip()]
        pref.category_preferences = cats
        reply = (
            f"Category filter set to: {', '.join(cats)}"
            if cats
            else "Category filter cleared."
        )
    elif command == "/portfolio":
        if not user.cognito_sub or not telegram_trade.paper_ready():
            reply = telegram_trade.LINK_REQUIRED
        else:
            reply = await telegram_trade.format_portfolio(session, user)
    elif command == "/status":
        reply = (
            f"Subscribed: {'yes' if pref.telegram_enabled else 'no'}\n"
            f"Minimum urgency: {pref.minimum_urgency}\n"
            f"Asset filter: {', '.join(pref.asset_preferences) or 'all'}\n"
            f"Category filter: {', '.join(pref.category_preferences) or 'all'}\n"
            f"Telegram trading: "
            f"{'linked' if user.cognito_sub else 'not linked (/link CODE)'}"
        )
    elif command in {"/help", "/commands"}:
        reply = HELP_TEXT
    else:
        reply = "Unknown command. /help shows what this bot can do."

    await session.commit()
    await _send(chat_id, reply)
    log.info("bot.command", chat=chat_id, command=command)


async def register_command_menu() -> None:
    """Register the '/' command menu so Telegram clients autocomplete commands."""
    async with httpx.AsyncClient(timeout=20) as client:
        await _tg_call(
            client,
            "setMyCommands",
            {
                "commands": [
                    {"command": "start", "description": "Subscribe to market alerts"},
                    {"command": "portfolio", "description": "Your simulated paper holdings"},
                    {"command": "link", "description": "Link this chat: /link CODE"},
                    {"command": "unlink", "description": "Disconnect Telegram trading"},
                    {"command": "urgency", "description": "Minimum urgency 0-100 (e.g. /urgency 80)"},
                    {"command": "assets", "description": "Filter by symbols (e.g. /assets BTC,SPY)"},
                    {"command": "categories", "description": "Filter: crypto, macro, stocks, geopolitics, commodities"},
                    {"command": "status", "description": "Show your current settings"},
                    {"command": "help", "description": "How Sunrise and paper trading work"},
                    {"command": "stop", "description": "Unsubscribe from alerts"},
                ]
            },
        )
    log.info("bot.command_menu_registered")


async def poll_forever() -> None:
    """Long-polling loop; run as a background task in the scheduler process."""
    settings = get_settings()
    if not (settings.telegram_bot_token):
        log.warn("bot.disabled_no_token")
        return

    await register_command_menu()

    factory = get_session_factory()
    async with factory() as session:
        offset = await _load_offset(session)
    log.info("bot.started", offset=offset)
    async with httpx.AsyncClient(timeout=45) as client:
        while True:
            result = await _tg_call(
                client, "getUpdates", {"timeout": 25, "offset": offset}
            )
            if not result:
                await asyncio.sleep(5)
                continue
            for update in result.get("result", []):
                offset = update["update_id"] + 1
                async with factory() as session:
                    # Persist the offset before handling so a bad update cannot
                    # wedge the poller, and a restart cannot replay it.
                    await _save_offset(session, offset)
                    try:
                        await handle_update(session, update)
                    except Exception as exc:
                        log.error("bot.update_failed", error=str(exc)[:200])


if __name__ == "__main__":
    asyncio.run(poll_forever())
