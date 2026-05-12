from polybot.market_discovery import parse_btc_market


def test_parse_btc_market_extracts_tokens():
    payload = {
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

    market = parse_btc_market(payload)

    assert market.market_id == "0xabc"
    assert market.up_token_id == "111"
    assert market.down_token_id == "222"
    assert market.tick_size == 0.01
    assert market.accepting_orders is True
