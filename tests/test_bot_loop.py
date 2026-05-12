from datetime import UTC, datetime, timedelta

import pytest

from polybot.bot import BotRunner
from polybot.config import (
    BotConfig,
    BotSection,
    ExitSection,
    LateWindowSection,
    RiskSection,
    StakingSection,
    StrategySection,
)
from polybot.models import Decision, DecisionAction, FeedAggregate, FeedPrice, Market, OrderbookSnapshot


DEFAULT_MARKET = object()


class FakeMarketDiscovery:
    def __init__(self, market: Market | None | object = DEFAULT_MARKET) -> None:
        now = datetime(2026, 5, 12, 21, 0, tzinfo=UTC)
        self.market = (
            Market(
                "m",
                "Bitcoin Up or Down",
                "slug",
                "up",
                "down",
                now,
                now + timedelta(minutes=5),
                0.01,
                5.0,
                True,
            )
            if market is DEFAULT_MARKET
            else market
        )

    async def find_btc_5m_market(self) -> Market | None:
        return self.market


class CloseableFakeMarketDiscovery(FakeMarketDiscovery):
    def __init__(self, market: Market | None = None) -> None:
        super().__init__(market)
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeOrderbookClient:
    def __init__(self, *, spread: float = 0.01) -> None:
        self.spread = spread

    async def get_book(self, token_id: str) -> OrderbookSnapshot:
        return OrderbookSnapshot("m", token_id, 0.49, 0.49 + self.spread, self.spread, 200, 200, 1)


class CloseableFakeOrderbookClient(FakeOrderbookClient):
    def __init__(self, *, spread: float = 0.01) -> None:
        super().__init__(spread=spread)
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeExecution:
    def __init__(self) -> None:
        self.orders = []

    async def place_order(self, decision, stake):
        self.orders.append((decision, stake))
        return {
            "status": "filled",
            "shares": stake / decision.target_price,
            "stake": stake,
            "price": decision.target_price,
            "token_id": decision.token_id,
            "market_id": decision.market_id,
        }

    async def cancel_all(self):
        return {"status": "cancelled"}


def _config(max_spread: float = 0.04) -> BotConfig:
    return BotConfig(
        bot=BotSection(mode="paper", cycle_seconds=1),
        risk=RiskSection(
            max_stake=10,
            max_daily_loss=25,
            max_spread=max_spread,
            min_liquidity=100,
            min_edge=0.03,
            max_feed_age_ms=2500,
            max_feed_deviation_bps=20,
        ),
        strategy=StrategySection(name="baseline_momentum"),
        staking=StakingSection(mode="fixed", fixed_stake=5),
        exit=ExitSection(mode="hold_to_resolution"),
        late_window=LateWindowSection(),
    )


def _feed() -> FeedAggregate:
    return FeedAggregate(
        101.0,
        [FeedPrice("a", "btc", 101.0, 1)],
        0,
        True,
        datetime(2026, 5, 12, 21, 3, tzinfo=UTC),
    )


def _trade_decision(token_id: str) -> Decision:
    return Decision(
        strategy="test",
        action=DecisionAction.BUY_UP,
        market_id="m",
        token_id=token_id,
        target_price=0.50,
        estimated_probability=0.60,
        confidence=0.75,
        expected_return=0.10,
        max_slippage=0.005,
        reason="test strategy",
        created_at=datetime(2026, 5, 12, 21, 3, tzinfo=UTC),
    )


class StaticStrategy:
    name = "test"

    def __init__(self, decision: Decision) -> None:
        self.decision = decision

    def decide(self, context):
        return self.decision


@pytest.mark.asyncio
async def test_bot_runner_single_cycle_places_paper_order(tmp_path):
    execution = FakeExecution()
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FakeOrderbookClient(),
        execution=execution,
        store_path=tmp_path / "bot.sqlite3",
        reference_start_price=100.0,
    )
    runner.latest_feed = _feed()

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    assert len(execution.orders) == 1
    decision, stake = execution.orders[0]
    assert decision.token_id == "up"
    assert stake == 5
    assert runner.positions.open_positions_count() == 1


@pytest.mark.asyncio
async def test_bot_runner_records_warning_when_feed_missing(tmp_path):
    execution = FakeExecution()
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FakeOrderbookClient(),
        execution=execution,
        store_path=tmp_path / "bot.sqlite3",
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    assert execution.orders == []
    assert runner.store.dashboard_snapshot()["recent_events"][0] == {
        "created_at": "2026-05-12T21:03:00+00:00",
        "level": "warning",
        "message": "no feed aggregate available",
    }


