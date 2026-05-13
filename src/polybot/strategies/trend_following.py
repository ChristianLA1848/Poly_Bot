from polybot.models import Decision, DecisionAction
from polybot.strategies.baseline_momentum import _expected_return, _no_trade
from polybot.strategies.base import StrategyContext


class TrendFollowingStrategy:
    name = "trend_following"
    min_delta_pct = 1.0
    min_seconds_elapsed = 300
    min_edge = 0.03

    def decide(self, context: StrategyContext) -> Decision:
        snapshot = context.snapshot
        if snapshot.market_profile != "longer_crypto":
            return _no_trade(
                self.name,
                context,
                reason="trend following requires a longer crypto market",
                reason_code="trend_not_supported_for_market",
            )
        if snapshot.target_price <= 0:
            return _no_trade(
                self.name,
                context,
                reason="target price missing",
                reason_code="target_missing",
            )
        if (
            snapshot.seconds_elapsed is None
            or snapshot.seconds_elapsed < self.min_seconds_elapsed
        ):
            return _no_trade(
                self.name,
                context,
                reason="not enough trend history in current window",
                reason_code="trend_history_too_short",
            )
        if abs(snapshot.delta_pct) < self.min_delta_pct:
            return _no_trade(
                self.name,
                context,
                reason="trend delta too small",
                reason_code="trend_delta_too_small",
            )

        if snapshot.delta > 0:
            book = context.up_book
            action = DecisionAction.BUY_UP
        else:
            book = context.down_book
            action = DecisionAction.BUY_DOWN

        estimated_probability = min(0.90, 0.55 + abs(snapshot.delta_pct) / 20)
        market_probability = book.best_ask
        edge = estimated_probability - market_probability
        expected_return = _expected_return(estimated_probability, book)
        if edge < self.min_edge:
            return _no_trade(
                self.name,
                context,
                reason="trend edge too low",
                reason_code="edge_too_low",
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
            confidence=min(0.90, estimated_probability),
            expected_return=expected_return,
            max_slippage=0.01,
            reason="trend confirmed with positive edge",
            created_at=context.now,
            reason_code="trend_confirmed",
            market_probability=market_probability,
            edge=edge,
        )
