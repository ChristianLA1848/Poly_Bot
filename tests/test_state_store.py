from datetime import UTC, datetime
import json

import pytest

from polybot.audit_log import AuditLog
from polybot.config import (
    BotConfig,
    BotSection,
    ExitSection,
    LateWindowSection,
    RiskSection,
    StakingSection,
    StrategySection,
)
from polybot.models import (
    BotEvent,
    Decision,
    DecisionAction,
    FeedAggregate,
    FeedPrice,
    Market,
    PaperTrade,
)
from polybot.state_store import StateStore


def make_bot_config_for_test() -> BotConfig:
    return BotConfig(
        bot=BotSection(mode="paper", cycle_seconds=1),
        risk=RiskSection(
            max_stake=10,
            max_daily_loss=25,
            max_spread=0.04,
            min_liquidity=100,
            min_edge=0.03,
            max_feed_age_ms=2500,
            max_feed_deviation_bps=20,
        ),
        strategy=StrategySection(name="baseline_momentum"),
        staking=StakingSection(mode="fixed", fixed_stake=5),
        exit=ExitSection(mode="hold_to_resolution"),
        late_window=LateWindowSection(),
    )


def make_decision(
    *,
    action: DecisionAction = DecisionAction.BUY_UP,
    created_at: datetime = datetime(2026, 5, 12, tzinfo=UTC),
    market_id: str = "0xmarket",
    token_id: str = "123",
    reason: str = "momentum up",
) -> Decision:
    return Decision(
        strategy="baseline_momentum",
        action=action,
        market_id=market_id,
        token_id=token_id,
        target_price=0.62,
        estimated_probability=0.70,
        confidence=0.82,
        expected_return=0.08,
        max_slippage=0.01,
        reason=reason,
        created_at=created_at,
    )


