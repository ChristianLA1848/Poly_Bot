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
        spread=round(ask - bid, 6),
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
        up_book=_book("up", round(up_ask - 0.02, 6), up_ask),
        down_book=_book("down", round(down_ask - 0.02, 6), down_ask),
        now=now,
    )


def test_baseline_strategy_buys_up_when_price_above_reference():
    decision = load_strategy("baseline_momentum").decide(_context())

    assert decision.action == DecisionAction.BUY_UP
    assert decision.token_id == "up"
    assert decision.target_price == 0.62
    assert decision.confidence > 0.5


def test_strategy_registry_lists_available_strategies():
    from polybot.strategies.base import list_strategy_metadata

    metadata = {item.name: item for item in list_strategy_metadata()}

    assert metadata["baseline_momentum"].label == "Baseline Momentum"
    assert metadata["late_window_5m"].market_profiles == ("btc_5m",)
    assert metadata["trend_following"].market_profiles == ("longer_crypto",)


def test_trend_following_rejects_btc_5m_market():
    decision = load_strategy("trend_following").decide(_context())

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason_code == "trend_not_supported_for_market"


def test_trend_following_rejects_unsupported_all_crypto_market():
    now = datetime(2026, 5, 12, 21, 0, tzinfo=UTC)
    market = Market(
        "m",
        "Weather Up or Down",
        "weather-updown-1h",
        "up",
        "down",
        now,
        now + timedelta(hours=1),
        0.01,
        5.0,
        True,
    )

    decision = load_strategy("trend_following").decide(
        _context(
            market=market,
            reference=100.0,
            price=102.0,
            now=now + timedelta(minutes=10),
            up_ask=0.50,
        )
    )

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason_code == "trend_not_supported_for_market"


def test_trend_following_rejects_longer_market_without_start_time():
    now = datetime(2026, 5, 12, 21, 0, tzinfo=UTC)
    market = Market(
        "m",
        "Bitcoin Up or Down - 1h",
        "btc-updown-1h",
        "up",
        "down",
        None,
        now + timedelta(hours=1),
        0.01,
        5.0,
        True,
    )

    decision = load_strategy("trend_following").decide(
        _context(
            market=market,
            reference=100.0,
            price=102.0,
            now=now,
            up_ask=0.50,
        )
    )

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason_code == "trend_history_too_short"


def test_trend_following_buys_up_on_longer_market_momentum():
    now = datetime(2026, 5, 12, 21, 0, tzinfo=UTC)
    market = Market(
        "m",
        "Bitcoin Up or Down - 1h",
        "btc-updown-1h",
        "up",
        "down",
        now,
        now + timedelta(hours=1),
        0.01,
        5.0,
        True,
    )

    decision = load_strategy("trend_following").decide(
        _context(
            market=market,
            reference=100.0,
            price=101.5,
            now=now + timedelta(minutes=10),
            up_ask=0.58,
        )
    )

    assert decision.action == DecisionAction.BUY_UP
    assert decision.reason_code == "trend_confirmed"
    assert decision.edge is not None
    assert decision.edge > 0


def test_late_window_alias_loads_late_window_5m_strategy():
    strategy = load_strategy("late_window")

    assert strategy.name == "late_window_5m"


def test_late_window_5m_rejects_missing_target_price():
    context = _context(reference=0.0, now=datetime(2026, 5, 12, 21, 4, 20, tzinfo=UTC))

    decision = load_strategy("late_window_5m").decide(context)

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason_code == "target_missing"


def test_late_window_5m_rejects_non_btc_5m_market():
    now = datetime(2026, 5, 12, 21, 0, tzinfo=UTC)
    market = Market(
        "m",
        "Bitcoin Up or Down - 1h",
        "btc-updown-1h",
        "up",
        "down",
        now,
        now + timedelta(hours=1),
        0.01,
        5.0,
        True,
    )

    decision = load_strategy("late_window_5m").decide(
        _context(market=market, now=now + timedelta(minutes=55))
    )

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason_code == "strategy_not_supported"


def test_late_window_5m_buys_up_with_reason_code_and_edge():
    decision = load_strategy("late_window_5m").decide(
        _context(
            reference=100.0,
            price=100.2,
            now=datetime(2026, 5, 12, 21, 4, 20, tzinfo=UTC),
            up_ask=0.84,
        )
    )

    assert decision.action == DecisionAction.BUY_UP
    assert decision.reason_code == "late_window_high_confidence"
    assert decision.market_probability == 0.84
    assert decision.edge == pytest.approx(decision.estimated_probability - 0.84)


