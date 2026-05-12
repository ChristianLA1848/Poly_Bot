from dataclasses import dataclass

from polybot.config import RiskSection
from polybot.models import Decision, DecisionAction, FeedAggregate, OrderbookSnapshot


@dataclass(frozen=True)
class RiskResult:
    accepted: bool
    reason: str


class RiskGate:
    def __init__(self, config: RiskSection) -> None:
        self.config = config

    def evaluate(
        self,
        decision: Decision,
        feed: FeedAggregate,
        book: OrderbookSnapshot,
        today_pnl: float,
        open_positions: int,
        open_orders: int,
    ) -> RiskResult:
        if decision.action == DecisionAction.NO_TRADE:
            return RiskResult(False, "strategy returned no trade")

        if not feed.fresh:
            return RiskResult(False, "feed stale")

        if feed.max_deviation_bps > self.config.max_feed_deviation_bps:
            return RiskResult(False, "feed deviation too high")

        if book.spread > self.config.max_spread:
            return RiskResult(False, "spread too high")

        if min(book.bid_size, book.ask_size) < self.config.min_liquidity:
            return RiskResult(False, "liquidity too low")

        if decision.estimated_probability - decision.target_price < self.config.min_edge:
            return RiskResult(False, "edge too low")

        if today_pnl <= -abs(self.config.max_daily_loss):
            return RiskResult(False, "daily loss limit hit")

        if open_positions >= self.config.max_open_positions:
            return RiskResult(False, "too many open positions")

        if open_orders >= self.config.max_open_orders:
            return RiskResult(False, "too many open orders")

        return RiskResult(True, "accepted")
