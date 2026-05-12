from datetime import UTC, datetime

import pytest

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
    assert agg.max_deviation_bps < 11
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


def test_aggregate_prices_rejects_non_positive_values():
    prices = [FeedPrice("coinbase", "BTC-USD", 0.0, 1_000_000)]

    with pytest.raises(ValueError, match="price values must be positive"):
        aggregate_prices(prices, now_ms=1_001_000, max_age_ms=2_500)
