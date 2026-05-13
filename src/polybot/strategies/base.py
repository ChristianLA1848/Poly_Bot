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
    question = market.question.lower()
    slug = market.slug.lower()
    is_btc_market = "bitcoin" in question or "btc" in slug
    duration = (
        (market.end_time - market.start_time).total_seconds()
        if market.start_time
        else None
    )
    if market.slug.startswith("btc-updown-5m-") or (is_btc_market and duration == 300):
        return "btc_5m"
    if is_btc_market:
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


@dataclass(frozen=True)
class StrategyMetadata:
    name: str
    label: str
    market_profiles: tuple[str, ...]
    description: str


STRATEGY_METADATA = {
    "baseline_momentum": StrategyMetadata(
        name="baseline_momentum",
        label="Baseline Momentum",
        market_profiles=("btc_5m", "longer_crypto", "all_crypto"),
        description="Momentum strategy using current BTC delta against target.",
    ),
    "late_window_5m": StrategyMetadata(
        name="late_window_5m",
        label="Late Window 5m",
        market_profiles=("btc_5m",),
        description="Trades BTC 5-minute windows late when confidence and return align.",
    ),
    "trend_following": StrategyMetadata(
        name="trend_following",
        label="Trend Following",
        market_profiles=("longer_crypto",),
        description="Conservative trend strategy for longer crypto windows.",
    ),
}


STRATEGY_ALIASES = {"late_window": "late_window_5m"}


def normalize_strategy_name(name: str) -> str:
    return STRATEGY_ALIASES.get(name, name)


def list_strategy_metadata() -> tuple[StrategyMetadata, ...]:
    return tuple(STRATEGY_METADATA.values())


def strategy_supports_market(name: str, market_profile: str) -> bool:
    metadata = STRATEGY_METADATA[normalize_strategy_name(name)]
    return market_profile in metadata.market_profiles


def load_strategy(name: str) -> Strategy:
    normalized = normalize_strategy_name(name)
    if normalized == "baseline_momentum":
        from polybot.strategies.baseline_momentum import BaselineMomentumStrategy

        return BaselineMomentumStrategy()
    if normalized == "late_window_5m":
        from polybot.strategies.late_window_5m import LateWindow5mStrategy

        return LateWindow5mStrategy()
    if normalized == "trend_following":
        from polybot.strategies.trend_following import TrendFollowingStrategy

        return TrendFollowingStrategy()
    raise ValueError(f"Unknown strategy: {name}")
