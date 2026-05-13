from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class DecisionAction(StrEnum):
    BUY_UP = "BUY_UP"
    BUY_DOWN = "BUY_DOWN"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"


class ExecutionMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


@dataclass(frozen=True)
class Market:
    market_id: str
    question: str
    slug: str
    up_token_id: str
    down_token_id: str
    start_time: datetime | None
    end_time: datetime
    tick_size: float
    min_size: float
    accepting_orders: bool
    price_to_beat: float | None = None


@dataclass(frozen=True)
class MarketSnapshot:
    market_id: str
    slug: str
    question: str
    market_profile: str
    start_time: datetime | None
    end_time: datetime
    accepting_orders: bool
    seconds_elapsed: float | None
    seconds_remaining: float
    window_seconds: float | None
    target_price: float
    btc_price: float
    delta: float
    delta_pct: float
    up_token_id: str
    down_token_id: str
    up_bid: float
    up_ask: float
    down_bid: float
    down_ask: float
    up_spread: float
    down_spread: float
    max_spread: float
    up_bid_size: float
    up_ask_size: float
    down_bid_size: float
    down_ask_size: float
    feed_fresh: bool
    feed_max_deviation_bps: float
    source_count: int


@dataclass(frozen=True)
class FeedPrice:
    source: str
    symbol: str
    value: float
    timestamp_ms: int


@dataclass(frozen=True)
class FeedAggregate:
    reference_price: float
    prices: tuple[FeedPrice, ...] | list[FeedPrice]
    max_deviation_bps: float
    fresh: bool
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "prices", tuple(self.prices))


@dataclass(frozen=True)
class OrderbookSnapshot:
    market_id: str
    token_id: str
    best_bid: float
    best_ask: float
    spread: float
    bid_size: float
    ask_size: float
    timestamp_ms: int


@dataclass(frozen=True)
class Decision:
    strategy: str
    action: DecisionAction
    market_id: str
    token_id: str
    target_price: float
    estimated_probability: float
    confidence: float
    expected_return: float
    max_slippage: float
    reason: str
    created_at: datetime
    reason_code: str = ""
    market_probability: float | None = None
    edge: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        data["created_at"] = self.created_at.isoformat()
        return data


@dataclass(frozen=True)
class BotEvent:
    level: str
    message: str
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data
