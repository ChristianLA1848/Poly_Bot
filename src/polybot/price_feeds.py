from datetime import UTC, datetime
from statistics import median
import time
from typing import Any

import httpx

from polybot.models import FeedAggregate, FeedPrice

BINANCE_BTC_URL = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
COINBASE_BTC_URL = "https://api.coinbase.com/v2/prices/BTC-USD/spot"


def aggregate_prices(
    prices: list[FeedPrice],
    now_ms: int,
    max_age_ms: int,
) -> FeedAggregate:
    if max_age_ms < 0:
        raise ValueError("max_age_ms must be non-negative")

    created_at = datetime.fromtimestamp(now_ms / 1000, tz=UTC)

    if not prices:
        return FeedAggregate(
            reference_price=0.0,
            prices=(),
            max_deviation_bps=0.0,
            fresh=False,
            created_at=created_at,
        )

    values = [price.value for price in prices]
    if any(value <= 0 for value in values):
        raise ValueError("price values must be positive")

    reference_price = float(median(values))
    max_deviation_bps = max(
        abs(price.value - reference_price) / reference_price * 10_000
        for price in prices
    )
    fresh = all(
        0 <= now_ms - price.timestamp_ms <= max_age_ms
        for price in prices
    )

    return FeedAggregate(
        reference_price=reference_price,
        prices=prices,
        max_deviation_bps=max_deviation_bps,
        fresh=fresh,
        created_at=created_at,
    )


async def fetch_btc_feed_aggregate(
    max_age_ms: int,
    client: httpx.AsyncClient | Any | None = None,
) -> FeedAggregate:
    """Fetch BTC spot prices from public REST endpoints and aggregate them."""
    if max_age_ms < 0:
        raise ValueError("max_age_ms must be non-negative")

    if client is not None:
        return await _fetch_btc_feed_aggregate_with_client(client, max_age_ms)

    async with httpx.AsyncClient(timeout=5.0) as owned_client:
        return await _fetch_btc_feed_aggregate_with_client(owned_client, max_age_ms)


async def _fetch_btc_feed_aggregate_with_client(
    client: httpx.AsyncClient | Any,
    max_age_ms: int,
) -> FeedAggregate:
    binance_response = await client.get(BINANCE_BTC_URL)
    coinbase_response = await client.get(COINBASE_BTC_URL)
    binance_response.raise_for_status()
    coinbase_response.raise_for_status()

    binance_price = float(binance_response.json()["price"])
    coinbase_price = float(coinbase_response.json()["data"]["amount"])
    now_ms = int(time.time() * 1000)
    prices = [
        FeedPrice("binance", "BTCUSDT", binance_price, now_ms),
        FeedPrice("coinbase", "BTC-USD", coinbase_price, now_ms),
    ]
    return aggregate_prices(prices, now_ms=now_ms, max_age_ms=max_age_ms)