def test_state_store_empty_snapshot(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()

    snapshot = store.dashboard_snapshot()

    assert snapshot == {
        "recent_decisions": [],
        "recent_events": [],
        "market_status": {
            "state": "unknown",
            "message": "No market checked yet.",
            "checked_at": None,
            "market_id": None,
            "slug": None,
            "question": None,
            "start_time": None,
            "end_time": None,
            "accepting_orders": None,
            "tick_size": None,
            "min_size": None,
            "market_profile": None,
        },
        "runtime_status": {
            "state": "stopped",
            "message": "Bot is stopped.",
            "updated_at": None,
            "last_error": None,
        },
        "feed_status": {
            "btc_price": None,
            "fresh": None,
            "max_deviation_bps": None,
            "created_at": None,
            "target_price": None,
            "delta": None,
            "delta_pct": None,
        },
    }


def test_state_store_empty_snapshot_includes_runtime_and_feed_defaults(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()

    snapshot = store.dashboard_snapshot()

    assert snapshot["runtime_status"] == {
        "state": "stopped",
        "message": "Bot is stopped.",
        "updated_at": None,
        "last_error": None,
    }
    assert snapshot["feed_status"] == {
        "btc_price": None,
        "fresh": None,
        "max_deviation_bps": None,
        "created_at": None,
        "target_price": None,
        "delta": None,
        "delta_pct": None,
    }


def test_state_store_records_runtime_status(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    updated_at = datetime(2026, 5, 13, 8, 0, tzinfo=UTC)

    store.record_runtime_status("running", "Bot loop running.", updated_at)

    assert store.dashboard_snapshot()["runtime_status"] == {
        "state": "running",
        "message": "Bot loop running.",
        "updated_at": updated_at.isoformat(),
        "last_error": None,
    }


def test_state_store_records_feed_status_with_target_delta(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    created_at = datetime(2026, 5, 13, 8, 0, tzinfo=UTC)
    feed = FeedAggregate(
        reference_price=103250.0,
        prices=[FeedPrice("coinbase", "BTC-USD", 103250.0, 1)],
        max_deviation_bps=1.4,
        fresh=True,
        created_at=created_at,
    )

    store.record_feed_status(feed, target_price=103000.0)

    assert store.dashboard_snapshot()["feed_status"] == {
        "btc_price": 103250.0,
        "fresh": True,
        "max_deviation_bps": 1.4,
        "created_at": created_at.isoformat(),
        "target_price": 103000.0,
        "delta": 250.0,
        "delta_pct": 0.242718,
    }


def test_state_store_returns_default_settings_when_unset(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    cfg = make_bot_config_for_test()

    assert store.get_settings(cfg) == cfg.model_dump(mode="json")


def test_state_store_records_settings_payload(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    cfg = make_bot_config_for_test()
    payload = cfg.model_copy(update={"bot": cfg.bot.model_copy(update={"mode": "live"})})

    store.record_settings(payload)

    assert store.get_settings(cfg)["bot"]["mode"] == "live"


def test_state_store_persists_settings_across_instances(tmp_path):
    db_path = tmp_path / "bot.sqlite3"
    store = StateStore(db_path)
    store.initialize()
    cfg = make_bot_config_for_test()
    payload = cfg.model_copy(update={"bot": cfg.bot.model_copy(update={"mode": "live"})})

    store.record_settings(payload)

    next_store = StateStore(db_path)
    assert next_store.get_settings(cfg)["bot"]["mode"] == "live"


def test_state_store_rejects_unknown_singleton_table(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()

    with pytest.raises(ValueError, match="unknown singleton table"):
        store._upsert_singleton_payload("decisions", {"state": "bad"})


def test_state_store_rounds_feed_delta_to_six_decimals(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    created_at = datetime(2026, 5, 13, 8, 0, tzinfo=UTC)
    feed = FeedAggregate(
        reference_price=103250.1234567,
        prices=[FeedPrice("coinbase", "BTC-USD", 103250.1234567, 1)],
        max_deviation_bps=1.4,
        fresh=True,
        created_at=created_at,
    )

    store.record_feed_status(feed, target_price=103000.0)

    assert store.dashboard_snapshot()["feed_status"]["delta"] == 250.123457


def test_state_store_records_decision_and_event(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()

    decision = make_decision()
    store.record_decision(decision)
    store.record_event(
        BotEvent(level="info", message="decision accepted", created_at=decision.created_at)
    )

    snapshot = store.dashboard_snapshot()

    assert snapshot["recent_decisions"][0]["action"] == "BUY_UP"
    assert snapshot["recent_events"][0]["message"] == "decision accepted"


def test_state_store_records_full_decision_payload(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    created_at = datetime(2026, 5, 12, 10, 5, tzinfo=UTC)
    decision = make_decision(
        action=DecisionAction.BUY_DOWN,
        created_at=created_at,
        market_id="0xother",
        token_id="456",
        reason="momentum down",
    )

    store.record_decision(decision)

    payload = store.dashboard_snapshot()["recent_decisions"][0]
    assert payload == {
        "strategy": "baseline_momentum",
        "action": "BUY_DOWN",
        "market_id": "0xother",
        "token_id": "456",
        "target_price": 0.62,
        "estimated_probability": 0.70,
        "confidence": 0.82,
        "expected_return": 0.08,
        "max_slippage": 0.01,
        "reason": "momentum down",
        "created_at": created_at.isoformat(),
        "reason_code": "",
        "market_probability": None,
        "edge": None,
    }


def test_state_store_records_and_lists_paper_trades(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    created_at = datetime(2026, 5, 13, 20, 20, tzinfo=UTC)
    end_time = datetime(2026, 5, 13, 20, 25, tzinfo=UTC)
    trade = PaperTrade(
        id=None,
        created_at=created_at,
        event_slug="btc-updown-5m-1",
        market_id="0xmarket",
        token_id="up",
        action="BUY_UP",
        strategy="late_window_5m",
        reason_code="late_window_high_confidence",
        stake=5.0,
        price=0.84,
        shares=5.952381,
        status="filled",
        estimated_probability=0.86,
        market_probability=0.84,
        edge=0.02,
        target_price=100.0,
        btc_price_at_entry=100.2,
        event_end_time=end_time,
    )

    trade_id = store.record_paper_trade(trade)

    trades = store.list_paper_trades()
    assert trade_id == 1
    assert len(trades) == 1
    assert trades[0]["id"] == 1
    assert trades[0]["event_slug"] == "btc-updown-5m-1"
    assert trades[0]["edge"] == 0.02
    assert trades[0]["resolved_at"] is None


def test_state_store_counts_event_trades_and_exposure(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    created_at = datetime(2026, 5, 13, 20, 20, tzinfo=UTC)
    end_time = datetime(2026, 5, 13, 20, 25, tzinfo=UTC)
    trade = PaperTrade(
        None,
        created_at,
        "slug-1",
        "0xmarket",
        "up",
        "BUY_UP",
        "baseline_momentum",
        "momentum_up",
        5.0,
        0.5,
        10.0,
        "filled",
        0.7,
        0.5,
        0.2,
        100.0,
        101.0,
        end_time,
    )

    store.record_paper_trade(trade)

    assert store.count_paper_trades_for_event("slug-1") == 1
    assert store.paper_event_exposure("slug-1") == 5.0


def test_state_store_evaluates_paper_trade_win_and_loss(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    created_at = datetime(2026, 5, 13, 20, 20, tzinfo=UTC)
    end_time = datetime(2026, 5, 13, 20, 25, tzinfo=UTC)
    up_trade = PaperTrade(
        None,
        created_at,
        "slug-1",
        "0xmarket",
        "up",
        "BUY_UP",
        "late_window_5m",
        "late_window_high_confidence",
        5.0,
        0.5,
        10.0,
        "filled",
        0.7,
        0.5,
        0.2,
        100.0,
        101.0,
        end_time,
    )
    down_trade = PaperTrade(
        None,
        created_at,
        "slug-1",
        "0xmarket",
        "down",
        "BUY_DOWN",
        "late_window_5m",
        "late_window_high_confidence",
        5.0,
        0.5,
        10.0,
        "filled",
        0.7,
        0.5,
        0.2,
        100.0,
        99.0,
        end_time,
    )
    store.record_paper_trade(up_trade)
    store.record_paper_trade(down_trade)

    evaluated = store.evaluate_open_paper_trades(
        now=datetime(2026, 5, 13, 20, 26, tzinfo=UTC),
        final_btc_price=101.0,
    )

    trades = sorted(store.list_paper_trades(), key=lambda row: row["id"])
    assert evaluated == 2
    assert trades[0]["outcome"] == "win"
    assert trades[0]["payout"] == 10.0
    assert trades[0]["pnl"] == 5.0
    assert trades[1]["outcome"] == "loss"
    assert trades[1]["payout"] == 0.0
    assert trades[1]["pnl"] == -5.0


def test_state_store_orders_snapshot_by_created_at_then_id(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    earlier = datetime(2026, 5, 12, 10, 0, tzinfo=UTC)
    later = datetime(2026, 5, 12, 10, 1, tzinfo=UTC)

    store.record_decision(make_decision(created_at=later, token_id="later"))
    store.record_decision(make_decision(created_at=earlier, token_id="earlier"))
    store.record_decision(make_decision(created_at=later, token_id="later-tie"))
    store.record_event(BotEvent(level="info", message="later", created_at=later))
    store.record_event(BotEvent(level="info", message="earlier", created_at=earlier))
    store.record_event(BotEvent(level="info", message="later tie", created_at=later))

    snapshot = store.dashboard_snapshot()

    assert [row["token_id"] for row in snapshot["recent_decisions"]] == [
        "later-tie",
        "later",
        "earlier",
    ]
    assert [row["message"] for row in snapshot["recent_events"]] == [
        "later tie",
        "later",
        "earlier",
    ]


def test_state_store_persists_across_instances(tmp_path):
    db_path = tmp_path / "bot.sqlite3"
    store = StateStore(db_path)
    store.initialize()
    decision = make_decision()
    store.record_decision(decision)
    store.record_event(
        BotEvent(level="info", message="decision accepted", created_at=decision.created_at)
    )

    next_store = StateStore(db_path)

    snapshot = next_store.dashboard_snapshot()
    assert snapshot["recent_decisions"][0]["market_id"] == "0xmarket"
    assert snapshot["recent_events"][0]["level"] == "info"


def test_state_store_records_market_status(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    start = datetime(2026, 5, 12, 21, 0, tzinfo=UTC)
    end = datetime(2026, 5, 12, 21, 5, tzinfo=UTC)
    checked_at = datetime(2026, 5, 12, 21, 3, tzinfo=UTC)
    market = Market(
        "0xmarket",
        "Bitcoin Up or Down - May 12, 9:00PM-9:05PM ET",
        "btc-updown-5m-1778619600",
        "up",
        "down",
        start,
        end,
        0.01,
        5.0,
        False,
    )

    store.record_market_status("not_accepting_orders", "market not accepting orders", checked_at, market)

    assert store.dashboard_snapshot()["market_status"] == {
        "state": "not_accepting_orders",
        "message": "market not accepting orders",
        "checked_at": checked_at.isoformat(),
        "market_id": "0xmarket",
        "slug": "btc-updown-5m-1778619600",
        "question": "Bitcoin Up or Down - May 12, 9:00PM-9:05PM ET",
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "accepting_orders": False,
        "tick_size": 0.01,
        "min_size": 5.0,
        "market_profile": "btc_5m",
    }


def test_audit_log_serializes_datetime_enum_and_dataclass_payloads(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    audit_log = AuditLog(log_path)
    feed_price = FeedPrice("coinbase", "BTC-USD", 103000.12, 1_778_520_000_000)
    created_at = datetime(2026, 5, 12, 11, 30, tzinfo=UTC)

    audit_log.append(
        "decision",
        {
            "created_at": created_at,
            "action": DecisionAction.BUY_UP,
            "feed_price": feed_price,
        },
    )

    record = json.loads(log_path.read_text(encoding="utf-8"))
    assert record == {
        "type": "decision",
        "payload": {
            "created_at": created_at.isoformat(),
            "action": "BUY_UP",
            "feed_price": {
                "source": "coinbase",
                "symbol": "BTC-USD",
                "value": 103000.12,
                "timestamp_ms": 1_778_520_000_000,
            },
        },
    }


def test_feed_aggregate_accepts_list_but_stores_tuple():
    prices = [FeedPrice("coinbase", "BTC-USD", 103000.12, 1_778_520_000_000)]
    aggregate = FeedAggregate(
        reference_price=103000.12,
        prices=prices,
        max_deviation_bps=1.2,
        fresh=True,
        created_at=datetime(2026, 5, 12, tzinfo=UTC),
    )

    prices.append(FeedPrice("kraken", "BTC-USD", 103001.0, 1_778_520_000_100))

    assert aggregate.prices == (
        FeedPrice("coinbase", "BTC-USD", 103000.12, 1_778_520_000_000),
    )
