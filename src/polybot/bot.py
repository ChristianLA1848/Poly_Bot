from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from polybot.config import BotConfig
from polybot.market_discovery import MarketDiscovery
from polybot.models import BotEvent, FeedAggregate, OrderbookSnapshot
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
    ) -> None:
        self.config = config
        self.market_discovery = market_discovery or MarketDiscovery()
        self.orderbook_client = orderbook_client or OrderbookClient()
        self.execution = execution
        self.store = StateStore(store_path)
        self.store.initialize()
        self.positions = PositionManager()
        self.reference_start_price = reference_start_price
        self.latest_feed = latest_feed

    async def run_once(self, now: datetime | None = None) -> None:
        now = now or datetime.now(tz=UTC)

        if self.latest_feed is None:
            self._record_event("warning", "no feed aggregate available", now)
            return

        market = await self.market_discovery.find_btc_5m_market()
        if market is None:
            self._record_event("warning", "market not found", now)
            return
        if not market.accepting_orders:
            self._record_event("warning", "market not accepting orders", now)
            return

        if self.reference_start_price is None:
            self.reference_start_price = self.latest_feed.reference_price

        up_book = await self.orderbook_client.get_book(market.up_token_id)
        down_book = await self.orderbook_client.get_book(market.down_token_id)
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
            self._record_event("info", f"risk gate blocked: {risk_result.reason}", now)
            return

        stake = calculate_stake(self.config.staking, decision, self.config.risk.max_stake)
        if self.execution is None:
            self._record_event("error", "execution engine missing", now)
            return

        result = await self.execution.place_order(decision, stake)
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
        self.store.record_event(BotEvent(level=level, message=message, created_at=created_at))

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
