from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import json
import re
from typing import Any

import httpx

from polybot.models import Market

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
BTC_5M_SLUG_PREFIX = "btc-updown-5m-"
BTC_5M_WINDOW_SECONDS = 5 * 60
BTC_5M_SLUG_RE = re.compile(r"^btc-updown-5m-(?P<timestamp>\d+)$")


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


def current_btc_5m_slug(now: datetime | None = None) -> str:
    current = now or datetime.now(tz=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    timestamp = int(current.timestamp())
    window_start = timestamp - (timestamp % BTC_5M_WINDOW_SECONDS)
    return f"{BTC_5M_SLUG_PREFIX}{window_start}"


def _window_from_slug(slug: str) -> tuple[datetime, datetime] | None:
    match = BTC_5M_SLUG_RE.match(slug)
    if match is None:
        return None

    start = datetime.fromtimestamp(int(match.group("timestamp")), tz=UTC)
    return start, start + timedelta(seconds=BTC_5M_WINDOW_SECONDS)


def _payload_time(payload: dict[str, Any], *fields: str) -> datetime:
    for field in fields:
        value = payload.get(field)
        if value:
            return _parse_dt(value)
    raise ValueError(f"payload must include one of: {', '.join(fields)}")


def parse_btc_market(payload: dict[str, Any]) -> Market:
    outcomes = [outcome.strip().lower() for outcome in _loads_list(payload["outcomes"], field="outcomes")]
    token_ids = _loads_list(payload["clobTokenIds"], field="clobTokenIds")

    if len(outcomes) != len(token_ids):
        raise ValueError("outcomes and clobTokenIds length mismatch")

    token_by_outcome = dict(zip(outcomes, token_ids, strict=True))
    if "up" not in token_by_outcome or "down" not in token_by_outcome:
        raise ValueError("outcomes must include Up and Down")

    slug = payload.get("slug") or ""
    slug_window = _window_from_slug(slug)
    start_time, end_time = (
        slug_window
        if slug_window is not None
        else (
            _parse_dt(payload["startDateIso"]) if payload.get("startDateIso") else None,
            _payload_time(payload, "endDate", "endDateIso"),
        )
    )

    return Market(
        market_id=payload["conditionId"],
        question=payload.get("question") or "",
        slug=slug,
        up_token_id=token_by_outcome["up"],
        down_token_id=token_by_outcome["down"],
        start_time=start_time,
        end_time=end_time,
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


def _extract_public_search_markets(payload: dict[str, Any]) -> list[dict[str, Any]]:
    markets = list(payload.get("markets") or [])
    for event in payload.get("events") or []:
        markets.extend(event.get("markets") or [])
    return markets


def _select_best_market(items: list[dict[str, Any]]) -> Market | None:
    markets = [parse_btc_market(item) for item in items if _is_btc_5m_updown_market(item)]
    if not markets:
        return None
    return sorted(markets, key=lambda market: (not market.accepting_orders, market.end_time))[0]


class MarketDiscovery:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(base_url=GAMMA_BASE_URL, timeout=10.0)
        self.now_provider = now_provider or (lambda: datetime.now(tz=UTC))

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
                "slug": current_btc_5m_slug(self.now_provider()),
                "closed": "false",
            },
        )
        response.raise_for_status()

        return _select_best_market(response.json())
