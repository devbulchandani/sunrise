"""Telegram Bot API notifications. No-ops gracefully when unconfigured."""

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("notify.telegram")

IMPACT_ICONS = {
    "positive": "🟢",
    "negative": "🔴",
    "neutral": "⚪",
}

LEVEL_HEADERS = {
    "CRITICAL": "🔴 SUNRISE — CRITICAL MARKET ALERT",
    "HIGH": "🟠 SUNRISE — HIGH-IMPACT EVENT",
}


def telegram_configured() -> bool:
    s = get_settings()
    return bool(s.telegram_bot_token and s.telegram_chat_id)


def format_event_message(event: dict) -> str:
    """event: {level, headline, urgency, confidence?, sentiment?, category?,
    assets: [{symbol, impact}], source_names, reason, url}"""
    level = event.get("level", "RELEVANT")
    header = LEVEL_HEADERS.get(level, f"🔵 SUNRISE — {level} EVENT")

    lines = [header, ""]
    lines.append(event["headline"])
    lines.append("")

    if event.get("urgency") is not None:
        lines.append(f"Urgency: {event['urgency']}/100")
    if event.get("confidence") is not None:
        lines.append(f"AI confidence: {event['confidence']}%")
    if event.get("sentiment"):
        icon = {"BULLISH": "📈", "BEARISH": "📉"}.get(event["sentiment"], "➖")
        lines.append(f"Sentiment: {icon} {event['sentiment']} (AI assessment)")
    lines.append("")

    markets = event.get("markets") or []
    if markets:
        lines.append("Markets potentially affected:")
        lines.append("  " + " · ".join(markets[:6]))
        lines.append("")

    markets = event.get("markets") or []
    if markets:
        lines.append("Markets potentially affected:")
        lines.append("  " + " · ".join(str(m) for m in markets[:6]))
        lines.append("")

    assets = event.get("assets") or []
    if assets:
        asset_lines = [
            f"{IMPACT_ICONS.get(a.get('impact', 'neutral'), '⚪')} {a['symbol']}"
            for a in assets[:8]
        ]
        lines.append("Potentially affected:")
        lines.append("  " + "  ".join(asset_lines))
        lines.append("")

    if event.get("reason"):
        lines.append("WHY IT MAY MATTER (AI interpretation)")
        # wrap at ~70 chars
        reason = event["reason"]
        for i in range(0, len(reason), 72):
            lines.append(reason[i : i + 72])
        lines.append("")

    sources = ", ".join(event.get("source_names", []))
    if sources:
        lines.append(f"SOURCES: {sources}")
    if event.get("url"):
        lines.append("")
        lines.append(f"Read more → {event['url']}")

    return "\n".join(lines)


async def send_telegram(text: str, chat_id: str | None = None) -> tuple[bool, str]:
    settings = get_settings()
    if not telegram_configured():
        return False, "telegram not configured"
    target = chat_id or settings.telegram_chat_id
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": target,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
        if resp.status_code == 200:
            log.info("notification.sent", channel="telegram", chat=target)
            return True, ""
        error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        log.warn("notification.failed", channel="telegram", error=error)
        return False, error
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:300]
        log.warn("notification.failed", channel="telegram", error=error)
        return False, error
