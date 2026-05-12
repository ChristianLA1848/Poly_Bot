from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from polybot.models import Decision, FeedAggregate, Market, OrderbookSnapshot


@dataclass(frozen=True)
class StrategyContext:
    market: Market
    reference_start_price: float
    feed: FeedAggregate
    up_book: OrderbookSnapshot
    down_book: OrderbookSnapshot
    now: datetime


class Strategy(Protocol):
    name: str

    def decide(self, context: StrategyContext) -> Decision:
        ...


def load_strategy(name: str) -> Strategy:
    if name == "baseline_momentum":
        from polybot.strategies.baseline_momentum import BaselineMomentumStrategy

        return BaselineMomentumStrategy()
    if name == "late_window":
        from polybot.strategies.late_window import LateWindowStrategy

        return LateWindowStrategy()
    raise ValueError(f"Unknown strategy: {name}")
