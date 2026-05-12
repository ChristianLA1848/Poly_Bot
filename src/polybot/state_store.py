import json
from pathlib import Path
import sqlite3
from typing import Any

from polybot.models import BotEvent, Decision


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

    def dashboard_snapshot(self) -> dict[str, Any]:
        with self.connect() as conn:
            decisions = conn.execute(
                "SELECT payload FROM decisions ORDER BY id DESC LIMIT 20"
            ).fetchall()
            events = conn.execute(
                "SELECT created_at, level, message FROM events ORDER BY id DESC LIMIT 50"
            ).fetchall()

        return {
            "recent_decisions": [json.loads(row["payload"]) for row in decisions],
            "recent_events": [dict(row) for row in events],
        }
