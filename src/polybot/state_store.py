from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

from polybot.config import BotConfig
from polybot.models import BotEvent, Decision, FeedAggregate, Market, PaperTrade
from polybot.strategies.base import classify_market_profile


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
    "market_profile": None,
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


SINGLETON_TABLES = {"market_status", "runtime_status", "feed_status", "settings"}


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
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    event_slug TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    token_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    stake REAL NOT NULL,
                    price REAL NOT NULL,
                    shares REAL NOT NULL,
                    status TEXT NOT NULL,
                    estimated_probability REAL,
                    market_probability REAL,
                    edge REAL,
                    target_price REAL NOT NULL,
                    btc_price_at_entry REAL NOT NULL,
                    event_end_time TEXT NOT NULL,
                    resolved_at TEXT,
                    final_btc_price REAL,
                    outcome TEXT,
                    payout REAL,
                    pnl REAL,
                    pnl_pct REAL
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
                "market_profile": classify_market_profile(market),
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

    def record_paper_trade(self, trade: PaperTrade) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO paper_trades (
                    created_at, event_slug, market_id, token_id, action, strategy, reason_code,
                    stake, price, shares, status, estimated_probability, market_probability,
                    edge, target_price, btc_price_at_entry, event_end_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.created_at.isoformat(),
                    trade.event_slug,
                    trade.market_id,
                    trade.token_id,
                    trade.action,
                    trade.strategy,
                    trade.reason_code,
                    trade.stake,
                    trade.price,
                    trade.shares,
                    trade.status,
                    trade.estimated_probability,
                    trade.market_probability,
                    trade.edge,
                    trade.target_price,
                    trade.btc_price_at_entry,
                    trade.event_end_time.isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def list_paper_trades(self, limit: int | None = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if limit is None:
                rows = conn.execute(
                    "SELECT * FROM paper_trades ORDER BY created_at DESC, id DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM paper_trades ORDER BY created_at DESC, id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(row) for row in rows]

    def count_paper_trades_for_event(self, event_slug: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM paper_trades WHERE event_slug = ? AND status = 'filled'",
                (event_slug,),
            ).fetchone()
        return int(row["count"])

    def paper_event_exposure(self, event_slug: str) -> float:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(stake), 0) AS exposure
                FROM paper_trades
                WHERE event_slug = ? AND status = 'filled' AND resolved_at IS NULL
                """,
                (event_slug,),
            ).fetchone()
        return float(row["exposure"])

    def evaluate_open_paper_trades(self, now: datetime, final_btc_price: float) -> int:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM paper_trades
                WHERE resolved_at IS NULL
                  AND status = 'filled'
                  AND event_end_time <= ?
                ORDER BY event_end_time ASC, id ASC
                """,
                (now.isoformat(),),
            ).fetchall()
            evaluated = 0
            for row in rows:
                action = row["action"]
                if action not in {"BUY_UP", "BUY_DOWN"}:
                    conn.execute(
                        "INSERT INTO events (created_at, level, message) VALUES (?, ?, ?)",
                        (
                            now.isoformat(),
                            "warning",
                            f"skipped paper trade with unsupported action: {action}",
                        ),
                    )
                    continue
                target_price = float(row["target_price"])
                shares = float(row["shares"])
                stake = float(row["stake"])
                won = (
                    final_btc_price >= target_price
                    if action == "BUY_UP"
                    else final_btc_price < target_price
                )
                payout = round(shares * 1.0, 6) if won else 0.0
                pnl = round(payout - stake, 6)
                pnl_pct = round(pnl / stake, 6) if stake > 0 else None
                conn.execute(
                    """
                    UPDATE paper_trades
                    SET resolved_at = ?, final_btc_price = ?, outcome = ?, payout = ?, pnl = ?, pnl_pct = ?
                    WHERE id = ?
                    """,
                    (
                        now.isoformat(),
                        final_btc_price,
                        "win" if won else "loss",
                        payout,
                        pnl,
                        pnl_pct,
                        row["id"],
                    ),
                )
                evaluated += 1
        return evaluated

    def paper_analytics(self) -> dict[str, Any]:
        trades = self.list_paper_trades(limit=None)
        resolved = [trade for trade in trades if trade["resolved_at"] is not None]
        open_trades = [trade for trade in trades if trade["resolved_at"] is None]
        wins = [trade for trade in resolved if trade["outcome"] == "win"]
        losses = [trade for trade in resolved if trade["outcome"] == "loss"]
        total_pnl = round(sum(float(trade["pnl"] or 0) for trade in resolved), 6)
        average_pnl = round(total_pnl / len(resolved), 6) if resolved else 0.0
        edge_values = [float(trade["edge"]) for trade in trades if trade["edge"] is not None]
        average_edge = round(sum(edge_values) / len(edge_values), 6) if edge_values else 0.0

        by_strategy: dict[str, dict[str, Any]] = {}
        for trade in trades:
            strategy = trade["strategy"]
            bucket = by_strategy.setdefault(strategy, {"trades": 0, "pnl": 0.0})
            bucket["trades"] += 1
            bucket["pnl"] = round(bucket["pnl"] + float(trade["pnl"] or 0), 6)

        cumulative = 0.0
        equity_curve = []
        for trade in sorted(resolved, key=lambda row: (row["resolved_at"], row["id"])):
            pnl = float(trade["pnl"] or 0)
            cumulative = round(cumulative + pnl, 6)
            equity_curve.append(
                {
                    "resolved_at": trade["resolved_at"],
                    "pnl": pnl,
                    "cumulative_pnl": cumulative,
                }
            )

        return {
            "total_trades": len(trades),
            "open_trades": len(open_trades),
            "resolved_trades": len(resolved),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": round(len(wins) / len(resolved), 6) if resolved else 0.0,
            "total_pnl": total_pnl,
            "average_pnl": average_pnl,
            "average_edge": average_edge,
            "by_strategy": by_strategy,
            "equity_curve": equity_curve,
            "recent_paper_trades": trades[:20],
        }

    def get_settings(self, default_config: BotConfig) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT payload FROM settings WHERE id = 1").fetchone()
        if row is None:
            return default_config.model_dump(mode="json")
        return json.loads(row["payload"])

    def record_settings(self, config: BotConfig) -> None:
        self._upsert_singleton_payload("settings", config.model_dump(mode="json"))

    def _upsert_singleton_payload(self, table: str, payload: dict[str, Any]) -> None:
        if table not in SINGLETON_TABLES:
            raise ValueError("unknown singleton table")

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
