"""Tests for ops failure-spike alerting."""

from app.services.notifications import ops_alerts
from app.services.notifications.ops_alerts import _should_alert


def setup_function() -> None:
    ops_alerts.reset_state()


def test_no_alert_below_threshold() -> None:
    assert not _should_alert(now=600.0, threshold=5, window_seconds=600,
                             cooldown_seconds=1800, last_alert_at=0.0)


def test_alert_at_threshold_within_window() -> None:
    # 5 failures inside a 600s window (all recent relative to now=2000)
    for t in (1990, 1992, 1994, 1996, 1998):
        ops_alerts._failures.append(t)
    assert _should_alert(now=2000.0, threshold=5, window_seconds=600,
                         cooldown_seconds=1800, last_alert_at=0.0)


def test_no_alert_when_failures_outside_window() -> None:
    # all 5 failures happened well before the 600s window ending at now=2000
    for t in (10, 12, 14, 16, 18):
        ops_alerts._failures.append(t)
    assert not _should_alert(now=2000.0, threshold=5, window_seconds=600,
                             cooldown_seconds=1800, last_alert_at=0.0)


def test_cooldown_blocks_second_alert() -> None:
    for t in (1990, 1992, 1994, 1996, 1998):
        ops_alerts._failures.append(t)
    # last alert was only 60s ago; cooldown is 1800s
    assert not _should_alert(now=2000.0, threshold=5, window_seconds=600,
                             cooldown_seconds=1800, last_alert_at=1940.0)


async def test_record_failure_alerts_and_resets(monkeypatch) -> None:
    import app.core.config as config

    sent = []

    async def fake_send(text, chat_id=None):
        sent.append(text)
        return True, "ok"

    monkeypatch.setattr(
        "app.services.notifications.telegram.send_telegram", fake_send
    )
    settings = config.get_settings()
    monkeypatch.setattr(settings, "ops_alert_failure_threshold", 2)

    from app.services.notifications.ops_alerts import record_analysis_failure

    assert await record_analysis_failure("LLM analysis", "boom") is False
    assert not sent  # below threshold
    assert await record_analysis_failure("LLM analysis", "boom again") is True
    assert len(sent) == 1
    assert "Sunrise pipeline degraded" in sent[0]
    # spike consumed -> immediate further failures don't re-alert
    assert await record_analysis_failure("LLM analysis", "third") is False
    assert len(sent) == 1
