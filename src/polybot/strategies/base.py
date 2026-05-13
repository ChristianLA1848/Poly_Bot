from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from polybot.models import (
    Decision,
    FeedAggregate,
    Market,
    MarketSnapshot,
    OrderbookSnapshot,
)


@dataclass(frozen=True)
class StrategyContext:
    market: Market
    reference_start_price: float
    feed: FeedAggregate
    up_book: OrderbookSnapshot
    down_book: OrderbookSnapshot
    now: datetime
    snapshot: MarketSnapshot = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot", build_market_snapshot(self))


def classify_market_profile(market: Market) -> str:
    duration = (
        (market.end_time - market.start_time).total_seconds()
        if market.start_time
        else None
    )
    if market.slug.startswith("btc-updown-5m-") or duration == 300:
        return "btc_5m"
    if "bitcoin" in market.question.lower() or "btc" in market.slug.lower():
        return "longer_crypto"
    return "all_crypto"


def build_market_snapshot(context: StrategyContext) -> MarketSnapshot:
    market = context.market
    seconds_remaining = (market.end_time - context.now).total_seconds()
    seconds_elapsed = None
    window_seconds = None
    if market.start_time is not None:
        seconds_elapsed = (context.now - market.start_time).total_seconds()
        window_seconds = (market.end_time - market.start_time).total_seconds()

    delta = round(context.feed.reference_price - context.reference_start_price, 6)
    delta_pct = (
        round((delta / context.reference_start_price) * 100, 6)
        if context.reference_start_price
        else 0.0
    )

    return MarketSnapshot(
        market_id=market.market_id,
        slug=market.slug,
        question=market.question,
        market_profile=classify_market_profile(market),
        start_time=market.start_time,
        end_time=market.end_time,
        accepting_orders=market.accepting_orders,
        seconds_elapsed=seconds_elapsed,
        seconds_remaining=seconds_remaining,
        window_seconds=window_seconds,
        target_price=context.reference_start_price,
        btc_price=context.feed.reference_price,
        delta=delta,
        delta_pct=delta_pct,
        up_token_id=market.up_token_id,
        down_token_id=market.down_token_id,
        up_bid=context.up_book.best_bid,
        up_ask=context.up_book.best_ask,
        down_bid=context.down_book.best_bid,
        down_ask=context.down_book.best_ask,
        up_spread=context.up_book.spread,
        down_spread=context.down_book.spread,
        max_spread=max(context.up_book.spread, context.down_book.spread),
        up_bid_size=context.up_book.bid_size,
        up_ask_size=context.up_book.ask_size,
        down_bid_size=context.down_book.bid_size,
        down_ask_size=context.down_book.ask_size,
        feed_fresh=context.feed.fresh,
        feed_max_deviation_bps=context.feed.max_deviation_bps,
        source_count=len(context.feed.prices),
    )


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
