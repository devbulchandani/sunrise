"""Ops alerting: notify the owner channel when the analysis pipeline degrades.

Tracks LLM analysis failures in a sliding window; when failures spike
(e.g. an API key runs out of credits or a model starts misbehaving), a single
Telegram alert goes to the owner chat — rate-limited by a cooldown so a full
outage produces one message, not hundreds.
"""

import time
from collections import deque

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("ops.alerts")

# module-level state (single process: scheduler / worker / maintenance)
_failures: deque[float] = deque()
_last_alert_at: float = 0.0


def _should_alert(
    now: float,
    threshold: int,
    window_seconds: float,
    cooldown_seconds: float,
    last_alert_at: float,
) -> bool:
    """Pure decision helper (unit-testable): did we cross the spike threshold,
    and are we outside the cooldown?"""
    recent = sum(1 for t in _failures if now - t <= window_seconds)
    return recent >= threshold and (now - last_alert_at) >= cooldown_seconds


async def record_analysis_failure(component: str, error: str) -> bool:
    """Record a pipeline failure; alert Telegram if this is a spike. Returns
    True when an alert was sent."""
    global _last_alert_at
    s = get_settings()
    now = time.monotonic()
    _failures.append(now)
    # keep the deque bounded to what any reasonable window needs
    while len(_failures) > max(s.ops_alert_failure_threshold * 10, 100):
        _failures.popleft()

    if not _should_alert(
        now,
        s.ops_alert_failure_threshold,
        s.ops_alert_window_minutes * 60,
        s.ops_alert_cooldown_minutes * 60,
        _last_alert_at,
    ):
        return False

    _last_alert_at = now
    _failures.clear()  # one alert per spike

    msg = (
        f"⚠️ Sunrise pipeline degraded\n\n"
        f"{s.ops_alert_failure_threshold}+ {component} failures in the last "
        f"{s.ops_alert_window_minutes} min.\nLast error: {error[:200]}\n\n"
        f"Check scheduler logs / Scraper Health dashboard."
    )
    log.warn("ops.alert_sent", component=component, error=error[:120])
    try:
        from app.services.notifications.telegram import send_telegram

        ok, detail = await send_telegram(msg)
        if not ok:
            log.error("ops.alert_delivery_failed", detail=detail[:150])
        return ok
    except Exception as exc:  # never let alerting break the pipeline
        log.error("ops.alert_error", error=str(exc)[:150])
        return False


def reset_state() -> None:
    """Test helper."""
    global _last_alert_at
    _failures.clear()
    _last_alert_at = 0.0
