from datetime import UTC, datetime, timedelta
import json

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
from polybot.models import (
    Decision,
    DecisionAction,
    FeedAggregate,
    FeedPrice,
    Market,
    OrderbookSnapshot,
    PaperTrade,
)


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


class FailingOrderbookClient:
    async def get_book(self, token_id: str) -> OrderbookSnapshot:
        raise ValueError("orderbook has no bid levels")


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
            "mode": "paper",
            "status": "filled",
            "shares": stake / decision.target_price,
            "stake": stake,
            "price": decision.target_price,
            "token_id": decision.token_id,
            "market_id": decision.market_id,
        }

    async def cancel_all(self):
        return {"status": "cancelled"}


class FakeLiveExecution:
    def __init__(self) -> None:
        self.orders = []

    async def place_order(self, decision, stake):
        self.orders.append((decision, stake))
        return {
            "status": "submitted",
            "market_id": decision.market_id,
            "token_id": decision.token_id,
            "stake": stake,
            "price": decision.target_price,
            "shares": 0,
        }


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
            max_open_positions=10,
        ),
        strategy=StrategySection(name="baseline_momentum"),
        staking=StakingSection(mode="fixed", fixed_stake=5),
        exit=ExitSection(mode="hold_to_resolution"),
        late_window=LateWindowSection(),
    )


def _live_config() -> BotConfig:
    config = _config()
    config.bot.mode = "live"
    return config


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
async def test_bot_runner_blocks_second_trade_in_same_event(tmp_path):
    execution = FakeExecution()
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FakeOrderbookClient(),
        execution=execution,
        store_path=tmp_path / "bot.sqlite3",
        reference_start_price=100.0,
        latest_feed=_feed(),
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))
    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, 30, tzinfo=UTC))

    snapshot = runner.store.dashboard_snapshot()
    assert len(execution.orders) == 1
    assert snapshot["recent_events"][0]["message"] == (
        "risk gate blocked: event_trade_limit_reached"
    )


@pytest.mark.asyncio
async def test_bot_runner_live_mode_ignores_existing_paper_event_trade_limit(tmp_path):
    execution = FakeLiveExecution()
    runner = BotRunner(
        config=_live_config(),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FakeOrderbookClient(),
        execution=execution,
        store_path=tmp_path / "bot.sqlite3",
        reference_start_price=100.0,
        latest_feed=_feed(),
    )
    runner.store.record_paper_trade(
        PaperTrade(
            id=None,
            created_at=datetime(2026, 5, 12, 21, 1, tzinfo=UTC),
            event_slug="slug",
            market_id="m",
            token_id="up",
            action=DecisionAction.BUY_UP.value,
            strategy="test",
            reason_code="seed",
            stake=5,
            price=0.50,
            shares=10,
            status="filled",
            estimated_probability=0.60,
            market_probability=0.50,
            edge=0.10,
            target_price=100.0,
            btc_price_at_entry=101.0,
            event_end_time=datetime(2026, 5, 12, 21, 5, tzinfo=UTC),
        )
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    assert len(execution.orders) == 1
    decision, stake = execution.orders[0]
    assert decision.token_id == "up"
    assert stake == 5


@pytest.mark.asyncio
async def test_bot_runner_allows_trade_in_different_event(tmp_path):
    now = datetime(2026, 5, 12, 21, 0, tzinfo=UTC)
    first_market = Market(
        "m1",
        "Bitcoin Up or Down",
        "slug-1",
        "up",
        "down",
        now,
        now + timedelta(minutes=5),
        0.01,
        5.0,
        True,
    )
    second_market = Market(
        "m2",
        "Bitcoin Up or Down",
        "slug-2",
        "up",
        "down",
        now + timedelta(minutes=5),
        now + timedelta(minutes=10),
        0.01,
        5.0,
        True,
    )
    market_discovery = FakeMarketDiscovery(market=first_market)
    execution = FakeExecution()
    runner = BotRunner(
        config=_config(),
        market_discovery=market_discovery,
        orderbook_client=FakeOrderbookClient(),
        execution=execution,
        store_path=tmp_path / "bot.sqlite3",
        reference_start_price=100.0,
        latest_feed=_feed(),
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))
    market_discovery.market = second_market
    runner.latest_feed = _feed()
    await runner.run_once(now=datetime(2026, 5, 12, 21, 8, tzinfo=UTC))

    assert len(execution.orders) == 2


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
async def test_bot_runner_writes_audit_records_for_order_path(tmp_path):
    execution = FakeExecution()
    audit_path = tmp_path / "audit.jsonl"
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FakeOrderbookClient(),
        execution=execution,
        store_path=tmp_path / "bot.sqlite3",
        reference_start_price=100.0,
        latest_feed=_feed(),
        audit_log_path=audit_path,
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [record["type"] for record in records] == ["decision", "order_result"]
    assert records[0]["payload"]["decision"]["action"] == "BUY_UP"
    assert records[0]["payload"]["snapshot"]["seconds_remaining"] == 120.0
    assert records[0]["payload"]["up_book"]["token_id"] == "up"
    assert records[0]["payload"]["down_book"]["token_id"] == "down"
    assert records[1]["payload"]["result"]["status"] == "filled"
    assert records[1]["payload"]["stake"] == 5


