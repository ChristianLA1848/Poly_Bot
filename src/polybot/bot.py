from datetime import UTC, datetime
from inspect import isawaitable
from pathlib import Path
from typing import Any

from polybot.audit_log import AuditLog
from polybot.config import BotConfig
from polybot.market_discovery import MarketDiscovery
from polybot.models import BotEvent, DecisionAction, FeedAggregate, Market, OrderbookSnapshot
from polybot.orderbook import OrderbookClient
from polybot.positions import PositionManager
from polybot.risk import RiskGate
from polybot.staking import calculate_stake
from polybot.state_store import StateStore
from polybot.strategies.base import StrategyContext, load_strategy


class BotRunner:
    def __init__(
        self,
        config: BotConfig,
        market_discovery: Any | None = None,
        orderbook_client: Any | None = None,
        execution: Any | None = None,
        store_path: str | Path = "./data/polybot.sqlite3",
        reference_start_price: float | None = None,
        latest_feed: FeedAggregate | None = None,
        audit_log_path: str | Path | None = None,
    ) -> None:
        self.config = config
        self.market_discovery = market_discovery or MarketDiscovery()
        self.orderbook_client = orderbook_client or OrderbookClient()
        self.execution = execution
        self.store = StateStore(store_path)
        self.store.initialize()
        self.positions = PositionManager()
        self.reference_start_price = reference_start_price
        self.reference_market_slug: str | None = None
        self.latest_feed = latest_feed
        self.audit_log = AuditLog(audit_log_path) if audit_log_path is not None else None

    async def __aenter__(self) -> "BotRunner":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._close_if_available(self.market_discovery)
        await self._close_if_available(self.orderbook_client)

    async def run_once(self, now: datetime | None = None) -> None:
        now = now or datetime.now(tz=UTC)

        if self.latest_feed is None:
            self._record_event("warning", "no feed aggregate available", now)
            return

        self.store.record_feed_status(self.latest_feed, self.reference_start_price)
        market = await self.market_discovery.find_btc_5m_market()
        if market is None:
            self.store.record_market_status("not_found", "market not found", now)
            self._record_event("warning", "market not found", now)
            return
        if not market.accepting_orders:
            self.store.record_market_status(
                "not_accepting_orders",
                "market not accepting orders",
                now,
                market,
            )
            self._record_event("warning", "market not accepting orders", now)
            return
        self.store.record_market_status("ready", "market ready", now, market)

        if self.reference_market_slug != market.slug:
            previous_market_slug = self.reference_market_slug
            self.reference_market_slug = market.slug
            if market.price_to_beat is not None:
                self.reference_start_price = market.price_to_beat
            elif previous_market_slug is not None:
                self.reference_start_price = None
        if self.reference_start_price is None:
            self.reference_start_price = self.latest_feed.reference_price
        self.store.record_feed_status(self.latest_feed, self.reference_start_price)

        try:
            up_book = await self.orderbook_client.get_book(market.up_token_id)
            down_book = await self.orderbook_client.get_book(market.down_token_id)
        except ValueError as exc:
            self._record_event("warning", f"orderbook unavailable: {exc}", now)
            return
        strategy = load_strategy(self.config.strategy.name)
        context = StrategyContext(
            market=market,
            reference_start_price=self.reference_start_price,
            feed=self.latest_feed,
            up_book=up_book,
            down_book=down_book,
            now=now,
        )
        decision = strategy.decide(context)
        self.store.record_decision(decision)
        self._append_audit(
            "decision",
            {
                "decision": decision,
                "feed": self.latest_feed,
                "market": market,
                "created_at": now,
            },
        )

        if self._has_unknown_trade_token(decision.action, decision.token_id, market):
            self._record_event("error", "strategy returned unknown token", now)
            return

        selected_book = self._selected_book(decision.token_id, market.up_token_id, up_book, down_book)
        risk_result = RiskGate(self.config.risk).evaluate(
            decision,
            self.latest_feed,
            selected_book,
            today_pnl=self.positions.unrealized_pnl(),
            open_positions=self.positions.open_positions_count(),
            open_orders=0,
        )
        if not risk_result.accepted:
            self._append_audit(
                "risk_block",
                {
                    "reason": risk_result.reason,
                    "decision": decision,
                    "feed": self.latest_feed,
                    "book": selected_book,
                    "created_at": now,
                },
            )
            self._record_event("info", f"risk gate blocked: {risk_result.reason}", now)
            return

        stake = calculate_stake(self.config.staking, decision, self.config.risk.max_stake)
        if self.execution is None:
            self._record_event("error", "execution engine missing", now)
            return

        result = await self.execution.place_order(decision, stake)
        self._append_audit(
            "order_result",
            {
                "decision": decision,
                "stake": stake,
                "result": result,
                "created_at": now,
            },
        )
        if result.get("status") == "filled":
            self.positions.record_fill(
                result["market_id"],
                result["token_id"],
                result["stake"],
                result["shares"],
                result["price"],
            )
        self._record_event("info", f"order result: {result.get('status')}", now)

    def _record_event(self, level: str, message: str, created_at: datetime) -> None:
        event = BotEvent(level=level, message=message, created_at=created_at)
        self.store.record_event(event)
        if level in {"warning", "error"}:
            self._append_audit("event", {"event": event})

    def _append_audit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.audit_log is None:
            return
        self.audit_log.append(event_type, payload)

    async def _close_if_available(self, client: Any) -> None:
        close = getattr(client, "aclose", None)
        if close is None:
            return

        result = close()
        if isawaitable(result):
            await result

    def _has_unknown_trade_token(
        self,
        action: DecisionAction,
        token_id: str,
        market: Market,
    ) -> bool:
        if action not in {DecisionAction.BUY_UP, DecisionAction.BUY_DOWN, DecisionAction.SELL}:
            return False
        return token_id not in {market.up_token_id, market.down_token_id}

    def _selected_book(
        self,
        token_id: str,
        up_token_id: str,
        up_book: OrderbookSnapshot,
        down_book: OrderbookSnapshot,
    ) -> OrderbookSnapshot:
        if token_id == up_token_id:
            return up_book
        if token_id == down_book.token_id:
            return down_book
        return up_book
