from polybot.positions import Position, PositionManager


def test_position_manager_tracks_today_pnl():
    manager = PositionManager()
    manager.record_fill("m", "up", stake=5.0, shares=10.0, price=0.5)
    manager.mark_price("up", 0.6)

    assert manager.unrealized_pnl() == 1.0
    assert manager.open_positions_count() == 1


def test_mark_unknown_token_is_no_op():
    manager = PositionManager()

    manager.mark_price("missing", 0.7)

    assert manager.unrealized_pnl() == 0
    assert manager.open_positions_count() == 0


def test_unrealized_pnl_sums_multiple_positions():
    manager = PositionManager()
    manager.record_fill("market-1", "up", stake=5.0, shares=10.0, price=0.5)
    manager.record_fill("market-2", "down", stake=4.0, shares=20.0, price=0.4)

    manager.mark_price("up", 0.6)
    manager.mark_price("down", 0.35)

    assert manager.unrealized_pnl() == 0.0
    assert manager.open_positions_count() == 2


def test_unrealized_pnl_rounds_to_six_decimals():
    manager = PositionManager()
    manager.record_fill("market-1", "up", stake=1.0, shares=1.0, price=0.123456)

    manager.mark_price("up", 0.123457)

    assert manager.unrealized_pnl() == 0.000001


def test_unrealized_pnl_tracks_standalone_negative_position():
    manager = PositionManager()
    manager.record_fill("market-1", "up", stake=10.0, shares=3.0, price=0.5)

    manager.mark_price("up", 0.333333)

    assert manager.unrealized_pnl() == -0.500001


def test_record_fill_replaces_same_token_position():
    manager = PositionManager()
    manager.record_fill("old-market", "up", stake=5.0, shares=10.0, price=0.5)

    manager.record_fill("new-market", "up", stake=6.0, shares=12.0, price=0.55)

    assert manager.open_positions_count() == 1
    assert manager.positions["up"] == Position(
        market_id="new-market",
        token_id="up",
        stake=6.0,
        shares=12.0,
        entry_price=0.55,
        mark_price=0.55,
    )
