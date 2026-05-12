from polybot.models import Decision, DecisionAction
from polybot.strategies.base import StrategyContext
from polybot.strategies.baseline_momentum import _expected_return, _no_trade


class LateWindowStrategy:
    name = "late_window"

    def decide(self, context: StrategyContext) -> Decision:
        seconds_remaining = (context.market.end_time - context.now).total_seconds()
        if seconds_remaining < 20 or seconds_remaining > 60:
            return _no_trade(
                self.name,
                context,
                reason="outside late window",
            )

        delta = (
            context.feed.reference_price - context.reference_start_price
        ) / context.reference_start_price
        if abs(delta) < 0.001:
            return _no_trade(
                self.name,
                context,
                reason="late window edge too small",
            )

        if delta > 0:
            book = context.up_book
            action = DecisionAction.BUY_UP
        else:
            book = context.down_book
            action = DecisionAction.BUY_DOWN

        estimated_probability = min(0.98, 0.80 + abs(delta) * 30)
        expected_return = _expected_return(estimated_probability, book)
        if expected_return < 0.01 or expected_return > 0.10:
            return _no_trade(
                self.name,
                context,
                reason="expected return outside late-window band",
                estimated_probability=estimated_probability,
                expected_return=expected_return,
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
        )
