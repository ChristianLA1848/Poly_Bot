from datetime import datetime
import json
from typing import Any

import httpx

from polybot.models import Market

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"


def _loads_list(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return value
    return list(json.loads(value))


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_btc_market(payload: dict[str, Any]) -> Market:
    outcomes = _loads_list(payload["outcomes"])
    token_ids = _loads_list(payload["clobTokenIds"])
    token_by_outcome = {
        outcome.lower(): token for outcome, token in zip(outcomes, token_ids, strict=True)
    }

    return Market(
        market_id=payload["conditionId"],
        question=payload.get("question") or "",
        slug=payload.get("slug") or "",
        up_token_id=token_by_outcome["up"],
        down_token_id=token_by_outcome["down"],
        start_time=_parse_dt(payload["startDateIso"]) if payload.get("startDateIso") else None,
        end_time=_parse_dt(payload["endDateIso"]),
        tick_size=float(payload.get("orderPriceMinTickSize") or 0.01),
        min_size=float(payload.get("orderMinSize") or 5.0),
        accepting_orders=bool(payload.get("acceptingOrders")),
    )


class MarketDiscovery:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client or httpx.AsyncClient(base_url=GAMMA_BASE_URL, timeout=10.0)

    async def find_btc_5m_market(self) -> Market | None:
        response = await self.client.get(
            "/markets",
            params={
                "closed": "false",
                "active": "true",
                "limit": 100,
                "order": "endDate",
                "ascending": "true",
            },
        )
        response.raise_for_status()

        for item in response.json():
            text = f"{item.get('question', '')} {item.get('slug', '')}".lower()
            if "bitcoin" in text and "up-or-down" in text and item.get("clobTokenIds"):
                return parse_btc_market(item)
        return None
