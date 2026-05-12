import pytest

from polybot import orderbook
from polybot.orderbook import parse_orderbook


BASE_BOOK_PAYLOAD = {
    "market": "0xabc",
    "asset_id": "111",
    "bids": [{"price": "0.48", "size": "40"}],
    "asks": [{"price": "0.52", "size": "30"}],
    "timestamp": "1760000000000",
}


def test_parse_orderbook_best_bid_ask():
    book = parse_orderbook(BASE_BOOK_PAYLOAD)

    assert book.best_bid == 0.48
    assert book.best_ask == 0.52
    assert book.spread == 0.04
    assert book.bid_size == 40.0
    assert book.ask_size == 30.0


def test_parse_orderbook_rejects_empty_bids():
    payload = BASE_BOOK_PAYLOAD | {"bids": []}

    with pytest.raises(ValueError, match="no bid levels"):
        parse_orderbook(payload)


def test_parse_orderbook_rejects_empty_asks():
    payload = BASE_BOOK_PAYLOAD | {"asks": []}

    with pytest.raises(ValueError, match="no ask levels"):
        parse_orderbook(payload)


def test_parse_orderbook_uses_best_prices_from_unsorted_levels():
    payload = BASE_BOOK_PAYLOAD | {
        "bids": [
            {"price": "0.47", "size": "10"},
            {"price": "0.49", "size": "20"},
            {"price": "0.48", "size": "30"},
        ],
        "asks": [
            {"price": "0.55", "size": "40"},
            {"price": "0.51", "size": "50"},
            {"price": "0.53", "size": "60"},
        ],
    }

    book = parse_orderbook(payload)

    assert book.best_bid == 0.49
    assert book.bid_size == 20.0
    assert book.best_ask == 0.51
    assert book.ask_size == 50.0
    assert book.spread == 0.02


@pytest.mark.parametrize("field", ["market", "asset_id", "timestamp"])
def test_parse_orderbook_rejects_missing_top_level_field(field):
    payload = BASE_BOOK_PAYLOAD.copy()
    del payload[field]

    with pytest.raises(ValueError, match=f"orderbook missing {field}"):
        parse_orderbook(payload)


@pytest.mark.parametrize("field", ["price", "size"])
def test_parse_orderbook_rejects_missing_level_field_with_context(field):
    level = {"price": "0.52", "size": "30"}
    del level[field]
    payload = BASE_BOOK_PAYLOAD | {"asks": [level]}

    with pytest.raises(ValueError, match=f"ask level 0 missing {field}"):
        parse_orderbook(payload)


@pytest.mark.parametrize("field", ["price", "size"])
def test_parse_orderbook_rejects_invalid_level_number_with_context(field):
    payload = BASE_BOOK_PAYLOAD | {"bids": [{"price": "0.48", "size": "40"}]}
    payload["bids"][0][field] = "bad"

    with pytest.raises(ValueError, match=f"bid level 0 {field} must be numeric"):
        parse_orderbook(payload)


def test_parse_orderbook_rejects_invalid_timestamp():
    payload = BASE_BOOK_PAYLOAD | {"timestamp": "bad"}

    with pytest.raises(ValueError, match="orderbook timestamp must be an integer"):
        parse_orderbook(payload)


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.closed = False

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_orderbook_client_closes_owned_client(monkeypatch):
    fake_client = FakeAsyncClient()
    monkeypatch.setattr(orderbook.httpx, "AsyncClient", lambda **kwargs: fake_client)

    async with orderbook.OrderbookClient() as client:
        assert client.client is fake_client

    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_orderbook_client_does_not_close_injected_client():
    fake_client = FakeAsyncClient()
    client = orderbook.OrderbookClient(client=fake_client)

    await client.aclose()

    assert fake_client.closed is False
