from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

from polybot.models import BotEvent, Decision, FeedAggregate, Market


DEFAULT_MARKET_STATUS = {
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
}


DEFAULT_RUNTIME_STATUS = {
    "state": "stopped",
    "message": "Bot is stopped.",
    "updated_at": None,
    "last_error": None,
}


DEFAULT_FEED_STATUS = {
    "btc_price": None,
    "fresh": None,
    "max_deviation_bps": None,
    "created_at": None,
    "target_price": None,
    "delta": None,
    "delta_pct": None,
}


class StateStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS market_status (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runtime_status (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feed_status (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL
                );
                """
            )

    def record_decision(self, decision: Decision) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO decisions (created_at, strategy, action, payload) VALUES (?, ?, ?, ?)",
                (
                    decision.created_at.isoformat(),
                    decision.strategy,
                    decision.action.value,
                    json.dumps(decision.to_dict(), sort_keys=True),
                ),
            )

    def record_event(self, event: BotEvent) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO events (created_at, level, message) VALUES (?, ?, ?)",
                (event.created_at.isoformat(), event.level, event.message),
            )

    def record_market_status(
        self,
        state: str,
        message: str,
        checked_at: datetime,
        market: Market | None = None,
    ) -> None:
        payload = DEFAULT_MARKET_STATUS | {
            "state": state,
            "message": message,
            "checked_at": checked_at.isoformat(),
        }
        if market is not None:
            payload |= {
                "market_id": market.market_id,
                "slug": market.slug,
                "question": market.question,
                "start_time": market.start_time.isoformat() if market.start_time else None,
                "end_time": market.end_time.isoformat(),
                "accepting_orders": market.accepting_orders,
                "tick_size": market.tick_size,
                "min_size": market.min_size,
            }

        self._upsert_singleton_payload("market_status", payload)

    def record_runtime_status(
        self,
        state: str,
        message: str,
        updated_at: datetime,
        last_error: str | None = None,
    ) -> None:
        payload = DEFAULT_RUNTIME_STATUS | {
            "state": state,
            "message": message,
            "updated_at": updated_at.isoformat(),
            "last_error": last_error,
        }
        self._upsert_singleton_payload("runtime_status", payload)

    def record_feed_status(self, feed: FeedAggregate, target_price: float | None) -> None:
        delta = (
            round(feed.reference_price - target_price, 6)
            if target_price is not None
            else None
        )
        delta_pct = round((delta / target_price) * 100, 6) if target_price else None
        payload = DEFAULT_FEED_STATUS | {
            "btc_price": feed.reference_price,
            "fresh": feed.fresh,
            "max_deviation_bps": feed.max_deviation_bps,
            "created_at": feed.created_at.isoformat(),
            "target_price": target_price,
            "delta": delta,
            "delta_pct": delta_pct,
        }
        self._upsert_singleton_payload("feed_status", payload)

    def _upsert_singleton_payload(self, table: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {table} (id, payload) VALUES (1, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (json.dumps(payload, sort_keys=True),),
            )

    def dashboard_snapshot(self) -> dict[str, Any]:
        """Return dashboard rows by event time, newest first, with id as tie-breaker."""
        with self.connect() as conn:
            decisions = conn.execute(
                "SELECT payload FROM decisions ORDER BY created_at DESC, id DESC LIMIT 20"
            ).fetchall()
            events = conn.execute(
                "SELECT created_at, level, message FROM events ORDER BY created_at DESC, id DESC LIMIT 50"
            ).fetchall()
            market_status = conn.execute(
                "SELECT payload FROM market_status WHERE id = 1"
            ).fetchone()
            runtime_status = conn.execute(
                "SELECT payload FROM runtime_status WHERE id = 1"
            ).fetchone()
            feed_status = conn.execute(
                "SELECT payload FROM feed_status WHERE id = 1"
            ).fetchone()

        return {
            "recent_decisions": [json.loads(row["payload"]) for row in decisions],
            "recent_events": [dict(row) for row in events],
            "market_status": json.loads(market_status["payload"])
            if market_status
            else DEFAULT_MARKET_STATUS,
            "runtime_status": json.loads(runtime_status["payload"])
            if runtime_status
            else DEFAULT_RUNTIME_STATUS,
            "feed_status": json.loads(feed_status["payload"])
            if feed_status
            else DEFAULT_FEED_STATUS,
        }
