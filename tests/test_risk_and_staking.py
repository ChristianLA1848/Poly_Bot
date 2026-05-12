from datetime import UTC, datetime

import pytest

from polybot.config import RiskSection, StakingSection
from polybot.models import Decision, DecisionAction, FeedAggregate, FeedPrice, OrderbookSnapshot
from polybot.risk import RiskGate, RiskResult
from polybot.staking import calculate_stake


def _risk_config() -> RiskSection:
    return RiskSection(
        max_stake=20.0,
        max_daily_loss=25.0,
        max_spread=0.04,
        min_liquidity=100.0,
        min_edge=0.03,
        max_feed_age_ms=2500,
        max_feed_deviation_bps=20,
        max_open_positions=2,
        max_open_orders=3,
    )


def _feed(*, fresh: bool = True, max_deviation_bps: float = 10.0) -> FeedAggregate:
    now = datetime(2026, 5, 12, 21, 3, tzinfo=UTC)
    return FeedAggregate(
        reference_price=100.0,
        prices=[FeedPrice("coinbase", "BTC", 100.0, 1)],
        max_deviation_bps=max_deviation_bps,
        fresh=fresh,
        created_at=now,
    )


def _book(
    *,
    spread: float = 0.02,
    bid_size: float = 150.0,
    ask_size: float = 150.0,
) -> OrderbookSnapshot:
    return OrderbookSnapshot(
        market_id="0xabc",
        token_id="up",
        best_bid=0.58,
        best_ask=0.60,
        spread=spread,
        bid_size=bid_size,
        ask_size=ask_size,
        timestamp_ms=1,
    )


def _decision(
    *,
    action: DecisionAction = DecisionAction.BUY_UP,
    target_price: float = 0.60,
    estimated_probability: float = 0.66,
    confidence: float = 0.72,
) -> Decision:
    return Decision(
        strategy="baseline_momentum",
        action=action,
        market_id="0xabc",
        token_id="up",
        target_price=target_price,
        estimated_probability=estimated_probability,
        confidence=confidence,
        expected_return=estimated_probability / target_price - 1,
        max_slippage=0.01,
        reason="accepted",
        created_at=datetime(2026, 5, 12, 21, 3, tzinfo=UTC),
    )


def _evaluate(
    *,
    config: RiskSection | None = None,
    decision: Decision | None = None,
    feed: FeedAggregate | None = None,
    book: OrderbookSnapshot | None = None,
    today_pnl: float = 0.0,
    open_positions: int = 0,
    open_orders: int = 0,
) -> RiskResult:
    return RiskGate(config or _risk_config()).evaluate(
        decision or _decision(),
        feed or _feed(),
        book or _book(),
        today_pnl=today_pnl,
        open_positions=open_positions,
        open_orders=open_orders,
    )


def test_risk_gate_accepts_clean_trade():
    assert _evaluate() == RiskResult(accepted=True, reason="accepted")


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"decision": _decision(action=DecisionAction.NO_TRADE)}, "strategy returned no trade"),
        ({"feed": _feed(fresh=False)}, "feed stale"),
        ({"feed": _feed(max_deviation_bps=21.0)}, "feed deviation too high"),
        ({"book": _book(spread=0.05)}, "spread too high"),
        ({"book": _book(bid_size=99.0)}, "liquidity too low"),
        ({"book": _book(ask_size=99.0)}, "liquidity too low"),
        ({"decision": _decision(estimated_probability=0.629)}, "edge too low"),
        ({"today_pnl": -25.0}, "daily loss limit hit"),
        ({"today_pnl": -30.0}, "daily loss limit hit"),
        ({"open_positions": 2}, "too many open positions"),
        ({"open_orders": 3}, "too many open orders"),
    ],
)
def test_risk_gate_blocks_rejected_trade_reasons(kwargs, reason):
    assert _evaluate(**kwargs) == RiskResult(accepted=False, reason=reason)


def test_risk_gate_allows_exact_thresholds_before_position_order_limits():
    result = _evaluate(
        feed=_feed(max_deviation_bps=20.0),
        book=_book(spread=0.04, bid_size=100.0, ask_size=100.0),
        decision=_decision(estimated_probability=0.63),
        today_pnl=-24.99,
        open_positions=1,
        open_orders=2,
    )

    assert result.accepted is True


def test_fixed_stake_is_capped():
    config = StakingSection(mode="fixed", fixed_stake=12.0)

    assert calculate_stake(config, _decision(), max_stake=8.0) == 8.0


def test_fixed_stake_can_be_below_cap():
    config = StakingSection(mode="fixed", fixed_stake=6.0)

    assert calculate_stake(config, _decision(), max_stake=8.0) == 6.0


def test_fractional_kelly_stake_is_capped_and_rounded():
    config = StakingSection(mode="fractional_kelly", kelly_fraction=1.0)
    decision = _decision(target_price=0.01, estimated_probability=1.0)

    assert calculate_stake(config, decision, max_stake=10.0) == 10.0


def test_fractional_kelly_stake_rounds_to_two_decimals():
    config = StakingSection(mode="fractional_kelly", kelly_fraction=0.25)
    decision = _decision(target_price=0.60, estimated_probability=0.70)

    assert calculate_stake(config, decision, max_stake=10.0) == 0.62


def test_fractional_kelly_returns_zero_when_no_positive_edge():
    config = StakingSection(mode="fractional_kelly", kelly_fraction=0.5)
    decision = _decision(target_price=0.60, estimated_probability=0.50)

    assert calculate_stake(config, decision, max_stake=10.0) == 0.0


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (0.80, 9.0),
        (0.79, 5.0),
        (0.65, 5.0),
        (0.64, 2.0),
    ],
)
def test_confidence_tiering_selects_stake_by_confidence(confidence, expected):
    config = StakingSection(
        mode="confidence_tiering",
        low_confidence_stake=2.0,
        medium_confidence_stake=5.0,
        high_confidence_stake=9.0,
    )

    assert (
        calculate_stake(config, _decision(confidence=confidence), max_stake=20.0)
        == expected
    )


def test_confidence_tiering_caps_selected_stake():
    config = StakingSection(mode="confidence_tiering", high_confidence_stake=9.0)

    assert calculate_stake(config, _decision(confidence=0.90), max_stake=4.0) == 4.0


def test_unknown_staking_mode_raises_value_error():
    config = StakingSection.model_construct(mode="mystery")

    with pytest.raises(ValueError, match="Unknown staking mode: mystery"):
        calculate_stake(config, _decision(), max_stake=10.0)
