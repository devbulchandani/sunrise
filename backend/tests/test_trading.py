"""Paper-trading integration tests: account, risk, fills, idempotency, cancel."""

from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import require_paper_trader
from app.core.config import get_settings
from app.models.models import Base, PaperOrder, PaperPosition, User
from app.services.trading import broker
from app.services.trading.accounts import account_summary, get_or_create_account
from app.services.trading.quotes import get_quote


@pytest_asyncio.fixture
async def trading(tmp_path, monkeypatch):
    import app.db.session as db_session

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/trading.db")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "_engine", engine)
    monkeypatch.setattr(db_session, "_session_factory", factory)

    settings = get_settings()
    monkeypatch.setattr(settings, "paper_trading_enabled", True)
    monkeypatch.setattr(settings, "paper_trading_frozen", False)
    monkeypatch.setattr(settings, "paper_starting_cash", 100_000.0)
    monkeypatch.setattr(settings, "paper_max_order_notional", 100_000.0)
    monkeypatch.setattr(settings, "paper_max_position_notional", 300_000.0)
    monkeypatch.setattr(settings, "paper_max_gross_exposure", 500_000.0)
    monkeypatch.setattr(settings, "paper_max_daily_orders", 20)
    monkeypatch.setattr(settings, "paper_max_daily_loss", 25_000.0)
    monkeypatch.setattr(settings, "paper_fee_per_order", 20.0)
    monkeypatch.setattr(settings, "paper_slippage_bps", 0.0)
    monkeypatch.setattr(settings, "paper_enforce_market_hours", False)
    monkeypatch.setattr(settings, "paper_limit_band_pct", 20.0)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with factory() as session:
        user = User(email="trader@example.com", cognito_sub="sub-trader")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return {"factory": factory, "user": user, "claims": {"sub": "sub-trader", "email": "trader@example.com"}}


async def _proposal(session, user, claims, **overrides):
    values = {
        "symbol": "RELIANCE",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": 10,
        "limit_price": None,
    }
    values.update(overrides)
    return await broker.create_proposal(session, user, claims, **values)


async def test_account_opening_balance(trading):
    async with trading["factory"]() as session:
        account = await get_or_create_account(session, trading["user"])
        summary = await account_summary(session, account)
    assert summary["cash"] == 100_000.0
    assert summary["equity"] == 100_000.0
    assert summary["mode"] == "paper"


async def test_market_buy_fills_and_updates_ledger(trading):
    async with trading["factory"]() as session:
        proposal = await _proposal(session, trading["user"], trading["claims"])
        assert broker.proposal_view(proposal)["approved"] is True

        order, account, idempotent = await broker.confirm_proposal(
            session, trading["user"], trading["claims"], proposal.id
        )
        assert idempotent is False
        assert order.status == "FILLED"
        assert order.filled_quantity == 10
        assert order.average_fill_price is not None

        position = (
            await session.execute(
                PaperPosition.__table__.select().where(PaperPosition.account_id == account.id)
            )
        ).first()
        assert position.quantity == 10
        summary = await account_summary(session, account)
        assert summary["cash"] < 100_000
        assert summary["position_count"] == 1
        assert summary["positions_value"] > 0


async def test_confirm_is_idempotent(trading):
    async with trading["factory"]() as session:
        proposal = await _proposal(session, trading["user"], trading["claims"], quantity=5)
        first, _account, first_idempotent = await broker.confirm_proposal(
            session, trading["user"], trading["claims"], proposal.id
        )
        second, _account2, second_idempotent = await broker.confirm_proposal(
            session, trading["user"], trading["claims"], proposal.id
        )
        count = (
            await session.execute(PaperOrder.__table__.select())
        ).all()
    assert first.id == second.id
    assert first_idempotent is False
    assert second_idempotent is True
    assert len(count) == 1


async def test_oversized_order_is_rejected(trading, monkeypatch):
    monkeypatch.setattr(get_settings(), "paper_max_order_notional", 1_000.0)
    async with trading["factory"]() as session:
        proposal = await _proposal(session, trading["user"], trading["claims"], quantity=10)
        view = broker.proposal_view(proposal)
        assert view["approved"] is False
        assert any(check["name"] == "order_notional" and not check["ok"] for check in view["checks"])
        with pytest.raises(broker.TradingError):
            await broker.confirm_proposal(
                session, trading["user"], trading["claims"], proposal.id
            )


