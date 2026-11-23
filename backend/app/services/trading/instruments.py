"""Curated paper-trading universe.

Prices are deliberately *simulated* and only exist to exercise the ledger,
risk checks, and fills. They are not a market-data feed and must never be
presented as live quotes.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    exchange: str
    sector: str
    base_price: Decimal


def _i(symbol: str, name: str, sector: str, price: str) -> Instrument:
    return Instrument(
        symbol=symbol,
        name=name,
        exchange="NSE",
        sector=sector,
        base_price=Decimal(price),
    )


INSTRUMENTS: dict[str, Instrument] = {
    item.symbol: item
    for item in [
        _i("RELIANCE", "Reliance Industries", "Energy", "2940.00"),
        _i("TCS", "Tata Consultancy Services", "Technology", "4120.00"),
        _i("INFY", "Infosys", "Technology", "1880.00"),
        _i("HDFCBANK", "HDFC Bank", "Financials", "1740.00"),
        _i("ICICIBANK", "ICICI Bank", "Financials", "1380.00"),
        _i("SBIN", "State Bank of India", "Financials", "860.00"),
        _i("AXISBANK", "Axis Bank", "Financials", "1180.00"),
        _i("KOTAKBANK", "Kotak Mahindra Bank", "Financials", "1760.00"),
        _i("BAJFINANCE", "Bajaj Finance", "Financials", "8900.00"),
        _i("TATASTEEL", "Tata Steel", "Materials", "165.00"),
        _i("LT", "Larsen & Toubro", "Industrials", "3650.00"),
        _i("BHARTIARTL", "Bharti Airtel", "Telecom", "1640.00"),
        _i("ITC", "ITC", "Consumer", "445.00"),
        _i("HINDUNILVR", "Hindustan Unilever", "Consumer", "2480.00"),
        _i("MARUTI", "Maruti Suzuki", "Auto", "12400.00"),
        _i("ASIANPAINT", "Asian Paints", "Materials", "2420.00"),
        _i("ADANIENT", "Adani Enterprises", "Conglomerate", "2350.00"),
        _i("WIPRO", "Wipro", "Technology", "260.00"),
        _i("SUNPHARMA", "Sun Pharmaceutical", "Healthcare", "1720.00"),
        _i("TITAN", "Titan Company", "Consumer", "3450.00"),
        _i("NIFTYBEES", "Nippon India Nifty 50 ETF", "ETF", "280.00"),
        _i("GOLDBEES", "Nippon India Gold ETF", "ETF", "68.00"),
    ]
}


def get_instrument(symbol: str) -> Instrument | None:
    return INSTRUMENTS.get((symbol or "").strip().upper())


def list_instruments() -> list[Instrument]:
    return sorted(INSTRUMENTS.values(), key=lambda item: item.symbol)
