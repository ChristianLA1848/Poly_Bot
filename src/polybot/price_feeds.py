from datetime import UTC, datetime
from statistics import median

from polybot.models import FeedAggregate, FeedPrice


def aggregate_prices(
    prices: list[FeedPrice],
    now_ms: int,
    max_age_ms: int,
) -> FeedAggregate:
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
    fresh = all(now_ms - price.timestamp_ms <= max_age_ms for price in prices)

    return FeedAggregate(
        reference_price=reference_price,
        prices=prices,
        max_deviation_bps=max_deviation_bps,
        fresh=fresh,
        created_at=created_at,
    )
