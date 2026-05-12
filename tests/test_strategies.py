from datetime import UTC, datetime, timedelta

import pytest

from polybot.models import (
    DecisionAction,
    FeedAggregate,
    FeedPrice,
    Market,
    OrderbookSnapshot,
)
from polybot.strategies.base import StrategyContext, load_strategy


def _market(end_offset: timedelta = timedelta(minutes=5)) -> Market:
    now = datetime(2026, 5, 12, 21, 0, tzinfo=UTC)
    return Market(
        market_id="0xabc",
        question="Bitcoin Up or Down",
        slug="btc-up-down",
        up_token_id="up",
        down_token_id="down",
        start_time=now,
        end_time=now + end_offset,
        tick_size=0.01,
        min_size=5.0,
        accepting_orders=True,
    )


def _aggregate(price: float) -> FeedAggregate:
    now = datetime(2026, 5, 12, 21, 3, tzinfo=UTC)
    return FeedAggregate(price, [FeedPrice("a", "btc", price, 1)], 0.0, True, now)


def _book(token_id: str, bid: float, ask: float) -> OrderbookSnapshot:
    return OrderbookSnapshot(
        market_id="0xabc",
        token_id=token_id,
        best_bid=bid,
        best_ask=ask,
        spread=ask - bid,
        bid_size=200.0,
        ask_size=200.0,
        timestamp_ms=1,
    )


def _context(
    *,
    price: float = 101.0,
    reference: float = 100.0,
    now: datetime = datetime(2026, 5, 12, 21, 3, tzinfo=UTC),
    market: Market | None = None,
    up_ask: float = 0.62,
    down_ask: float = 0.40,
) -> StrategyContext:
    return StrategyContext(
        market=market or _market(),
        reference_start_price=reference,
        feed=_aggregate(price),
        up_book=_book("up", 0.60, up_ask),
        down_book=_book("down", 0.38, down_ask),
        now=now,
    )


def test_baseline_strategy_buys_up_when_price_above_reference():
    decision = load_strategy("baseline_momentum").decide(_context())

    assert decision.action == DecisionAction.BUY_UP
    assert decision.token_id == "up"
    assert decision.target_price == 0.62
    assert decision.confidence > 0.5


def test_baseline_strategy_skips_small_delta():
    decision = load_strategy("baseline_momentum").decide(_context(price=100.04))

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason == "price delta too small"


def test_baseline_strategy_buys_down_when_price_below_reference():
    decision = load_strategy("baseline_momentum").decide(_context(price=99.0))

    assert decision.action == DecisionAction.BUY_DOWN
    assert decision.token_id == "down"
    assert decision.target_price == 0.40
    assert decision.expected_return > 0


def test_late_window_strategy_waits_outside_window():
    decision = load_strategy("late_window").decide(
        _context(
            market=_market(),
            now=datetime(2026, 5, 12, 21, 1, tzinfo=UTC),
            up_ask=0.94,
            down_ask=0.08,
        )
    )

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason == "outside late window"


def test_late_window_strategy_accepts_trade_inside_return_band():
    market = _market(end_offset=timedelta(minutes=5))
    decision = load_strategy("late_window").decide(
        _context(
            price=100.2,
            market=market,
            now=datetime(2026, 5, 12, 21, 4, 20, tzinfo=UTC),
            up_ask=0.84,
        )
    )

    assert decision.action == DecisionAction.BUY_UP
    assert decision.token_id == "up"
    assert 0.01 <= decision.expected_return <= 0.10
    assert decision.max_slippage == 0.005


def test_late_window_strategy_skips_small_delta_inside_window():
    market = _market(end_offset=timedelta(minutes=5))
    decision = load_strategy("late_window").decide(
        _context(
            price=100.05,
            market=market,
            now=datetime(2026, 5, 12, 21, 4, 20, tzinfo=UTC),
        )
    )

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason == "late window edge too small"


def test_late_window_strategy_skips_return_outside_band():
    market = _market(end_offset=timedelta(minutes=5))
    decision = load_strategy("late_window").decide(
        _context(
            price=101.0,
            market=market,
            now=datetime(2026, 5, 12, 21, 4, 20, tzinfo=UTC),
            up_ask=0.70,
        )
    )

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason == "expected return outside late-window band"


def test_load_strategy_rejects_unknown_name():
    with pytest.raises(ValueError, match="Unknown strategy: unknown"):
        load_strategy("unknown")