def test_strategy_decision_includes_reason_code_and_edge_fields():
    decision = load_strategy("baseline_momentum").decide(_context())

    assert decision.reason_code == "momentum_up"
    assert decision.market_probability == 0.62
    assert decision.edge == pytest.approx(decision.estimated_probability - 0.62)
    assert decision.to_dict()["reason_code"] == "momentum_up"
    assert "edge" in decision.to_dict()


def test_baseline_strategy_skips_small_delta():
    decision = load_strategy("baseline_momentum").decide(_context(price=100.04))

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason == "price delta too small"


def test_baseline_strategy_trades_at_exact_delta_threshold():
    decision = load_strategy("baseline_momentum").decide(
        _context(reference=125.0, price=125.0625)
    )

    assert decision.action == DecisionAction.BUY_UP
    assert decision.reason == "btc delta 0.00050"


@pytest.mark.parametrize("reference", [0.0, -100.0])
def test_baseline_strategy_skips_non_positive_reference(reference):
    decision = load_strategy("baseline_momentum").decide(
        _context(reference=reference, price=101.0)
    )

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason == "reference start price must be positive"


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


def test_late_window_strategy_marks_sub_minimum_remaining_time_too_late():
    decision = load_strategy("late_window").decide(
        _context(now=datetime(2026, 5, 12, 21, 4, 50, tzinfo=UTC))
    )

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason == "too close to resolution"
    assert decision.reason_code == "too_late"


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


def test_strategy_context_builds_market_snapshot():
    now = datetime(2026, 5, 12, 21, 4, 20, tzinfo=UTC)
    market = _market(end_offset=timedelta(minutes=5))
    context = _context(
        price=100.25,
        reference=100.0,
        market=market,
        now=now,
        up_ask=0.84,
        down_ask=0.18,
    )

    snapshot = context.snapshot

    assert snapshot.market_profile == "btc_5m"
    assert snapshot.seconds_remaining == 40.0
    assert snapshot.window_seconds == 300.0
    assert snapshot.target_price == 100.0
    assert snapshot.btc_price == 100.25
    assert snapshot.delta == 0.25
    assert snapshot.delta_pct == 0.25
    assert snapshot.up_ask == 0.84
    assert snapshot.down_ask == 0.18
    assert snapshot.max_spread == 0.02
    assert snapshot.feed_fresh is True
    assert snapshot.source_count == 1


def test_late_window_strategy_buys_down_inside_return_band():
    market = _market(end_offset=timedelta(minutes=5))
    decision = load_strategy("late_window").decide(
        _context(
            price=99.8,
            market=market,
            now=datetime(2026, 5, 12, 21, 4, 20, tzinfo=UTC),
            down_ask=0.84,
        )
    )

    assert decision.action == DecisionAction.BUY_DOWN
    assert decision.token_id == "down"
    assert 0.01 <= decision.expected_return <= 0.10


def test_late_window_strategy_trades_at_exact_delta_threshold():
    market = _market(end_offset=timedelta(minutes=5))
    decision = load_strategy("late_window").decide(
        _context(
            reference=4125.0,
            price=4129.125,
            market=market,
            now=datetime(2026, 5, 12, 21, 4, 20, tzinfo=UTC),
            up_ask=0.80,
        )
    )

    assert decision.action == DecisionAction.BUY_UP
    assert decision.reason == "late-window probability and return accepted"


@pytest.mark.parametrize(
    ("now", "seconds_remaining"),
    [
        (datetime(2026, 5, 12, 21, 4, tzinfo=UTC), 60),
        (datetime(2026, 5, 12, 21, 4, 40, tzinfo=UTC), 20),
    ],
)
def test_late_window_strategy_trades_at_window_boundaries(
    now: datetime,
    seconds_remaining: int,
):
    market = _market(end_offset=timedelta(minutes=5))
    decision = load_strategy("late_window").decide(
        _context(price=100.2, market=market, now=now, up_ask=0.84)
    )

    assert (market.end_time - now).total_seconds() == seconds_remaining
    assert decision.action == DecisionAction.BUY_UP


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


@pytest.mark.parametrize("reference", [0.0, -100.0])
def test_late_window_strategy_skips_non_positive_reference(reference):
    market = _market(end_offset=timedelta(minutes=5))
    decision = load_strategy("late_window").decide(
        _context(
            reference=reference,
            price=101.0,
            market=market,
            now=datetime(2026, 5, 12, 21, 4, 20, tzinfo=UTC),
        )
    )

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason == "target price missing"
    assert decision.reason_code == "target_missing"


def test_load_strategy_rejects_unknown_name():
    with pytest.raises(ValueError, match="Unknown strategy: unknown"):
        load_strategy("unknown")
