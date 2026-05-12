from typing import Any

import httpx

from polybot.models import OrderbookSnapshot

CLOB_BASE_URL = "https://clob.polymarket.com"


def _best(levels: list[dict[str, str]], *, reverse: bool, side: str) -> tuple[float, float]:
    if not levels:
        raise ValueError(f"orderbook has no {side} levels")

    parsed = [(float(level["price"]), float(level["size"])) for level in levels]
    price, size = sorted(parsed, key=lambda row: row[0], reverse=reverse)[0]
    return price, size


def parse_orderbook(payload: dict[str, Any]) -> OrderbookSnapshot:
    best_bid, bid_size = _best(payload.get("bids", []), reverse=True, side="bid")
    best_ask, ask_size = _best(payload.get("asks", []), reverse=False, side="ask")

    return OrderbookSnapshot(
        market_id=payload["market"],
        token_id=payload["asset_id"],
        best_bid=best_bid,
        best_ask=best_ask,
        spread=round(best_ask - best_bid, 6),
        bid_size=bid_size,
        ask_size=ask_size,
        timestamp_ms=int(payload["timestamp"]),
    )


class OrderbookClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client or httpx.AsyncClient(base_url=CLOB_BASE_URL, timeout=10.0)

    async def get_book(self, token_id: str) -> OrderbookSnapshot:
        response = await self.client.get("/book", params={"token_id": token_id})
        response.raise_for_status()
        return parse_orderbook(response.json())
