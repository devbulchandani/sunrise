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
from app.services.trading import broker, telegram_trade
from app.services.trading.accounts import (
    account_summary,
    get_or_create_account,
    portfolio_snapshot,
)
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
    monkeypatch.setattr(settings, "paper_telegram_enabled", True)
    monkeypatch.setattr(settings, "paper_telegram_ticket_notional", 25_000.0)
    monkeypatch.setattr(settings, "paper_telegram_max_symbols", 4)
    monkeypatch.setattr(settings, "paper_telegram_link_ttl_seconds", 600)

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

            portfolio = await client.get("/api/trading/portfolio")
            assert portfolio.status_code == 200
            book = portfolio.json()
            assert book["account"]["position_count"] == 1
            assert book["positions"][0]["symbol"] == "INFY"
            assert 0 < book["positions"][0]["weight_pct"] < 100

            link_code = await client.post("/api/trading/telegram/link-code")
            assert link_code.status_code == 201
            assert len(link_code.json()["code"]) == 8

            link_status = await client.get("/api/trading/telegram")
            assert link_status.status_code == 200
            assert link_status.json()["linked"] is False

            unlinked = await client.delete("/api/trading/telegram")
            assert unlinked.status_code == 200
            assert unlinked.json()["linked"] is False
        finally:
            app.dependency_overrides.pop(require_paper_trader, None)


async def test_portfolio_marks_every_holding(trading):
    async with trading["factory"]() as session:
        proposal = await _proposal(session, trading["user"], trading["claims"], quantity=10)
        await broker.confirm_proposal(session, trading["user"], trading["claims"], proposal.id)
        account = await get_or_create_account(session, trading["user"])
        snapshot = await portfolio_snapshot(session, account)

    assert snapshot["position_count"] == 1
    row = snapshot["positions"][0]
    assert row["symbol"] == "RELIANCE"
    assert row["quantity"] == 10
    assert row["cost_basis"] > 0
    assert row["market_value"] > 0
    assert 0 < row["weight_pct"] < 100
    assert 0 < snapshot["cash_weight_pct"] < 100
    assert snapshot["invested"] > 0
    assert snapshot["account"]["position_count"] == 1
    assert abs(snapshot["total_return_pct"]) < 5


async def test_telegram_link_code_is_single_use(trading):
    async with trading["factory"]() as session:
        code, expires_at = await telegram_trade.issue_link_code(session, trading["user"])
        assert len(code) == 8
        assert expires_at is not None

        user, error = await telegram_trade.consume_link_code(session, code, "5550001")
        assert error == ""
        assert user is not None
        assert user.telegram_chat_id == "5550001"

        reused, error = await telegram_trade.consume_link_code(session, code, "5550002")
        assert reused is None
        assert "invalid or already used" in error

        wrong, error = await telegram_trade.consume_link_code(session, "NOSUCH01", "5550003")
        assert wrong is None
        assert "invalid" in error


async def test_telegram_link_requires_verified_identity(trading):
    from sqlalchemy import select
    from app.models.models import User

    async with trading["factory"]() as session:
        subscriber = User(email="tg@subscribers.sunrise.local", telegram_chat_id="777")
        session.add(subscriber)
        await session.commit()
        with pytest.raises(broker.TradingError):
            await telegram_trade.issue_link_code(session, subscriber)
        stored = (
            await session.execute(select(User).where(User.id == subscriber.id))
        ).scalar_one()
        assert stored.cognito_sub is None


async def test_telegram_quick_trade_requires_link(trading):
    async with trading["factory"]() as session:
        text, markup = await telegram_trade.handle_callback(session, "999", "pt:0:INFY:B")
    assert markup is None
    assert "not linked" in text.lower()