@pytest.mark.asyncio
async def test_bot_runner_records_event_when_risk_gate_blocks(tmp_path):
    execution = FakeExecution()
    runner = BotRunner(
        config=_config(max_spread=0.001),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FakeOrderbookClient(spread=0.02),
        execution=execution,
        store_path=tmp_path / "bot.sqlite3",
        reference_start_price=100.0,
    )
    runner.latest_feed = _feed()

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    assert execution.orders == []
    assert runner.store.dashboard_snapshot()["recent_events"][0]["message"] == (
        "risk gate blocked: spread too high"
    )


@pytest.mark.asyncio
async def test_bot_runner_records_warning_when_market_missing(tmp_path):
    execution = FakeExecution()
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(market=None),
        orderbook_client=FakeOrderbookClient(),
        execution=execution,
        store_path=tmp_path / "bot.sqlite3",
        latest_feed=_feed(),
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    assert execution.orders == []
    assert runner.store.dashboard_snapshot()["recent_events"][0]["message"] == "market not found"


@pytest.mark.asyncio
async def test_bot_runner_records_warning_when_market_not_accepting_orders(tmp_path):
    now = datetime(2026, 5, 12, 21, 0, tzinfo=UTC)
    market = Market(
        "m",
        "Bitcoin Up or Down",
        "slug",
        "up",
        "down",
        now,
        now + timedelta(minutes=5),
        0.01,
        5.0,
        False,
    )
    execution = FakeExecution()
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(market=market),
        orderbook_client=FakeOrderbookClient(),
        execution=execution,
        store_path=tmp_path / "bot.sqlite3",
        latest_feed=_feed(),
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    assert execution.orders == []
    assert runner.store.dashboard_snapshot()["recent_events"][0]["message"] == (
        "market not accepting orders"
    )


@pytest.mark.asyncio
async def test_bot_runner_records_error_when_execution_engine_missing(tmp_path):
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FakeOrderbookClient(),
        execution=None,
        store_path=tmp_path / "bot.sqlite3",
        reference_start_price=100.0,
        latest_feed=_feed(),
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    assert runner.store.dashboard_snapshot()["recent_events"][0]["message"] == (
        "execution engine missing"
    )


@pytest.mark.asyncio
async def test_bot_runner_blocks_unknown_trade_token_before_risk_and_execution(tmp_path, monkeypatch):
    execution = FakeExecution()
    monkeypatch.setattr(
        "polybot.bot.load_strategy",
        lambda name: StaticStrategy(_trade_decision("unknown-token")),
    )
    runner = BotRunner(
        config=_config(max_spread=0.001),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FakeOrderbookClient(spread=0.02),
        execution=execution,
        store_path=tmp_path / "bot.sqlite3",
        reference_start_price=100.0,
        latest_feed=_feed(),
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    assert execution.orders == []
    assert runner.store.dashboard_snapshot()["recent_events"][0] == {
        "created_at": "2026-05-12T21:03:00+00:00",
        "level": "error",
        "message": "strategy returned unknown token",
    }


@pytest.mark.asyncio
async def test_bot_runner_aclose_closes_closeable_clients(tmp_path):
    market_discovery = CloseableFakeMarketDiscovery()
    orderbook_client = CloseableFakeOrderbookClient()
    runner = BotRunner(
        config=_config(),
        market_discovery=market_discovery,
        orderbook_client=orderbook_client,
        execution=FakeExecution(),
        store_path=tmp_path / "bot.sqlite3",
    )

    await runner.aclose()

    assert market_discovery.closed is True
    assert orderbook_client.closed is True


@pytest.mark.asyncio
async def test_bot_runner_async_context_manager_closes_clients(tmp_path):
    market_discovery = CloseableFakeMarketDiscovery()
    orderbook_client = CloseableFakeOrderbookClient()

    async with BotRunner(
        config=_config(),
        market_discovery=market_discovery,
        orderbook_client=orderbook_client,
        execution=FakeExecution(),
        store_path=tmp_path / "bot.sqlite3",
    ):
        assert market_discovery.closed is False
        assert orderbook_client.closed is False

    assert market_discovery.closed is True
    assert orderbook_client.closed is True
