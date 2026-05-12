from typing import Any

import httpx

from polybot.models import OrderbookSnapshot

CLOB_BASE_URL = "https://clob.polymarket.com"


def _required(payload: dict[str, Any], field: str) -> Any:
    try:
        return payload[field]
    except KeyError as exc:
        raise ValueError(f"orderbook missing {field}") from exc


def _level_value(level: dict[str, Any], *, side: str, index: int, field: str) -> float:
    try:
        raw_value = level[field]
    except KeyError as exc:
        raise ValueError(f"{side} level {index} missing {field}") from exc

    try:
        return float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{side} level {index} {field} must be numeric") from exc


def _best(levels: list[dict[str, Any]], *, reverse: bool, side: str) -> tuple[float, float]:
    if not levels:
        raise ValueError(f"orderbook has no {side} levels")

    parsed = []
    for index, level in enumerate(levels):
        if not isinstance(level, dict):
            raise ValueError(f"{side} level {index} must be an object")
        price = _level_value(level, side=side, index=index, field="price")
        size = _level_value(level, side=side, index=index, field="size")
        parsed.append((price, size))

    price, size = sorted(parsed, key=lambda row: row[0], reverse=reverse)[0]
    return price, size


def parse_orderbook(payload: dict[str, Any]) -> OrderbookSnapshot:
    best_bid, bid_size = _best(payload.get("bids", []), reverse=True, side="bid")
    best_ask, ask_size = _best(payload.get("asks", []), reverse=False, side="ask")
    timestamp = _required(payload, "timestamp")

    try:
        timestamp_ms = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise ValueError("orderbook timestamp must be an integer") from exc

    return OrderbookSnapshot(
        market_id=_required(payload, "market"),
        token_id=_required(payload, "asset_id"),
        best_bid=best_bid,
        best_ask=best_ask,
        spread=round(best_ask - best_bid, 6),
        bid_size=bid_size,
        ask_size=ask_size,
        timestamp_ms=timestamp_ms,
    )


class OrderbookClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(base_url=CLOB_BASE_URL, timeout=10.0)

    async def __aenter__(self) -> "OrderbookClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def get_book(self, token_id: str) -> OrderbookSnapshot:
        response = await self.client.get("/book", params={"token_id": token_id})
        response.raise_for_status()
        return parse_orderbook(response.json())