async def test_telegram_quick_trade_confirm_flow(trading):
    async with trading["factory"]() as session:
        code, _ = await telegram_trade.issue_link_code(session, trading["user"])
        linked, error = await telegram_trade.consume_link_code(session, code, "5550009")
        assert error == "" and linked is not None

        text, markup = await telegram_trade.handle_callback(
            session, "5550009", "pt:0:INFY:B"
        )
        assert "REVIEW PAPER ORDER" in text
        assert markup is not None
        confirm_data = markup["inline_keyboard"][0][0]["callback_data"]
        assert confirm_data.startswith("pc:")
        proposal_id = int(confirm_data.split(":")[1])

        filled, result_markup = await telegram_trade.handle_callback(
            session, "5550009", confirm_data
        )
        assert "FILLED" in filled
        assert result_markup is None

        replay, _ = await telegram_trade.handle_callback(session, "5550009", confirm_data)
        assert "Already confirmed" in replay

        account = await get_or_create_account(session, trading["user"])
        snapshot = await portfolio_snapshot(session, account)
        assert any(row["symbol"] == "INFY" for row in snapshot["positions"])
        assert proposal_id > 0


async def test_telegram_sell_button_only_for_held_symbols(trading):
    from sqlalchemy import select

    async with trading["factory"]() as session:
        code, _ = await telegram_trade.issue_link_code(session, trading["user"])
        await telegram_trade.consume_link_code(session, code, "5550010")
        user = (
            await session.execute(select(User).where(User.id == trading["user"].id))
        ).scalar_one()

        keyboard = await telegram_trade.trade_keyboard(
            session,
            user,
            7,
            [
                {"symbol": "INFY", "impact": "positive", "confidence": 70},
                {"symbol": "NOTAREALSYMBOL", "impact": "negative", "confidence": 50},
            ],
        )
        assert keyboard is not None
        rows = keyboard["inline_keyboard"]
        assert rows[0][0]["callback_data"] == "pt:7:INFY:B"
        assert len(rows[0]) == 1  # no position, so no sell button
        assert rows[-1][0]["url"].endswith("/trading?event=7")


async def test_telegram_confirm_does_not_cross_accounts(trading):
    from app.models.models import User

    async with trading["factory"]() as session:
        proposal = await _proposal(session, trading["user"], trading["claims"], quantity=1)

        other = User(email="other@example.com", cognito_sub="sub-other")
        session.add(other)
        await session.commit()
        code, _ = await telegram_trade.issue_link_code(session, other)
        await telegram_trade.consume_link_code(session, code, "5550011")

        text, _markup = await telegram_trade.handle_callback(
            session, "5550011", f"pc:{proposal.id}"
        )
    assert "not found" in text.lower()


async def test_telegram_sell_is_sized_to_holding(trading):
    from sqlalchemy import select
    from app.models.models import TradeProposal

    async with trading["factory"]() as session:
        code, _ = await telegram_trade.issue_link_code(session, trading["user"])
        await telegram_trade.consume_link_code(session, code, "5550012")

        _text, markup = await telegram_trade.handle_callback(
            session, "5550012", "pt:0:INFY:B"
        )
        assert markup is not None
        await telegram_trade.handle_callback(
            session, "5550012", markup["inline_keyboard"][0][0]["callback_data"]
        )
        orders = await broker.list_orders(session, trading["user"])
        held = orders[0].filled_quantity
        assert held > 0

        user = (
            await session.execute(select(User).where(User.id == trading["user"].id))
        ).scalar_one()
        keyboard = await telegram_trade.trade_keyboard(
            session, user, 0, [{"symbol": "INFY", "impact": "positive", "confidence": 70}]
        )
        assert keyboard is not None
        assert len(keyboard["inline_keyboard"][0]) == 2
        assert keyboard["inline_keyboard"][0][1]["callback_data"] == "pt:0:INFY:S"

        _sell_text, sell_markup = await telegram_trade.handle_callback(
            session, "5550012", "pt:0:INFY:S"
        )
        assert sell_markup is not None
        proposal_id = int(sell_markup["inline_keyboard"][0][0]["callback_data"].split(":")[1])
        proposal = (
            await session.execute(
                select(TradeProposal).where(TradeProposal.id == proposal_id)
            )
        ).scalar_one()
        assert proposal.side == "SELL"
        assert proposal.quantity == held


