"""Deterministic simulated quotes for the paper desk."""

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.services.trading.instruments import Instrument, get_instrument

_CENTS = Decimal("0.01")


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: Decimal
    currency: str
    source: str
    as_of: datetime
    instrument: Instrument

    def summary(self) -> dict:
        return {
            "symbol": self.symbol,
            "price": float(self.price),
            "currency": self.currency,
            "source": self.source,
            "as_of": self.as_of.isoformat(),
            "instrument": {
                "symbol": self.instrument.symbol,
                "name": self.instrument.name,
                "exchange": self.instrument.exchange,
                "sector": self.instrument.sector,
            },
        }


def get_quote(symbol: str, at: datetime | None = None) -> Quote | None:
    """Return a stable, slowly-moving simulated quote for a supported symbol."""
    instrument = get_instrument(symbol)
    if instrument is None:
        return None

    moment = at or datetime.now(timezone.utc)
    seed = int(hashlib.sha256(instrument.symbol.encode()).hexdigest()[:8], 16)
    phase = moment.timestamp() / 600.0 + (seed % 997)
    wave = 0.006 * math.sin(phase) + 0.003 * math.sin(phase * 2.3 + 1.7)
    price = (instrument.base_price * (Decimal("1") + Decimal(str(wave)))).quantize(
        _CENTS, rounding=ROUND_HALF_UP
    )
    return Quote(
        symbol=instrument.symbol,
        price=price,
        currency="INR",
        source="simulated",
        as_of=moment,
        instrument=instrument,
    )
