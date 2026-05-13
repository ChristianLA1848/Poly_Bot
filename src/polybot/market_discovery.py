from datetime import datetime
import json
from typing import Any

import httpx

from polybot.models import Market

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"


def _loads_list(value: Any, *, field: str) -> list[str]:
    if isinstance(value, list):
        decoded = value
    elif isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field} must be valid JSON") from exc
    else:
        raise ValueError(f"{field} must be a JSON string or list")

    if not isinstance(decoded, list):
        raise ValueError(f"{field} must decode to a list")

    if not all(isinstance(item, str) for item in decoded):
        raise ValueError(f"{field} must contain only strings")

    return decoded


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_btc_market(payload: dict[str, Any]) -> Market:
    outcomes = [outcome.strip().lower() for outcome in _loads_list(payload["outcomes"], field="outcomes")]
    token_ids = _loads_list(payload["clobTokenIds"], field="clobTokenIds")

    if len(outcomes) != len(token_ids):
        raise ValueError("outcomes and clobTokenIds length mismatch")

    token_by_outcome = dict(zip(outcomes, token_ids, strict=True))
    if "up" not in token_by_outcome or "down" not in token_by_outcome:
        raise ValueError("outcomes must include Up and Down")

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


def _is_btc_5m_updown_market(item: dict[str, Any]) -> bool:
    question = (item.get("question") or "").lower()
    slug = (item.get("slug") or "").lower()
    has_btc_slug = slug.startswith("btc-updown-5m-")
    has_question_match = "bitcoin" in question and "up or down" in question
    return (has_btc_slug or has_question_match) and bool(item.get("clobTokenIds"))


class MarketDiscovery:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(base_url=GAMMA_BASE_URL, timeout=10.0)

    async def __aenter__(self) -> "MarketDiscovery":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

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
            if _is_btc_5m_updown_market(item):
                return parse_btc_market(item)
        return None