@pytest.mark.asyncio
async def test_bot_runner_writes_audit_records_for_risk_block_and_warning(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    blocked_runner = BotRunner(
        config=_config(max_spread=0.001),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FakeOrderbookClient(spread=0.02),
        execution=FakeExecution(),
        store_path=tmp_path / "blocked.sqlite3",
        reference_start_price=100.0,
        latest_feed=_feed(),
        audit_log_path=audit_path,
    )
    warning_runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FakeOrderbookClient(),
        execution=FakeExecution(),
        store_path=tmp_path / "warning.sqlite3",
        audit_log_path=audit_path,
    )

    await blocked_runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))
    await warning_runner.run_once(now=datetime(2026, 5, 12, 21, 4, tzinfo=UTC))

    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [record["type"] for record in records] == [
        "decision",
        "risk_block",
        "event",
    ]
    assert records[1]["payload"]["reason"] == "spread too high"
    assert records[1]["payload"]["snapshot"]["market_profile"] == "btc_5m"
    assert records[1]["payload"]["up_book"]["spread"] == 0.02
    assert records[1]["payload"]["down_book"]["spread"] == 0.02
    assert records[2]["payload"]["event"]["level"] == "warning"
    assert records[2]["payload"]["event"]["message"] == "no feed aggregate available"


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
    assert runner.store.dashboard_snapshot()["market_status"]["state"] == "not_found"


@pytest.mark.asyncio
async def test_bot_runner_evaluates_open_paper_trades(tmp_path):
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(market=None),
        orderbook_client=FakeOrderbookClient(),
        execution=FakeExecution(),
        store_path=tmp_path / "bot.sqlite3",
        latest_feed=_feed(),
    )
    end_time = datetime(2026, 5, 12, 21, 1, tzinfo=UTC)
    runner.store.record_paper_trade(
        PaperTrade(
            None,
            datetime(2026, 5, 12, 21, 0, tzinfo=UTC),
            "old-slug",
            "m",
            "up",
            "BUY_UP",
            "baseline_momentum",
            "momentum_up",
            5.0,
            0.5,
            10.0,
            "filled",
            0.7,
            0.5,
            0.2,
            100.0,
            100.5,
            end_time,
        )
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    assert runner.store.list_paper_trades()[0]["outcome"] == "win"


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
    snapshot = runner.store.dashboard_snapshot()
    assert snapshot["recent_events"][0]["message"] == "market not accepting orders"
    assert snapshot["market_status"]["state"] == "not_accepting_orders"
    assert snapshot["market_status"]["slug"] == "slug"
    assert snapshot["feed_status"]["btc_price"] == 101.0
    assert snapshot["feed_status"]["target_price"] is None


@pytest.mark.asyncio
async def test_bot_runner_records_ready_market_status_before_deciding(tmp_path):
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FakeOrderbookClient(),
        execution=FakeExecution(),
        store_path=tmp_path / "bot.sqlite3",
        reference_start_price=100.0,
        latest_feed=_feed(),
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    assert runner.store.dashboard_snapshot()["market_status"]["state"] == "ready"


@pytest.mark.asyncio
async def test_bot_runner_records_warning_when_orderbook_unavailable(tmp_path):
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FailingOrderbookClient(),
        execution=FakeExecution(),
        store_path=tmp_path / "bot.sqlite3",
        reference_start_price=100.0,
        latest_feed=_feed(),
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    snapshot = runner.store.dashboard_snapshot()
    assert snapshot["recent_events"][0] == {
        "created_at": "2026-05-12T21:03:00+00:00",
        "level": "warning",
        "message": "orderbook unavailable: orderbook has no bid levels",
    }


@pytest.mark.asyncio
async def test_bot_runner_records_feed_and_target_status(tmp_path):
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FakeOrderbookClient(),
        execution=FakeExecution(),
        store_path=tmp_path / "bot.sqlite3",
        reference_start_price=100.0,
        latest_feed=_feed(),
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    assert runner.store.dashboard_snapshot()["feed_status"] == {
        "btc_price": 101.0,
        "fresh": True,
        "max_deviation_bps": 0,
        "created_at": "2026-05-12T21:03:00+00:00",
        "target_price": 100.0,
        "delta": 1.0,
        "delta_pct": 1.0,
    }


@pytest.mark.asyncio
async def test_bot_runner_uses_market_price_to_beat_as_target(tmp_path):
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
        True,
        99.5,
    )
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(market=market),
        orderbook_client=FakeOrderbookClient(),
        execution=FakeExecution(),
        store_path=tmp_path / "bot.sqlite3",
        latest_feed=_feed(),
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    assert runner.reference_start_price == 99.5
    assert runner.store.dashboard_snapshot()["feed_status"]["target_price"] == 99.5


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
        lambda name, late_window=None: StaticStrategy(_trade_decision("unknown-token")),
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
