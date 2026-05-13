from collections.abc import Callable
from dataclasses import replace
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
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(?P<data>.*?)</script>')
PRICE_TO_BEAT_RE = re.compile(r'"priceToBeat"\s*:\s*(?P<price>\d+(?:\.\d+)?)')


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


def _parse_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _payload_price_to_beat(payload: dict[str, Any]) -> float | None:
    direct_price = _parse_optional_float(payload.get("priceToBeat"))
    if direct_price is not None:
        return direct_price

    metadata = payload.get("eventMetadata")
    if isinstance(metadata, dict):
        return _parse_optional_float(metadata.get("priceToBeat"))

    return None


def _normalize_iso(value: str) -> str:
    return value.replace(".000Z", "Z")


def _extract_next_data_open_price(html: str, start_time: datetime | None) -> float | None:
    match = NEXT_DATA_RE.search(html)
    if match is None:
        return None

    try:
        next_data = json.loads(match.group("data"))
    except json.JSONDecodeError:
        return None

    expected_start = start_time.isoformat().replace("+00:00", "Z") if start_time else None
    queries = (
        next_data.get("props", {})
        .get("pageProps", {})
        .get("dehydratedState", {})
        .get("queries", [])
    )
    for query in queries:
        query_key = query.get("queryKey") or []
        if query_key[:3] != ["crypto-prices", "price", "BTC"]:
            continue
        if expected_start is not None and len(query_key) > 3:
            if _normalize_iso(query_key[3]) != expected_start:
                continue
        data = query.get("state", {}).get("data", {})
        price = _parse_optional_float(data.get("openPrice"))
        if price is not None:
            return price

    return None


def _extract_price_to_beat_from_event_page(
    html: str,
    slug: str,
    start_time: datetime | None = None,
) -> float | None:
    next_data_price = _extract_next_data_open_price(html, start_time)
    if next_data_price is not None:
        return next_data_price

    slug_marker = f'"slug":"{slug}"'
    start = html.find(slug_marker)
    while start != -1:
        next_slug = html.find('"slug":"', start + len(slug_marker))
        segment = html[start : next_slug if next_slug != -1 else start + 50_000]
        match = PRICE_TO_BEAT_RE.search(segment)
        if match is not None:
            return float(match.group("price"))
        start = html.find(slug_marker, start + len(slug_marker))

    return None


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
        price_to_beat=_payload_price_to_beat(payload),
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
        slug = current_btc_5m_slug(self.now_provider())
        response = await self.client.get(
            "/markets",
            params={
                "slug": slug,
                "closed": "false",
            },
        )
        response.raise_for_status()

        market = _select_best_market(response.json())
        if market is None or market.price_to_beat is not None:
            return market

        price_to_beat = await self._fetch_price_to_beat(slug, market.start_time)
        if price_to_beat is None:
            return market

        return replace(market, price_to_beat=price_to_beat)

    async def _fetch_price_to_beat(self, slug: str, start_time: datetime | None) -> float | None:
        try:
            response = await self.client.get(f"https://polymarket.com/de/event/{slug}", params={})
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        return _extract_price_to_beat_from_event_page(response.text, slug, start_time)
