from datetime import UTC, datetime

import pytest

from polybot import price_feeds
from polybot.models import FeedPrice
from polybot.price_feeds import aggregate_prices


def test_aggregate_prices_uses_median_and_deviation():
    prices = [
        FeedPrice("pm_binance", "btcusdt", 100.0, 1_000_000),
        FeedPrice("pm_chainlink", "btc/usd", 100.1, 1_000_010),
        FeedPrice("coinbase", "BTC-USD", 99.9, 1_000_020),
    ]

    agg = aggregate_prices(prices, now_ms=1_001_000, max_age_ms=2_500)

    assert agg.reference_price == 100.0
    assert agg.fresh is True
    assert agg.max_deviation_bps == pytest.approx(10.0)
    assert agg.created_at.tzinfo == UTC


def test_aggregate_prices_marks_stale():
    prices = [FeedPrice("pm_binance", "btcusdt", 100.0, 1_000_000)]

    agg = aggregate_prices(prices, now_ms=1_010_000, max_age_ms=2_500)

    assert agg.fresh is False


def test_aggregate_prices_empty_input_returns_stale_zero_reference():
    agg = aggregate_prices([], now_ms=1_778_520_000_000, max_age_ms=2_500)

    assert agg.reference_price == 0.0
    assert agg.prices == ()
    assert agg.max_deviation_bps == 0.0
    assert agg.fresh is False
    assert agg.created_at == datetime.fromtimestamp(1_778_520_000, tz=UTC)


def test_aggregate_prices_marks_mixed_freshness_stale_and_stores_tuple():
    prices = [
        FeedPrice("pm_binance", "btcusdt", 100.0, 1_000_000),
        FeedPrice("coinbase", "BTC-USD", 100.2, 1_000_900),
    ]

    agg = aggregate_prices(prices, now_ms=1_002_600, max_age_ms=2_500)

    assert agg.reference_price == 100.1
    assert agg.fresh is False
    assert agg.prices == tuple(prices)


def test_aggregate_prices_uses_even_count_median_for_deviation():
    prices = [
        FeedPrice("pm_binance", "btcusdt", 100.0, 1_000_000),
        FeedPrice("coinbase", "BTC-USD", 102.0, 1_000_100),
    ]

    agg = aggregate_prices(prices, now_ms=1_000_200, max_age_ms=2_500)

    assert agg.reference_price == 101.0
    assert agg.max_deviation_bps == pytest.approx(99.0099009901)


def test_aggregate_prices_marks_future_timestamp_stale():
    prices = [FeedPrice("coinbase", "BTC-USD", 100.0, 1_001_001)]

    agg = aggregate_prices(prices, now_ms=1_001_000, max_age_ms=2_500)

    assert agg.fresh is False


def test_aggregate_prices_rejects_negative_max_age():
    prices = [FeedPrice("coinbase", "BTC-USD", 100.0, 1_000_000)]

    with pytest.raises(ValueError, match="max_age_ms must be non-negative"):
        aggregate_prices(prices, now_ms=1_001_000, max_age_ms=-1)


@pytest.mark.parametrize("value", [0.0, -1.0])
def test_aggregate_prices_rejects_non_positive_values(value):
    prices = [FeedPrice("coinbase", "BTC-USD", value, 1_000_000)]

    with pytest.raises(ValueError, match="price values must be positive"):
        aggregate_prices(prices, now_ms=1_001_000, max_age_ms=2_500)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self):
        self.urls = []

    async def get(self, url):
        self.urls.append(url)
        if "binance" in url:
            return FakeResponse({"price": "100.00"})
        return FakeResponse({"data": {"amount": "100.20"}})


@pytest.mark.asyncio
async def test_fetch_btc_feed_aggregate_uses_public_rest_prices(monkeypatch):
    fake_client = FakeClient()
    monkeypatch.setattr("polybot.price_feeds.time.time", lambda: 1_778_520_000.0)

    agg = await price_feeds.fetch_btc_feed_aggregate(max_age_ms=2_500, client=fake_client)

    assert fake_client.urls == [
        "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
        "https://api.coinbase.com/v2/prices/BTC-USD/spot",
    ]
    assert [price.source for price in agg.prices] == ["binance", "coinbase"]
    assert agg.reference_price == 100.1
    assert agg.fresh is True
