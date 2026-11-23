"""Telegram Bot API notifications. No-ops gracefully when unconfigured."""

import textwrap

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("notify.telegram")

IMPACT_ICONS = {
    "positive": "🟢",
    "negative": "🔴",
    "neutral": "⚪",
}

# Plain-English label for the AI's per-asset direction.
IMPACT_WORDS = {
    "positive": "tailwind",
    "negative": "headwind",
    "neutral": "neutral",
}

LEVEL_HEADERS = {
    "CRITICAL": "🔴 SUNRISE · CRITICAL SIGNAL",
    "HIGH": "🟠 SUNRISE · HIGH-IMPACT SIGNAL",
    "RELEVANT": "🔵 SUNRISE · SIGNAL",
    "BACKGROUND": "⚪ SUNRISE · BACKGROUND",
}


def telegram_configured() -> bool:
    """A bot token is enough: per-chat sends do not need the owner's chat id."""
    return bool(get_settings().telegram_bot_token)


def _clip(text: str | None, limit: int) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _wrap(text: str, width: int = 72) -> str:
    """Word-wrap paragraphs so Telegram/email lines break at spaces."""
    lines: list[str] = []
    for paragraph in (text or "").split("\n"):
        paragraph = " ".join(paragraph.split())
        if not paragraph:
            continue
        lines.extend(
            textwrap.wrap(
                paragraph,
                width=width,
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    return "\n".join(lines)


def format_event_message(event: dict, paper_hint: bool = False) -> str:
    """A clear, sectioned alert.

    event: {level, headline, summary?, urgency, confidence?, sentiment?,
    category?, assets: [{symbol, impact, confidence?}], source_names, reason,
    markets?, url?}
    """
    level = event.get("level", "RELEVANT")
    header = LEVEL_HEADERS.get(level, f"🔵 SUNRISE · {level} SIGNAL")

    facts = [
        f"{event.get('urgency', 0)}/100 urgency",
    ]
    if event.get("confidence") is not None:
        facts.append(f"{event['confidence']}% AI confidence")
    if event.get("sentiment"):
        icon = {"BULLISH": "📈", "BEARISH": "📉"}.get(event["sentiment"], "➖")
        facts.append(f"{icon} {event['sentiment']}")
    if event.get("category"):
        facts.append(str(event["category"]).replace("_", " ").title())

    lines = [header, " · ".join(facts), "", "WHAT HAPPENED"]
    lines.append(_clip(event.get("headline"), 300) or "Headline unavailable")
    summary = _clip(event.get("summary"), 700)
    if summary and summary != event.get("headline"):
        lines.append("")
        lines.append(_wrap(summary))

    reason = _clip(event.get("reason"), 700)
    if reason:
        lines.extend(
            [
                "",
                "WHY IT MAY MATTER (AI interpretation, not a forecast)",
                _wrap(reason),
            ]
        )

    assets = event.get("assets") or []
    if assets:
        lines.extend(["", "STOCKS THE AI FLAGS"])
        for asset in assets[:6]:
            impact = (asset.get("impact") or "neutral").lower()
            label = IMPACT_WORDS.get(impact, "unclear")
            confidence = asset.get("confidence")
            suffix = f" · {confidence}% confidence" if confidence is not None else ""
            lines.append(
                f"{IMPACT_ICONS.get(impact, '⚪')} {asset.get('symbol', '?')} — "
                f"{label}{suffix}"
            )

    markets = event.get("markets") or []
    if markets:
        lines.extend(["", "MARKETS MENTIONED", " · ".join(str(m) for m in markets[:6])])

    ipo = event.get("ipo")
    if ipo:
        lines.extend(["", "IPO RESEARCH (AI-generated, not advice)"])
        if ipo.get("company_overview"):
            lines.append(_wrap(_clip(ipo["company_overview"], 400)))
        strengths = ipo.get("strengths") or []
        risks = ipo.get("risks") or []
        if strengths:
            lines.append("Strengths: " + _clip("; ".join(strengths[:3]), 300))
        if risks:
            lines.append("Risks: " + _clip("; ".join(risks[:3]), 300))

    context = event.get("market_context")
    if context and context.get("queries"):
        lines.extend(
            [
                "",
                "MARKET CONTEXT (live research)",
                f"verified via: {', '.join(context['queries'][:3])}",
            ]
        )

    sources = ", ".join(event.get("source_names") or [])
    if sources:
        lines.extend(["", f"SOURCES: {_clip(sources, 300)}"])
    if event.get("url"):
        lines.append(f"Full signal → {event['url']}")

    if paper_hint:
        lines.extend(
            [
                "",
                "Paper desk: tap a button below for a simulated trade. "
                "Nothing is submitted until you confirm.",
            ]
        )
    lines.extend(["", "AI output can be wrong. Verify before acting. Not investment advice."])
    return _clip("\n".join(lines), 3900)


async def send_telegram(
    text: str, chat_id: str | None = None, reply_markup: dict | None = None
) -> tuple[bool, str]:
    settings = get_settings()
    if not telegram_configured():
        return False, "telegram not configured"
    target = chat_id or settings.telegram_chat_id
    payload: dict = {
        "chat_id": target,
        "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json=payload,
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
