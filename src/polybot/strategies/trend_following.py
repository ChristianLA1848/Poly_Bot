from polybot.strategies.base import StrategyContext
from polybot.strategies.baseline_momentum import _no_trade


class TrendFollowingStrategy:
    name = "trend_following"

    def decide(self, context: StrategyContext):
        return _no_trade(
            self.name,
            context,
            reason="trend following requires a longer crypto market",
            reason_code="trend_not_supported_for_market",
            estimated_probability=0.5,
            expected_return=0.0,
        )
