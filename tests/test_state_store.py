from datetime import UTC, datetime

from polybot.models import BotEvent, Decision, DecisionAction
from polybot.state_store import StateStore


def test_state_store_records_decision_and_event(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()

    decision = Decision(
        strategy="baseline_momentum",
        action=DecisionAction.BUY_UP,
        market_id="0xmarket",
        token_id="123",
        target_price=0.62,
        estimated_probability=0.70,
        confidence=0.82,
        expected_return=0.08,
        max_slippage=0.01,
        reason="momentum up",
        created_at=datetime(2026, 5, 12, tzinfo=UTC),
    )
    store.record_decision(decision)
    store.record_event(BotEvent(level="info", message="decision accepted", created_at=decision.created_at))

    snapshot = store.dashboard_snapshot()

    assert snapshot["recent_decisions"][0]["action"] == "BUY_UP"
    assert snapshot["recent_events"][0]["message"] == "decision accepted"
