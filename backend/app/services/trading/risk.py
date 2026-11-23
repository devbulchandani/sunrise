"""Deterministic risk checks for paper orders.

Every check is returned, not just the first failure, so the desk can show the
full picture before a user confirms. The same policy runs at proposal time and
again at confirmation time with a fresh quote.
"""

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.services.trading.quotes import Quote

_IST = ZoneInfo("Asia/Kolkata")
_CENTS = Decimal("0.01")
MAX_QUANTITY = 1_000_000


@dataclass
class RiskCheck:
    name: str
    ok: bool
    detail: str

    def as_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass
class RiskResult:
    checks: list[RiskCheck]
    approved: bool
    notional: Decimal
    fee: Decimal
    quote: Quote

    @property
    def failed(self) -> list[RiskCheck]:
        return [check for check in self.checks if not check.ok]


def is_market_open(at: datetime | None = None) -> bool:
    moment = at.astimezone(_IST) if at else datetime.now(_IST)
    if moment.weekday() >= 5:
        return False
    return time(9, 15) <= moment.time() <= time(15, 30)


def evaluate_order(
    *,
    side: str,
    order_type: str,
    quantity: int,
    limit_price: Decimal | None,
    quote: Quote,
    cash: Decimal,
    position_quantity: int,
    gross_exposure: Decimal,
    daily_orders: int,
    daily_realized_loss: Decimal,
    settings: Settings,
) -> RiskResult:
    checks: list[RiskCheck] = []
    side = (side or "").upper()
    order_type = (order_type or "").upper()

    checks.append(
        RiskCheck(
            "side",
            side in {"BUY", "SELL"},
            f"Order side must be BUY or SELL (got {side or 'empty'}).",
        )
    )
    checks.append(
        RiskCheck(
            "order_type",
            order_type in {"MARKET", "LIMIT"},
            f"Order type must be MARKET or LIMIT (got {order_type or 'empty'}).",
        )
    )
    checks.append(
        RiskCheck(
            "quantity",
            1 <= quantity <= MAX_QUANTITY,
            f"Quantity must be between 1 and {MAX_QUANTITY} (got {quantity}).",
        )
    )

    if order_type == "LIMIT":
        checks.append(
            RiskCheck(
                "limit_price",
                limit_price is not None and limit_price > 0,
                "A limit order needs a positive limit price.",
            )
        )
        if limit_price is not None and limit_price > 0 and quote.price > 0:
            deviation = abs(limit_price - quote.price) / quote.price * Decimal("100")
            band = Decimal(str(settings.paper_limit_band_pct))
            checks.append(
                RiskCheck(
                    "limit_band",
                    deviation <= band,
                    f"Limit is {deviation:.1f}% from the simulated quote; the band is ±{band}%.",
                )
            )
    else:
        checks.append(RiskCheck("limit_price", True, "Market orders do not use a limit price."))

    pricing = limit_price if order_type == "LIMIT" and limit_price else quote.price
    notional = (pricing * Decimal(quantity)).quantize(_CENTS, rounding=ROUND_HALF_UP)
    fee = Decimal(str(settings.paper_fee_per_order)).quantize(_CENTS)

    checks.append(
        RiskCheck(
            "order_notional",
            notional <= Decimal(str(settings.paper_max_order_notional)),
            f"Order notional ₹{notional:,.2f} must be ≤ ₹{settings.paper_max_order_notional:,.2f}.",
        )
    )

    if side == "BUY":
        required = notional + fee
        checks.append(
            RiskCheck(
                "buying_power",
                cash >= required,
                f"Cash ₹{cash:,.2f} must cover ₹{required:,.2f} (notional + fee).",
            )
        )
        resulting_position = (
            Decimal(position_quantity) * quote.price + notional
        ).quantize(_CENTS)
        checks.append(
            RiskCheck(
                "position_limit",
                resulting_position <= Decimal(str(settings.paper_max_position_notional)),
                f"Position value ₹{resulting_position:,.2f} must be ≤ ₹{settings.paper_max_position_notional:,.2f}.",
            )
        )
        resulting_exposure = (gross_exposure + notional).quantize(_CENTS)
    else:
        checks.append(
            RiskCheck(
                "position_available",
                position_quantity >= quantity,
                f"You hold {position_quantity} {quote.symbol}; cannot sell {quantity}.",
            )
        )
        checks.append(
            RiskCheck("buying_power", True, "Sells credit cash; no buying power is required.")
        )
        checks.append(
            RiskCheck("position_limit", True, "Sells reduce position value.")
        )
        resulting_exposure = max(gross_exposure - notional, Decimal("0")).quantize(_CENTS)

    checks.append(
        RiskCheck(
            "gross_exposure",
            resulting_exposure <= Decimal(str(settings.paper_max_gross_exposure)),
            f"Gross exposure ₹{resulting_exposure:,.2f} must be ≤ ₹{settings.paper_max_gross_exposure:,.2f}.",
        )
    )
    checks.append(
        RiskCheck(
            "daily_orders",
            daily_orders < settings.paper_max_daily_orders,
            f"{daily_orders} orders today; the cap is {settings.paper_max_daily_orders}.",
        )
    )
    checks.append(
        RiskCheck(
            "daily_loss",
            daily_realized_loss < Decimal(str(settings.paper_max_daily_loss)),
            f"Realised loss today ₹{daily_realized_loss:,.2f} must stay below ₹{settings.paper_max_daily_loss:,.2f}.",
        )
    )
    if settings.paper_enforce_market_hours:
        checks.append(
            RiskCheck(
                "market_hours",
                is_market_open(),
                "NSE market hours are 09:15–15:30 IST, Monday–Friday.",
            )
        )
    else:
        checks.append(
            RiskCheck(
                "market_hours",
                True,
                "Market-hours enforcement is off for this paper environment.",
            )
        )

    return RiskResult(
        checks=checks,
        approved=all(check.ok for check in checks),
        notional=notional,
        fee=fee,
        quote=quote,
    )
