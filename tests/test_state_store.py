from datetime import UTC, datetime
import json

from polybot.audit_log import AuditLog
from polybot.models import BotEvent, Decision, DecisionAction, FeedAggregate, FeedPrice
from polybot.state_store import StateStore


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

    assert snapshot == {"recent_decisions": [], "recent_events": []}


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
    }


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
