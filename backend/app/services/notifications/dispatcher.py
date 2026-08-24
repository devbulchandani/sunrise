"""Notification dispatch: filter events by user preferences, send to channels."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.models import (
    EventAsset,
    MarketEvent,
    Notification,
    Source,
    User,
    UserPreference,
)
from app.services.analysis.urgency import urgency_level
from app.services.notifications.email import email_configured, send_email
from app.services.notifications.telegram import format_event_message, send_telegram, telegram_configured

log = get_logger("notify.dispatch")

# minimum urgency levels that each channel sends at all (anti-spam floor)
CHANNEL_FLOORS = {"telegram": 61, "email": 41}


def user_wants(user_pref: UserPreference | None, event: MarketEvent, assets: list[str]) -> bool:
    """Filter an event against one user's preferences."""
    if event.analysis_status != "DONE":
        return False
    min_urgency = user_pref.minimum_urgency if user_pref else 60
    if event.urgency < min_urgency:
        return False

    if user_pref:
        cats = set(user_pref.category_preferences or [])
        if cats and _category_group(event.category) not in cats:
            return False
        wanted_assets = set(user_pref.asset_preferences or [])
        if wanted_assets and not (set(assets) & wanted_assets):
            # no overlap with watched assets -> only pass if urgency is critical
            if event.urgency < 81:
                return False
    return True


CATEGORY_GROUPS = {
    "MONETARY_POLICY": "macro", "INFLATION": "macro", "EMPLOYMENT": "macro",
    "GDP": "macro", "REGULATION": "macro", "BANKING": "stocks", "EARNINGS": "stocks",
    "MERGERS_ACQUISITIONS": "stocks", "MARKET_MOVEMENT": "stocks", "TECHNOLOGY": "stocks",
    "AI": "stocks", "CRYPTO": "crypto", "GEOPOLITICS": "geopolitics",
    "COMMODITIES": "commodities", "ENERGY": "commodities", "OTHER": "other",
}


def _category_group(category: str) -> str:
    return CATEGORY_GROUPS.get(category, "other")


def build_event_payload(event: MarketEvent, source_names: list[str], primary_url: str | None) -> dict:
    return {
        "markets": getattr(event, "affected_markets", None) or [],
        "event_id": event.id,
        "level": urgency_level(event.urgency),
        "headline": event.headline,
        "urgency": event.urgency,
        "confidence": event.confidence,
        "sentiment": event.sentiment,
        "category": event.category,
        "reason": event.reason or "",
        "source_names": source_names,
        "url": primary_url,
    }


async def dispatch_event_notifications(session: AsyncSession, event_id: int) -> int:
    """Send notifications for a completed event according to user prefs.
    Returns count of successfully sent notifications."""
    settings = get_settings()

    event_result = await session.execute(
        select(MarketEvent).where(MarketEvent.id == event_id)
    )
    event = event_result.scalar_one_or_none()
    if event is None:
        return 0

    assets_result = await session.execute(
        select(EventAsset).where(EventAsset.event_id == event.id)
    )
    assets = list(assets_result.scalars())
    asset_symbols = [a.symbol for a in assets]

    users_result = await session.execute(select(User))
    users = list(users_result.scalars())

    sent = 0
    for user in users:
        pref_result = await session.execute(
            select(UserPreference).where(UserPreference.user_id == user.id)
        )
        pref = pref_result.scalar_one_or_none()

        if not user_wants(pref, event, asset_symbols):
            continue

        # dedupe: never send the same event twice to the same user/channel
        already = await session.execute(
            select(Notification.id).where(
                Notification.user_id == user.id,
                Notification.event_id == event.id,
                Notification.channel == "telegram",
                Notification.status.in_(["SENT", "QUEUED"]),
            )
        )
        if already.scalar() is not None:
            continue

        payload = build_event_message_context(event, assets)

        # telegram: only real bot subscribers (a None chat would fall back
        # to the owner's env chat and cause duplicate deliveries)
        if (
            user.telegram_chat_id
            and (pref is None or pref.telegram_enabled)
            and telegram_configured()
        ):
            ok, err = await _send_telegram_for_user(session, user, event, payload)
            if ok:
                sent += 1

        if (
            (pref is None or pref.email_enabled)
            and email_configured()
            and user.email
            and not user.email.endswith("@subscribers.sunrise.local")
        ):
            text = format_event_message(payload)
            ok, err = send_email(user.email, f"Sunrise — {payload['level']}: {event.headline[:80]}", text)
            session.add(
                Notification(
                    user_id=user.id, event_id=event.id, channel="email",
                    status="SENT" if ok else "FAILED", error=err or None,
                    sent_at=datetime.now(timezone.utc) if ok else None,
                )
            )
            if ok:
                sent += 1

    # owner's default chat from env — always receives critical+ events,
    # skipped if the owner also subscribed via the bot (would double-send)
    if telegram_configured() and event.urgency >= CHANNEL_FLOORS["telegram"]:
        owner_is_subscriber = any(
            u.telegram_chat_id == settings.telegram_chat_id for u in users
        )
        if not users or not owner_is_subscriber:
            payload = build_event_message_context(event, assets)
            text = format_event_message(payload)
            ok, err = await send_telegram(text)
            session.add(
                Notification(
                    event_id=event.id, channel="telegram",
                    status="SENT" if ok else "FAILED", error=err or None,
                    sent_at=datetime.now(timezone.utc) if ok else None,
                )
            )
            if ok:
                sent += 1

    await session.commit()
    log.info("notifications.dispatched", event=event_id, sent=sent)
    return sent


def build_event_message_context(event: MarketEvent, assets) -> dict:
    from sqlalchemy import select as _select

    return {
        "event_id": event.id,
        "level": urgency_level(event.urgency),
        "headline": event.headline,
        "urgency": event.urgency,
        "confidence": event.confidence,
        "sentiment": event.sentiment,
        "category": event.category,
        "reason": event.reason or "",
        "markets": event.affected_markets or [],
        "assets": [
            {"symbol": a.symbol, "impact": a.impact} for a in assets
        ],
        "source_names": getattr(event, "_source_names", []),
        "url": getattr(event, "_primary_url", None),
    }


async def _send_telegram_for_user(session, user, event, payload):
    if not telegram_configured():
        return False, ""
    chat_id = user.telegram_chat_id  # None -> default env chat
    text = format_event_message(payload)
    ok, err = await send_telegram(text, chat_id=chat_id)
    session.add(
        Notification(
            user_id=user.id,
            event_id=event.id,
            channel="telegram",
            status="SENT" if ok else "FAILED",
            error=err or None,
            sent_at=datetime.now(timezone.utc) if ok else None,
        )
    )
    return ok, err
