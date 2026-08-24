"""Telegram subscriber bot: lets anyone /start the bot and receive alerts.

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

Run inside the scheduler process so exactly one instance polls.
"""

import asyncio
import json
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.models.models import User, UserPreference

log = get_logger("notify.bot")

API = "https://api.telegram.org"

HELP_TEXT = (
    "☀️ Welcome to Sunrise — autonomous market intelligence.\n\n"
    "You're subscribed. You'll receive market events rated HIGH or CRITICAL "
    "(urgency 61+). Every alert separates FACT from AI interpretation.\n\n"
    "Commands:\n"
    "/urgency 80 — only events at this urgency or above (0-100)\n"
    "/assets BTC,SPY — only events touching these symbols (empty = all)\n"
    "/categories crypto,macro — filter: crypto, macro, stocks, geopolitics, commodities\n"
    "/status — your current settings\n"
    "/stop — unsubscribe\n\n"
    "Not financial advice. AI output is interpretation, never prediction."
)


def _offset_file() -> str:
    import tempfile

    return os_path_join(tempfile.gettempdir(), "sunrise-tg-offset")


def os_path_join(a: str, b: str) -> str:
    return f"{a}/{b}"


def _load_offset() -> int:
    try:
        with open(_offset_file()) as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def _save_offset(offset: int) -> None:
    try:
        with open(_offset_file(), "w") as f:
            f.write(str(offset))
    except OSError:
        pass


async def _tg_call(client: httpx.AsyncClient, method: str, payload: dict | None = None) -> dict | None:
    settings = get_settings()
    try:
        resp = await client.post(
            f"{API}/bot{settings.telegram_bot_token}/{method}",
            json=payload or {},
            timeout=40,
        )
        data = resp.json()
        return data if data.get("ok") else None
    except Exception as exc:
        log.warn("bot.api_error", method=method, error=str(exc)[:150])
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


async def handle_update(session: AsyncSession, update: dict) -> None:
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
    user, pref, created = await _get_or_create_user(session, chat_id)

    if command == "/start":
        pref.telegram_enabled = True
        await session.commit()
        reply = HELP_TEXT if created else "Welcome back — subscription re-activated."
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
    elif command == "/status":
        reply = (
            f"Subscribed: {'yes' if pref.telegram_enabled else 'no'}\n"
            f"Minimum urgency: {pref.minimum_urgency}\n"
            f"Asset filter: {', '.join(pref.asset_preferences) or 'all'}\n"
            f"Category filter: {', '.join(pref.category_preferences) or 'all'}"
        )
    else:
        reply = "Unknown command. /start shows options."

    await session.commit()

    await _tg_call(
        httpx.AsyncClient(),
        "sendMessage",
        {"chat_id": chat_id, "text": reply},
    )
    log.info("bot.command", chat=chat_id, command=command)


async def poll_forever() -> None:
    """Long-polling loop; run as a background task in the scheduler process."""
    settings = get_settings()
    if not (settings.telegram_bot_token):
        log.warn("bot.disabled_no_token")
        return

    offset = _load_offset()
    log.info("bot.started")
    async with httpx.AsyncClient(timeout=45) as client:
        while True:
            result = await _tg_call(
                client, "getUpdates", {"timeout": 30, "offset": offset}
            )
            if not result:
                await asyncio.sleep(5)
                continue
            for update in result.get("result", []):
                offset = update["update_id"] + 1
                _save_offset(offset)
                factory = get_session_factory()
                async with factory() as session:
                    try:
                        await handle_update(session, update)
                    except Exception as exc:
                        log.error("bot.update_failed", error=str(exc)[:200])


if __name__ == "__main__":
    asyncio.run(poll_forever())
