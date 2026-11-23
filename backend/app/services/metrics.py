"""Durable operational counters (LLM calls, etc.)."""

from sqlalchemy import text

from app.core.logging import get_logger
from app.db.session import get_session_factory

log = get_logger("metrics")


async def increment_counter(name: str, amount: int = 1) -> None:
    """Best-effort increment; metrics must never break the caller."""
    try:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(
                text(
                    "INSERT INTO metric_counters (name, value) VALUES (:name, :amount) "
                    "ON CONFLICT (name) DO UPDATE "
                    "SET value = metric_counters.value + :amount"
                ),
                {"name": name, "amount": amount},
            )
            await session.commit()
    except Exception as exc:  # pragma: no cover - defensive
        log.warn("metrics.increment_failed", name=name, error=str(exc)[:150])


async def read_counter(name: str) -> int:
    try:
        factory = get_session_factory()
        async with factory() as session:
            value = (
                await session.execute(
                    text("SELECT value FROM metric_counters WHERE name = :name"),
                    {"name": name},
                )
            ).scalar()
            return int(value or 0)
    except Exception:  # pragma: no cover - defensive
        return 0