async def test_bot_link_and_portfolio_commands(trading, monkeypatch):
    from app.services.notifications import bot_subscribers as bot

    sent: list[tuple[str, str, dict | None]] = []

    async def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    monkeypatch.setattr(bot, "_send", fake_send)

    def message(text: str, chat_type: str = "private", chat_id: int = 4242) -> dict:
        return {
            "update_id": 1,
            "message": {
                "chat": {"id": chat_id, "type": chat_type},
                "text": text,
            },
        }

    async with trading["factory"]() as session:
        code, _ = await telegram_trade.issue_link_code(session, trading["user"])
        await bot.handle_update(session, message(f"/link {code}"))
        assert "Linked to your Sunrise account" in sent[-1][1]

        await bot.handle_update(session, message("/portfolio"))
        assert "PAPER PORTFOLIO" in sent[-1][1]

        await bot.handle_update(session, message("/status"))
        assert "Telegram trading: linked" in sent[-1][1]


async def test_bot_refuses_link_from_group_chat(trading, monkeypatch):
    from app.services.notifications import bot_subscribers as bot

    sent: list[str] = []

    async def fake_send(chat_id, text, reply_markup=None):
        sent.append(text)

    monkeypatch.setattr(bot, "_send", fake_send)
    async with trading["factory"]() as session:
        code, _ = await telegram_trade.issue_link_code(session, trading["user"])
        await bot.handle_update(
            session,
            {
                "update_id": 2,
                "message": {
                    "chat": {"id": -100123, "type": "group"},
                    "text": f"/link {code}",
                },
            },
        )
        linked = await telegram_trade.get_user_by_chat(session, "-100123")
    assert "private chat" in sent[-1]
    assert linked is None


async def test_bot_callback_is_private_chat_only(trading, monkeypatch):
    from app.services.notifications import bot_subscribers as bot

    calls: list[tuple[str, dict]] = []

    async def fake_tg_call(client, method, payload=None):
        calls.append((method, payload or {}))
        return {"ok": True}

    monkeypatch.setattr(bot, "_tg_call", fake_tg_call)
    async with trading["factory"]() as session:
        await bot.handle_update(
            session,
            {
                "update_id": 3,
                "callback_query": {
                    "id": "cb-1",
                    "data": "pt:0:INFY:B",
                    "message": {"chat": {"id": -100123, "type": "group"}},
                },
            },
        )
    sent = [payload for method, payload in calls if method == "sendMessage"]
    assert sent and "private chat" in sent[0]["text"]
    assert any(method == "answerCallbackQuery" for method, _ in calls)


async def test_linking_carries_subscriber_filters(trading):
    from sqlalchemy import select
    from app.models.models import User, UserPreference

    async with trading["factory"]() as session:
        subscriber = User(
            email="telegram-5550020@subscribers.sunrise.local",
            telegram_chat_id="5550020",
        )
        session.add(subscriber)
        await session.flush()
        session.add(
            UserPreference(
                user_id=subscriber.id,
                minimum_urgency=85,
                asset_preferences=["INFY"],
                category_preferences=["stocks"],
                email_enabled=False,
                telegram_enabled=True,
            )
        )
        await session.commit()

        code, _ = await telegram_trade.issue_link_code(session, trading["user"])
        linked, error = await telegram_trade.consume_link_code(session, code, "5550020")
        assert error == "" and linked is not None

        pref = (
            await session.execute(
                select(UserPreference).where(
                    UserPreference.user_id == trading["user"].id
                )
            )
        ).scalar_one()
        assert pref.minimum_urgency == 85
        assert pref.asset_preferences == ["INFY"]
        assert pref.category_preferences == ["stocks"]

        stale = (
            await session.execute(select(User).where(User.id == subscriber.id))
        ).scalar_one()
        assert stale.telegram_chat_id is None


async def test_expired_telegram_link_code_is_rejected(trading, monkeypatch):
    monkeypatch.setattr(get_settings(), "paper_telegram_link_ttl_seconds", -1)
    async with trading["factory"]() as session:
        code, _ = await telegram_trade.issue_link_code(session, trading["user"])
        user, error = await telegram_trade.consume_link_code(session, code, "5550030")
    assert user is None
    assert "expired" in error.lower()


async def test_telegram_trading_respects_freeze(trading, monkeypatch):
    monkeypatch.setattr(get_settings(), "paper_trading_frozen", True)
    async with trading["factory"]() as session:
        code, _ = await telegram_trade.issue_link_code(session, trading["user"])
        await telegram_trade.consume_link_code(session, code, "5550031")
        text, markup = await telegram_trade.handle_callback(
            session, "5550031", "pt:0:INFY:B"
        )
    assert markup is None
    assert "closed" in text.lower()
