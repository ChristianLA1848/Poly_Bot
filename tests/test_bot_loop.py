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
from polybot.models import FeedAggregate, FeedPrice, Market, OrderbookSnapshot


class FakeMarketDiscovery:
    def __init__(self, market: Market | None = None) -> None:
        now = datetime(2026, 5, 12, 21, 0, tzinfo=UTC)
        self.market = market or Market(
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

    async def find_btc_5m_market(self) -> Market | None:
        return self.market


class FakeOrderbookClient:
    def __init__(self, *, spread: float = 0.01) -> None:
        self.spread = spread

    async def get_book(self, token_id: str) -> OrderbookSnapshot:
        return OrderbookSnapshot("m", token_id, 0.49, 0.49 + self.spread, self.spread, 200, 200, 1)


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
