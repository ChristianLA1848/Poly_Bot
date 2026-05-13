import pytest
from datetime import UTC, datetime

from polybot import market_discovery
from polybot.market_discovery import current_btc_5m_slug, parse_btc_market


BASE_MARKET_PAYLOAD = {
    "id": "100",
    "conditionId": "0xabc",
    "question": "Bitcoin Up or Down - May 12, 9:00PM ET",
    "slug": "bitcoin-up-or-down-may-12-9pm-et",
    "endDateIso": "2026-05-12T21:05:00Z",
    "startDateIso": "2026-05-12T21:00:00Z",
    "outcomes": '["Up", "Down"]',
    "clobTokenIds": '["111", "222"]',
    "orderPriceMinTickSize": 0.01,
    "orderMinSize": 5,
    "acceptingOrders": True,
}


def test_parse_btc_market_extracts_tokens():
    market = parse_btc_market(BASE_MARKET_PAYLOAD)

    assert market.market_id == "0xabc"
    assert market.up_token_id == "111"
    assert market.down_token_id == "222"
    assert market.tick_size == 0.01
    assert market.accepting_orders is True


def test_current_btc_5m_slug_uses_current_utc_window():
    now = datetime(2026, 5, 13, 16, 39, 14, tzinfo=UTC)

    assert current_btc_5m_slug(now) == "btc-updown-5m-1778690100"


def test_parse_btc_market_derives_window_from_btc_slug():
    payload = BASE_MARKET_PAYLOAD | {
        "slug": "btc-updown-5m-1778690100",
        "startDateIso": "2026-05-12",
        "endDateIso": "2026-05-13",
        "endDate": "2026-05-13T16:40:00Z",
    }

    market = parse_btc_market(payload)

    assert market.start_time == datetime(2026, 5, 13, 16, 35, tzinfo=UTC)
    assert market.end_time == datetime(2026, 5, 13, 16, 40, tzinfo=UTC)


def test_parse_btc_market_accepts_native_list_fields():
    payload = BASE_MARKET_PAYLOAD | {
        "outcomes": ["Up", "Down"],
        "clobTokenIds": ["111", "222"],
    }

    market = parse_btc_market(payload)

    assert market.up_token_id == "111"
    assert market.down_token_id == "222"


def test_parse_btc_market_handles_reversed_outcome_ordering():
    payload = BASE_MARKET_PAYLOAD | {
        "outcomes": '[" Down ", " Up "]',
        "clobTokenIds": '["222", "111"]',
    }

    market = parse_btc_market(payload)

    assert market.up_token_id == "111"
    assert market.down_token_id == "222"


def test_parse_btc_market_rejects_malformed_non_list_json():
    payload = BASE_MARKET_PAYLOAD | {"outcomes": '"Up"'}

    with pytest.raises(ValueError, match="outcomes must decode to a list"):
        parse_btc_market(payload)


def test_parse_btc_market_rejects_invalid_json():
    payload = BASE_MARKET_PAYLOAD | {"outcomes": '["Up"'}

    with pytest.raises(ValueError, match="outcomes must be valid JSON"):
        parse_btc_market(payload)


def test_parse_btc_market_rejects_length_mismatch():
    payload = BASE_MARKET_PAYLOAD | {
        "outcomes": '["Up", "Down"]',
        "clobTokenIds": '["111"]',
    }

    with pytest.raises(ValueError, match="outcomes and clobTokenIds length mismatch"):
        parse_btc_market(payload)


def test_parse_btc_market_rejects_missing_up_down_outcome():
    payload = BASE_MARKET_PAYLOAD | {"outcomes": '["Up", "Flat"]'}

    with pytest.raises(ValueError, match="outcomes must include Up and Down"):
        parse_btc_market(payload)


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.closed = False

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_market_discovery_closes_owned_client(monkeypatch):
    fake_client = FakeAsyncClient()
    monkeypatch.setattr(market_discovery.httpx, "AsyncClient", lambda **kwargs: fake_client)

    async with market_discovery.MarketDiscovery() as discovery:
        assert discovery.client is fake_client

    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_market_discovery_does_not_close_injected_client():
    fake_client = FakeAsyncClient()
    discovery = market_discovery.MarketDiscovery(client=fake_client)

    await discovery.aclose()

    assert fake_client.closed is False


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeMarketsClient:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    async def get(self, path, params):
        self.requests.append((path, params))
        return FakeResponse(self.payload)


class FakeDiscoveryClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.requests = []

    async def get(self, path, params):
        self.requests.append((path, params))
        return FakeResponse(self.payloads[path])


class FakeRoutingClient:
    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    async def get(self, path, params=None):
        params = params or {}
        self.requests.append((path, params))
        key = (path, params.get("slug"))
        return FakeResponse(self.routes.get(key, []))


@pytest.mark.asyncio
async def test_market_discovery_finds_btc_updown_slug():
    payload = [
        BASE_MARKET_PAYLOAD
        | {
            "question": "Bitcoin Up or Down - May 13, 12:30AM-12:35AM ET",
            "slug": "btc-updown-5m-1778646600",
        }
    ]
    discovery = market_discovery.MarketDiscovery(client=FakeMarketsClient(payload))

    market = await discovery.find_btc_5m_market()

    assert market is not None
    assert market.slug == "btc-updown-5m-1778646600"


@pytest.mark.asyncio
async def test_market_discovery_fetches_current_window_by_slug():
    current_payload = BASE_MARKET_PAYLOAD | {
        "question": "Bitcoin Up or Down - May 13, 12:35PM-12:40PM ET",
        "slug": "btc-updown-5m-1778690100",
        "acceptingOrders": True,
        "enableOrderBook": True,
        "liquidity": "20484.0386",
        "startDateIso": "2026-05-12",
        "endDateIso": "2026-05-13",
        "endDate": "2026-05-13T16:40:00Z",
    }
    stale_payload = BASE_MARKET_PAYLOAD | {
        "slug": "btc-updown-5m-1766162100",
        "acceptingOrders": False,
    }
    client = FakeRoutingClient(
        {
            ("/markets", "btc-updown-5m-1778690100"): [current_payload],
            ("/markets", None): [stale_payload],
        }
    )
    discovery = market_discovery.MarketDiscovery(
        client=client,
        now_provider=lambda: datetime(2026, 5, 13, 16, 39, 14, tzinfo=UTC),
    )

    market = await discovery.find_btc_5m_market()

    assert market is not None
    assert market.slug == "btc-updown-5m-1778690100"
    assert market.accepting_orders is True
    assert client.requests == [
        ("/markets", {"slug": "btc-updown-5m-1778690100", "closed": "false"})
    ]


@pytest.mark.asyncio
async def test_market_discovery_finds_question_with_up_or_down_words():
    payload = [
        BASE_MARKET_PAYLOAD
        | {
            "question": "Bitcoin Up or Down - May 13, 12:30AM-12:35AM ET",
            "slug": "bitcoin-up-or-down-may-13",
        }
    ]
    discovery = market_discovery.MarketDiscovery(client=FakeMarketsClient(payload))

    market = await discovery.find_btc_5m_market()

    assert market is not None
    assert market.question.startswith("Bitcoin Up or Down")


@pytest.mark.asyncio
async def test_market_discovery_prefers_accepting_order_market():
    payload = [
        BASE_MARKET_PAYLOAD
        | {
            "slug": "btc-updown-5m-1778646300",
            "acceptingOrders": False,
            "endDateIso": "2026-05-13T00:35:00Z",
        },
        BASE_MARKET_PAYLOAD
        | {
            "slug": "btc-updown-5m-1778646600",
            "acceptingOrders": True,
            "endDateIso": "2026-05-13T00:40:00Z",
        },
    ]
    discovery = market_discovery.MarketDiscovery(client=FakeMarketsClient(payload))

    market = await discovery.find_btc_5m_market()

    assert market is not None
    assert market.slug == "btc-updown-5m-1778646600"


@pytest.mark.asyncio
async def test_market_discovery_returns_none_when_current_window_missing():
    client = FakeDiscoveryClient(
        {
            "/markets": [],
        }
    )
    discovery = market_discovery.MarketDiscovery(
        client=client,
        now_provider=lambda: datetime(2026, 5, 13, 16, 39, 14, tzinfo=UTC),
    )

    market = await discovery.find_btc_5m_market()

    assert market is None
    assert client.requests == [
        ("/markets", {"slug": "btc-updown-5m-1778690100", "closed": "false"})
    ]