async def test_sell_requires_position(trading):
    async with trading["factory"]() as session:
        proposal = await _proposal(
            session, trading["user"], trading["claims"], side="SELL", quantity=1
        )
        view = broker.proposal_view(proposal)
        assert view["approved"] is False
        assert any(check["name"] == "position_available" and not check["ok"] for check in view["checks"])


async def test_limit_order_stays_open_then_cancels(trading):
    quote = get_quote("RELIANCE")
    assert quote is not None
    limit = (quote.price * Decimal("0.99")).quantize(Decimal("0.01"))
    async with trading["factory"]() as session:
        proposal = await _proposal(
            session,
            trading["user"],
            trading["claims"],
            order_type="LIMIT",
            quantity=3,
            limit_price=limit,
        )
        order, _account, _ = await broker.confirm_proposal(
            session, trading["user"], trading["claims"], proposal.id
        )
        assert order.status == "OPEN"
        cancelled = await broker.cancel_order(
            session, trading["user"], trading["claims"], order.id
        )
        assert cancelled.status == "CANCELLED"


async def test_market_hours_check_can_block(trading, monkeypatch):
    monkeypatch.setattr(get_settings(), "paper_enforce_market_hours", True)
    monkeypatch.setattr("app.services.trading.risk.is_market_open", lambda: False)
    async with trading["factory"]() as session:
        proposal = await _proposal(session, trading["user"], trading["claims"])
        view = broker.proposal_view(proposal)
        assert view["approved"] is False
        assert any(check["name"] == "market_hours" and not check["ok"] for check in view["checks"])


async def test_reconciliation_is_clean_after_fill(trading):
    async with trading["factory"]() as session:
        proposal = await _proposal(session, trading["user"], trading["claims"], quantity=2)
        await broker.confirm_proposal(session, trading["user"], trading["claims"], proposal.id)
        account = await get_or_create_account(session, trading["user"])
        result = await broker.reconcile_account(session, account)
    assert result["ok"] is True
    assert result["discrepancies"] == []


async def test_reconciliation_detects_cash_drift(trading):
    async with trading["factory"]() as session:
        account = await get_or_create_account(session, trading["user"])
        account.cash = account.cash + Decimal("1.00")
        await session.commit()
        result = await broker.reconcile_account(session, account)
    assert result["ok"] is False
    assert any(item["kind"] == "cash" for item in result["discrepancies"])


async def test_paper_kill_switches(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "paper_trading_frozen", True)
    with pytest.raises(HTTPException) as frozen:
        await require_paper_trader({"sub": "someone"})
    assert frozen.value.status_code == 503

    monkeypatch.setattr(settings, "paper_trading_frozen", False)
    monkeypatch.setattr(settings, "paper_trading_enabled", False)
    with pytest.raises(HTTPException) as disabled:
        await require_paper_trader({"sub": "someone"})
    assert disabled.value.status_code == 503


async def test_trading_routes_require_auth_and_full_flow(trading, monkeypatch):
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        config = await client.get("/api/trading/config")
        assert config.status_code == 200
        assert config.json()["paper_enabled"] is True
        assert config.json()["live_enabled"] is False
        assert len(config.json()["instruments"]) > 5

        unauthorized = await client.get("/api/trading/account")
        assert unauthorized.status_code == 401

        app.dependency_overrides[require_paper_trader] = lambda: trading["claims"]
        try:
            account = await client.get("/api/trading/account")
            assert account.status_code == 200
            assert account.json()["cash"] == 100_000.0

            proposal = await client.post(
                "/api/trading/proposals",
                json={
                    "symbol": "INFY",
                    "side": "BUY",
                    "order_type": "MARKET",
                    "quantity": 2,
                },
            )
            assert proposal.status_code == 201
            body = proposal.json()
            assert body["approved"] is True

            confirmed = await client.post(f"/api/trading/proposals/{body['id']}/confirm")
            assert confirmed.status_code == 200
            assert confirmed.json()["order"]["status"] == "FILLED"

            orders = await client.get("/api/trading/orders")
            assert orders.status_code == 200
            assert len(orders.json()) == 1
        finally:
            app.dependency_overrides.pop(require_paper_trader, None)
