from polybot.config import LateWindowSection
from polybot.models import Decision, DecisionAction
from polybot.strategies.baseline_momentum import _expected_return, _no_trade
from polybot.strategies.base import StrategyContext


class LateWindow5mStrategy:
    name = "late_window_5m"

    def __init__(self, settings: LateWindowSection | None = None) -> None:
        self.settings = settings or LateWindowSection()

    def decide(self, context: StrategyContext) -> Decision:
        snapshot = context.snapshot
        if snapshot.market_profile != "btc_5m":
            return _no_trade(
                self.name,
                context,
                reason="late-window 5m strategy only supports BTC 5-minute markets",
                reason_code="strategy_not_supported",
            )
        if snapshot.target_price <= 0:
            return _no_trade(
                self.name,
                context,
                reason="target price missing",
                reason_code="target_missing",
            )
        if snapshot.seconds_remaining < self.settings.min_seconds_remaining:
            return _no_trade(
                self.name,
                context,
                reason="too close to resolution",
                reason_code="too_late",
            )
        if snapshot.seconds_remaining > self.settings.max_seconds_remaining:
            return _no_trade(
                self.name,
                context,
                reason="outside late window",
                reason_code="too_early",
            )
        if abs(snapshot.delta_pct) < self.settings.min_delta_pct:
            return _no_trade(
                self.name,
                context,
                reason="late window edge too small",
                reason_code="edge_too_low",
            )

        if snapshot.delta > 0:
            book = context.up_book
            action = DecisionAction.BUY_UP
        else:
            book = context.down_book
            action = DecisionAction.BUY_DOWN

        estimated_probability = min(0.98, 0.80 + abs(snapshot.delta_pct / 100) * 30)
        market_probability = book.best_ask
        expected_return = _expected_return(estimated_probability, book)
        edge = estimated_probability - market_probability
        if (
            expected_return < self.settings.min_expected_return
            or expected_return > self.settings.max_expected_return
        ):
            return _no_trade(
                self.name,
                context,
                reason="expected return outside late-window band",
                reason_code="return_out_of_range",
                estimated_probability=estimated_probability,
                expected_return=expected_return,
                market_probability=market_probability,
                edge=edge,
            )
        if estimated_probability < self.settings.min_confidence:
            return _no_trade(
                self.name,
                context,
                reason="late-window confidence too low",
                reason_code="confidence_too_low",
                estimated_probability=estimated_probability,
                expected_return=expected_return,
                market_probability=market_probability,
                edge=edge,
            )

        return Decision(
            strategy=self.name,
            action=action,
            market_id=context.market.market_id,
            token_id=book.token_id,
            target_price=book.best_ask,
            estimated_probability=estimated_probability,
            confidence=estimated_probability,
            expected_return=expected_return,
            max_slippage=0.005,
            reason="late-window probability and return accepted",
            created_at=context.now,
            reason_code="late_window_high_confidence",
            market_probability=market_probability,
            edge=edge,
        )
