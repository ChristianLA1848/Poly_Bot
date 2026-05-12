import pytest

from polybot.orderbook import parse_orderbook


def test_parse_orderbook_best_bid_ask():
    payload = {
        "market": "0xabc",
        "asset_id": "111",
        "bids": [{"price": "0.48", "size": "40"}],
        "asks": [{"price": "0.52", "size": "30"}],
        "timestamp": "1760000000000",
    }

    book = parse_orderbook(payload)

    assert book.best_bid == 0.48
    assert book.best_ask == 0.52
    assert book.spread == 0.04
    assert book.bid_size == 40.0
    assert book.ask_size == 30.0


def test_parse_orderbook_rejects_empty_bids():
    payload = {
        "market": "0xabc",
        "asset_id": "111",
        "bids": [],
        "asks": [{"price": "0.52", "size": "30"}],
        "timestamp": "1760000000000",
    }

    with pytest.raises(ValueError, match="no bid levels"):
        parse_orderbook(payload)


def test_parse_orderbook_rejects_empty_asks():
    payload = {
        "market": "0xabc",
        "asset_id": "111",
        "bids": [{"price": "0.48", "size": "40"}],
        "asks": [],
        "timestamp": "1760000000000",
    }

    with pytest.raises(ValueError, match="no ask levels"):
        parse_orderbook(payload)
