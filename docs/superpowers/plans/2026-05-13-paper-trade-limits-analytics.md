# Paper Trade Limits Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Limit trades per event, persist paper fills, evaluate paper outcomes, and show paper performance analytics with an equity graph.

**Architecture:** Add paper-trade persistence to `StateStore` as the source of truth for paper performance. Keep `BotRunner` responsible for orchestration: evaluate old paper trades, enforce event limits, execute orders, then record filled paper trades. Expose analytics through the existing dashboard snapshot and render a lightweight SVG graph in the dashboard without adding a chart dependency.

**Tech Stack:** Python 3.14, SQLite via `sqlite3`, dataclasses/Pydantic, FastAPI dashboard, vanilla JavaScript/SVG, pytest, Ruff.

---

## File Structure

- Modify `src/polybot/config.py`: add `RiskSection.max_trades_per_event` and `RiskSection.max_event_exposure`.
- Modify `configs/bot.example.toml`: document conservative defaults.
- Modify `configs/bot.local.toml`: add defaults if the file exists and is tracked in the workspace.
- Modify `src/polybot/models.py`: add `PaperTrade` and `PaperTradeResult` dataclasses.
- Modify `src/polybot/state_store.py`: add `paper_trades` table, journal methods, evaluation methods, analytics aggregation.
- Modify `src/polybot/bot.py`: evaluate open paper trades, enforce per-event limits, record paper fills.
- Modify `src/polybot/dashboard/app.py`: include paper analytics in `/api/snapshot`.
- Modify `src/polybot/dashboard/static/index.html`: add Analytics tab and graph container.
- Modify `src/polybot/dashboard/static/app.js`: render analytics metrics, recent trades, and SVG equity curve.
- Modify `src/polybot/dashboard/static/styles.css`: style analytics cards and graph.
- Modify tests under `tests/`: add focused coverage for config, store, bot behavior, analytics, and dashboard.

---

### Task 1: Config For Event Trade Limits

**Files:**
- Modify: `src/polybot/config.py`
- Modify: `configs/bot.example.toml`
- Modify: `configs/bot.local.toml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config test**

Add this test to `tests/test_config.py`:

```python
def test_risk_config_accepts_event_trade_limits():
    data = _valid_config_data()
    data["risk"]["max_trades_per_event"] = 2
    data["risk"]["max_event_exposure"] = 12.5

    config = BotConfig.model_validate(data)

    assert config.risk.max_trades_per_event == 2
    assert config.risk.max_event_exposure == 12.5
```

If `_valid_config_data()` is not present, create it by extracting the existing valid config dictionary in `tests/test_config.py` into a helper named `_valid_config_data()`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_config.py::test_risk_config_accepts_event_trade_limits -v
```

Expected: FAIL because `RiskSection` does not expose the two fields.

- [ ] **Step 3: Add risk fields**

In `src/polybot/config.py`, update `RiskSection`:

```python
class RiskSection(BaseModel):
    max_stake: float = Field(gt=0.0)
    max_daily_loss: float = Field(gt=0.0)
    max_spread: float = Field(ge=0.0)
    min_liquidity: float = Field(gt=0.0)
    min_edge: float = Field(ge=0.0)
    max_feed_age_ms: int = Field(gt=0)
    max_feed_deviation_bps: int = Field(ge=0)
    max_open_positions: int = Field(default=1, ge=0)
    max_open_orders: int = Field(default=2, ge=0)
    max_trades_per_event: int = Field(default=1, ge=0)
    max_event_exposure: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def default_event_exposure(self) -> "RiskSection":
        if self.max_event_exposure is None:
            self.max_event_exposure = self.max_stake
        return self
```

Keep the existing `model_validator` import already used in this file.

- [ ] **Step 4: Add config defaults**

In `configs/bot.example.toml`, add under `[risk]`:

```toml
max_trades_per_event = 1
max_event_exposure = 10.0
```

In `configs/bot.local.toml`, add the same keys under `[risk]` if they are not already present.

- [ ] **Step 5: Run config tests**

Run:

```bash
uv run pytest tests/test_config.py -q
uv run ruff check src/polybot/config.py tests/test_config.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/polybot/config.py configs/bot.example.toml configs/bot.local.toml tests/test_config.py
git commit -m "feat: add event trade limit config"
```

---

### Task 2: Paper Trade Journal Persistence

**Files:**
- Modify: `src/polybot/models.py`
- Modify: `src/polybot/state_store.py`
- Test: `tests/test_state_store.py`

- [ ] **Step 1: Write failing paper trade store test**

Add imports in `tests/test_state_store.py`:

```python
from polybot.models import PaperTrade
```

Add this test:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_state_store.py::test_state_store_records_and_lists_paper_trades -v
```

Expected: FAIL because `PaperTrade` and journal methods do not exist.

- [ ] **Step 3: Add PaperTrade model**

In `src/polybot/models.py`, add:

```python
@dataclass(frozen=True)
class PaperTrade:
    id: int | None
    created_at: datetime
    event_slug: str
    market_id: str
    token_id: str
    action: str
    strategy: str
    reason_code: str
    stake: float
    price: float
    shares: float
    status: str
    estimated_probability: float | None
    market_probability: float | None
    edge: float | None
    target_price: float
    btc_price_at_entry: float
    event_end_time: datetime
```

- [ ] **Step 4: Add table and serialization helpers**

In `src/polybot/state_store.py`, import `PaperTrade` and add table DDL inside `initialize()`:

```sql
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
```

Add methods:

```python
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

def list_paper_trades(self, limit: int = 100) -> list[dict[str, Any]]:
    with self.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM paper_trades ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
```

- [ ] **Step 5: Run store tests**

Run:

```bash
uv run pytest tests/test_state_store.py::test_state_store_records_and_lists_paper_trades -v
uv run pytest tests/test_state_store.py -q
uv run ruff check src/polybot/models.py src/polybot/state_store.py tests/test_state_store.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/polybot/models.py src/polybot/state_store.py tests/test_state_store.py
git commit -m "feat: add paper trade journal"
```

---

### Task 3: Record Paper Fills And Enforce Event Limits

**Files:**
- Modify: `src/polybot/bot.py`
- Modify: `src/polybot/state_store.py`
- Test: `tests/test_bot_loop.py`
- Test: `tests/test_state_store.py`

- [ ] **Step 1: Add store count/exposure test**

Add this test to `tests/test_state_store.py`:

```python
def test_state_store_counts_event_trades_and_exposure(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    created_at = datetime(2026, 5, 13, 20, 20, tzinfo=UTC)
    end_time = datetime(2026, 5, 13, 20, 25, tzinfo=UTC)
    trade = PaperTrade(
        None, created_at, "slug-1", "0xmarket", "up", "BUY_UP", "baseline_momentum",
        "momentum_up", 5.0, 0.5, 10.0, "filled", 0.7, 0.5, 0.2, 100.0, 101.0, end_time
    )

    store.record_paper_trade(trade)

    assert store.count_paper_trades_for_event("slug-1") == 1
    assert store.paper_event_exposure("slug-1") == 5.0
```

- [ ] **Step 2: Add bot limit tests**

Add this test to `tests/test_bot_loop.py`:

```python
@pytest.mark.asyncio
async def test_bot_runner_blocks_second_trade_in_same_event(tmp_path):
    execution = FakeExecution()
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FakeOrderbookClient(),
        execution=execution,
        store_path=tmp_path / "bot.sqlite3",
        reference_start_price=100.0,
        latest_feed=_feed(),
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))
    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, 30, tzinfo=UTC))

    snapshot = runner.store.dashboard_snapshot()
    assert len(execution.orders) == 1
    assert snapshot["recent_events"][0]["message"] == (
        "risk gate blocked: event_trade_limit_reached"
    )
```

Add a different-event allowance test:

```python
@pytest.mark.asyncio
async def test_bot_runner_allows_trade_in_different_event(tmp_path):
    now = datetime(2026, 5, 12, 21, 0, tzinfo=UTC)
    first_market = Market("m1", "Bitcoin Up or Down", "slug-1", "up", "down", now, now + timedelta(minutes=5), 0.01, 5.0, True)
    second_market = Market("m2", "Bitcoin Up or Down", "slug-2", "up", "down", now + timedelta(minutes=5), now + timedelta(minutes=10), 0.01, 5.0, True)
    market_discovery = FakeMarketDiscovery(market=first_market)
    execution = FakeExecution()
    runner = BotRunner(
        config=_config(),
        market_discovery=market_discovery,
        orderbook_client=FakeOrderbookClient(),
        execution=execution,
        store_path=tmp_path / "bot.sqlite3",
        reference_start_price=100.0,
        latest_feed=_feed(),
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))
    market_discovery.market = second_market
    runner.latest_feed = _feed()
    await runner.run_once(now=datetime(2026, 5, 12, 21, 8, tzinfo=UTC))

    assert len(execution.orders) == 2
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_state_store.py::test_state_store_counts_event_trades_and_exposure tests/test_bot_loop.py::test_bot_runner_blocks_second_trade_in_same_event tests/test_bot_loop.py::test_bot_runner_allows_trade_in_different_event -v
```

Expected: FAIL because count/exposure methods and bot journal enforcement are missing.

- [ ] **Step 4: Add store helpers**

In `src/polybot/state_store.py`, add:

```python
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
            "SELECT COALESCE(SUM(stake), 0) AS exposure FROM paper_trades WHERE event_slug = ? AND status = 'filled' AND resolved_at IS NULL",
            (event_slug,),
        ).fetchone()
    return float(row["exposure"])
```

- [ ] **Step 5: Enforce limits and record fills**

In `src/polybot/bot.py`, import `PaperTrade`. After risk gate accepts and before stake calculation, add:

```python
event_trade_count = self.store.count_paper_trades_for_event(market.slug)
if event_trade_count >= self.config.risk.max_trades_per_event:
    self._record_event("info", "risk gate blocked: event_trade_limit_reached", now)
    return
```

After `stake = calculate_stake(...)`, add exposure check:

```python
event_exposure = self.store.paper_event_exposure(market.slug)
if event_exposure + stake > self.config.risk.max_event_exposure:
    self._record_event("info", "risk gate blocked: event_exposure_limit_reached", now)
    return
```

After a filled result and `self.positions.record_fill(...)`, record the paper trade:

```python
if result.get("mode") == "paper":
    self.store.record_paper_trade(
        PaperTrade(
            id=None,
            created_at=now,
            event_slug=market.slug,
            market_id=result["market_id"],
            token_id=result["token_id"],
            action=decision.action.value,
            strategy=decision.strategy,
            reason_code=decision.reason_code,
            stake=result["stake"],
            price=result["price"],
            shares=result["shares"],
            status=result["status"],
            estimated_probability=decision.estimated_probability,
            market_probability=decision.market_probability,
            edge=decision.edge,
            target_price=self.reference_start_price,
            btc_price_at_entry=self.latest_feed.reference_price,
            event_end_time=market.end_time,
        )
    )
```

- [ ] **Step 6: Run tests**

Run:

```bash
uv run pytest tests/test_state_store.py::test_state_store_counts_event_trades_and_exposure tests/test_bot_loop.py::test_bot_runner_blocks_second_trade_in_same_event tests/test_bot_loop.py::test_bot_runner_allows_trade_in_different_event -v
uv run pytest tests/test_bot_loop.py tests/test_state_store.py -q
uv run ruff check src/polybot/bot.py src/polybot/state_store.py tests/test_bot_loop.py tests/test_state_store.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/polybot/bot.py src/polybot/state_store.py tests/test_bot_loop.py tests/test_state_store.py
git commit -m "feat: enforce paper event trade limits"
```

---

### Task 4: Evaluate Open Paper Trades

**Files:**
- Modify: `src/polybot/state_store.py`
- Modify: `src/polybot/bot.py`
- Test: `tests/test_state_store.py`
- Test: `tests/test_bot_loop.py`

- [ ] **Step 1: Add evaluation tests**

Add to `tests/test_state_store.py`:

```python
def test_state_store_evaluates_paper_trade_win_and_loss(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    created_at = datetime(2026, 5, 13, 20, 20, tzinfo=UTC)
    end_time = datetime(2026, 5, 13, 20, 25, tzinfo=UTC)
    up_trade = PaperTrade(None, created_at, "slug-1", "0xmarket", "up", "BUY_UP", "late_window_5m", "late_window_high_confidence", 5.0, 0.5, 10.0, "filled", 0.7, 0.5, 0.2, 100.0, 101.0, end_time)
    down_trade = PaperTrade(None, created_at, "slug-1", "0xmarket", "down", "BUY_DOWN", "late_window_5m", "late_window_high_confidence", 5.0, 0.5, 10.0, "filled", 0.7, 0.5, 0.2, 100.0, 99.0, end_time)
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
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run pytest tests/test_state_store.py::test_state_store_evaluates_paper_trade_win_and_loss -v
```

Expected: FAIL because `evaluate_open_paper_trades()` does not exist.

- [ ] **Step 3: Implement evaluation**

In `src/polybot/state_store.py`, add:

```python
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
        for row in rows:
            action = row["action"]
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
    return len(rows)
```

- [ ] **Step 4: Call evaluation from BotRunner**

In `src/polybot/bot.py`, immediately after confirming `latest_feed` exists, add:

```python
self.store.evaluate_open_paper_trades(now, self.latest_feed.reference_price)
```

This uses the current cycle's BTC feed as the pragmatic final price source for ended events.

- [ ] **Step 5: Add bot evaluation regression**

Add to `tests/test_bot_loop.py`:

```python
@pytest.mark.asyncio
async def test_bot_runner_evaluates_open_paper_trades(tmp_path):
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(market=None),
        orderbook_client=FakeOrderbookClient(),
        execution=FakeExecution(),
        store_path=tmp_path / "bot.sqlite3",
        latest_feed=_feed(),
    )
    end_time = datetime(2026, 5, 12, 21, 1, tzinfo=UTC)
    runner.store.record_paper_trade(
        PaperTrade(
            None, datetime(2026, 5, 12, 21, 0, tzinfo=UTC), "old-slug", "m", "up",
            "BUY_UP", "baseline_momentum", "momentum_up", 5.0, 0.5, 10.0, "filled",
            0.7, 0.5, 0.2, 100.0, 100.5, end_time
        )
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    assert runner.store.list_paper_trades()[0]["outcome"] == "win"
```

Import `PaperTrade` in `tests/test_bot_loop.py`.

- [ ] **Step 6: Run tests**

Run:

```bash
uv run pytest tests/test_state_store.py::test_state_store_evaluates_paper_trade_win_and_loss tests/test_bot_loop.py::test_bot_runner_evaluates_open_paper_trades -v
uv run pytest tests/test_bot_loop.py tests/test_state_store.py -q
uv run ruff check src/polybot/bot.py src/polybot/state_store.py tests/test_bot_loop.py tests/test_state_store.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/polybot/bot.py src/polybot/state_store.py tests/test_bot_loop.py tests/test_state_store.py
git commit -m "feat: evaluate paper trade outcomes"
```

---

### Task 5: Paper Analytics Summary

**Files:**
- Modify: `src/polybot/state_store.py`
- Modify: `src/polybot/dashboard/app.py`
- Test: `tests/test_state_store.py`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Add analytics aggregation test**

Add to `tests/test_state_store.py`:

```python
def test_state_store_returns_paper_analytics_summary(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    created_at = datetime(2026, 5, 13, 20, 20, tzinfo=UTC)
    end_time = datetime(2026, 5, 13, 20, 25, tzinfo=UTC)
    store.record_paper_trade(PaperTrade(None, created_at, "slug-1", "0xmarket", "up", "BUY_UP", "late_window_5m", "late_window_high_confidence", 5.0, 0.5, 10.0, "filled", 0.7, 0.5, 0.2, 100.0, 101.0, end_time))
    store.record_paper_trade(PaperTrade(None, created_at, "slug-2", "0xmarket", "down", "BUY_DOWN", "baseline_momentum", "momentum_down", 5.0, 0.5, 10.0, "filled", 0.6, 0.5, 0.1, 100.0, 99.0, end_time))
    store.evaluate_open_paper_trades(datetime(2026, 5, 13, 20, 26, tzinfo=UTC), 101.0)

    analytics = store.paper_analytics()

    assert analytics["total_trades"] == 2
    assert analytics["resolved_trades"] == 2
    assert analytics["winning_trades"] == 1
    assert analytics["losing_trades"] == 1
    assert analytics["win_rate"] == 0.5
    assert analytics["total_pnl"] == 0.0
    assert analytics["average_edge"] == 0.15
    assert analytics["by_strategy"]["late_window_5m"]["trades"] == 1
    assert len(analytics["equity_curve"]) == 2
    assert analytics["equity_curve"][-1]["cumulative_pnl"] == 0.0
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run pytest tests/test_state_store.py::test_state_store_returns_paper_analytics_summary -v
```

Expected: FAIL because `paper_analytics()` does not exist.

- [ ] **Step 3: Implement analytics**

In `src/polybot/state_store.py`, add:

```python
def paper_analytics(self) -> dict[str, Any]:
    trades = self.list_paper_trades(limit=1000)
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
```

- [ ] **Step 4: Expose analytics in dashboard snapshot**

In `src/polybot/dashboard/app.py`, inside `/api/snapshot` before returning `data`, add:

```python
data["paper_analytics"] = store.paper_analytics()
```

- [ ] **Step 5: Add dashboard API test**

Add to `tests/test_dashboard.py`:

```python
def test_dashboard_snapshot_includes_paper_analytics(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    app = create_dashboard_app(store, dashboard_config_for_test(), control_service=None)
    client = TestClient(app)

    response = client.get("/api/snapshot")

    assert response.status_code == 200
    assert response.json()["paper_analytics"]["total_trades"] == 0
    assert response.json()["paper_analytics"]["equity_curve"] == []
```

- [ ] **Step 6: Run tests**

Run:

```bash
uv run pytest tests/test_state_store.py::test_state_store_returns_paper_analytics_summary tests/test_dashboard.py::test_dashboard_snapshot_includes_paper_analytics -v
uv run pytest tests/test_state_store.py tests/test_dashboard.py -q
uv run ruff check src/polybot/state_store.py src/polybot/dashboard/app.py tests/test_state_store.py tests/test_dashboard.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/polybot/state_store.py src/polybot/dashboard/app.py tests/test_state_store.py tests/test_dashboard.py
git commit -m "feat: expose paper trade analytics"
```

---

### Task 6: Dashboard Analytics Graph

**Files:**
- Modify: `src/polybot/dashboard/static/index.html`
- Modify: `src/polybot/dashboard/static/app.js`
- Modify: `src/polybot/dashboard/static/styles.css`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Add failing dashboard HTML test assertions**

In `tests/test_dashboard.py`, extend `test_dashboard_root_contains_tabs_controls_and_settings`:

```python
    assert 'data-tab-target="analytics"' in html
    assert 'id="paper-total-pnl"' in html
    assert 'id="paper-win-rate"' in html
    assert 'id="paper-trade-counts"' in html
    assert 'id="paper-average-edge"' in html
    assert 'id="equity-curve"' in html
    assert 'id="paper-trades"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_dashboard.py::test_dashboard_root_contains_tabs_controls_and_settings -v
```

Expected: FAIL because the Analytics UI does not exist.

- [ ] **Step 3: Add Analytics tab HTML**

In `src/polybot/dashboard/static/index.html`, add a new tab button:

```html
<button
  class="tab"
  type="button"
  id="analytics-tab"
  role="tab"
  aria-selected="false"
  aria-controls="analytics-panel"
  data-tab-target="analytics"
>
  Analytics
</button>
```

Add a new panel before Logs:

```html
<section
  class="tab-panel"
  id="analytics-panel"
  role="tabpanel"
  aria-labelledby="analytics-tab"
  data-tab-panel="analytics"
>
  <section class="metrics" aria-label="Paper analytics metrics">
    <article class="metric"><span>Paper P/L</span><strong id="paper-total-pnl">$0.00</strong></article>
    <article class="metric"><span>Win Rate</span><strong id="paper-win-rate">0.0%</strong></article>
    <article class="metric"><span>Trades</span><strong id="paper-trade-counts">0 / 0</strong></article>
    <article class="metric"><span>Average Edge</span><strong id="paper-average-edge">-</strong></article>
  </section>
  <section class="grid">
    <article class="panel">
      <div class="panel-heading">
        <h2>Equity Curve</h2>
        <span id="equity-point-count">0</span>
      </div>
      <div class="chart" id="equity-curve" aria-label="Paper equity curve"></div>
    </article>
    <article class="panel">
      <div class="panel-heading">
        <h2>Paper Trades</h2>
        <span id="paper-trade-count">0</span>
      </div>
      <ul class="list" id="paper-trades"></ul>
    </article>
  </section>
</section>
```

- [ ] **Step 4: Render analytics in JavaScript**

In `src/polybot/dashboard/static/app.js`, add constants:

```javascript
const paperTotalPnl = document.querySelector("#paper-total-pnl");
const paperWinRate = document.querySelector("#paper-win-rate");
const paperTradeCounts = document.querySelector("#paper-trade-counts");
const paperAverageEdge = document.querySelector("#paper-average-edge");
const equityCurve = document.querySelector("#equity-curve");
const equityPointCount = document.querySelector("#equity-point-count");
const paperTradeCount = document.querySelector("#paper-trade-count");
const paperTradesList = document.querySelector("#paper-trades");
```

Add:

```javascript
function renderEquityCurve(points) {
  if (!equityCurve) return;
  equityCurve.innerHTML = "";
  if (!points || points.length === 0) {
    equityCurve.classList.add("is-empty");
    equityCurve.textContent = "No resolved paper trades yet.";
    setText(equityPointCount, "0");
    return;
  }
  equityCurve.classList.remove("is-empty");
  setText(equityPointCount, String(points.length));
  const width = 640;
  const height = 220;
  const values = points.map((point) => Number(point.cumulative_pnl));
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const span = max - min || 1;
  const path = values
    .map((value, index) => {
      const x = points.length === 1 ? width : (index / (points.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
  const zeroY = height - ((0 - min) / span) * height;
  equityCurve.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Cumulative paper P/L">
      <line x1="0" y1="${zeroY.toFixed(2)}" x2="${width}" y2="${zeroY.toFixed(2)}" class="zero-line"></line>
      <path d="${path}" class="${values.at(-1) >= 0 ? "positive-line" : "negative-line"}"></path>
    </svg>
  `;
}

function renderPaperTrades(trades) {
  if (!paperTradesList) return;
  setText(paperTradeCount, String((trades || []).length));
  paperTradesList.innerHTML = "";
  if (!trades || trades.length === 0) {
    renderEmpty(paperTradesList, "No paper trades recorded yet.");
    return;
  }
  for (const trade of trades) {
    const pnl = trade.pnl === null || trade.pnl === undefined ? "open" : formatCurrency(trade.pnl, true);
    paperTradesList.appendChild(
      createRow(
        `${trade.action || "TRADE"} ${pnl}`,
        `${trade.strategy || "-"} / ${trade.reason_code || "-"}`,
        trade.created_at || "",
      ),
    );
  }
}

function renderPaperAnalytics(analytics) {
  const data = analytics || {};
  setText(paperTotalPnl, formatCurrency(data.total_pnl || 0, true));
  setText(paperWinRate, `${(Number(data.win_rate || 0) * 100).toFixed(1)}%`);
  setText(paperTradeCounts, `${data.open_trades || 0} open / ${data.resolved_trades || 0} resolved`);
  setText(paperAverageEdge, data.average_edge === undefined ? "-" : Number(data.average_edge).toFixed(4));
  renderEquityCurve(data.equity_curve || []);
  renderPaperTrades(data.recent_paper_trades || []);
}
```

Call it in `refreshSnapshot()`:

```javascript
renderPaperAnalytics(snapshot.paper_analytics);
```

- [ ] **Step 5: Add graph styles**

In `src/polybot/dashboard/static/styles.css`, add:

```css
.chart {
  min-height: 260px;
  padding: 18px;
}

.chart.is-empty {
  display: grid;
  place-items: center;
  color: var(--muted);
  font-weight: 700;
}

.chart svg {
  display: block;
  width: 100%;
  height: auto;
  min-height: 220px;
}

.zero-line {
  stroke: var(--border);
  stroke-width: 2;
}

.positive-line,
.negative-line {
  fill: none;
  stroke-width: 4;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.positive-line {
  stroke: #0f766e;
}

.negative-line {
  stroke: #b42318;
}
```

- [ ] **Step 6: Run dashboard checks**

Run:

```bash
uv run pytest tests/test_dashboard.py -q
node --check src/polybot/dashboard/static/app.js
uv run ruff check tests/test_dashboard.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/polybot/dashboard/static/index.html src/polybot/dashboard/static/app.js src/polybot/dashboard/static/styles.css tests/test_dashboard.py
git commit -m "feat: add paper analytics dashboard"
```

---

### Task 7: Full Verification

**Files:**
- Verify all modified files.

- [ ] **Step 1: Run full tests**

Run:

```bash
uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run lint**

Run:

```bash
uv run ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 3: Run JS syntax check**

Run:

```bash
node --check src/polybot/dashboard/static/app.js
```

Expected: no output and exit code 0.

- [ ] **Step 4: Run one paper bot cycle**

Run:

```bash
uv run polybot run --config configs/bot.local.toml
```

Expected: command exits 0 with `Completed one bot cycle.` or records a clean no-trade/block event without Python traceback.

- [ ] **Step 5: Inspect working tree**

Run:

```bash
git status --short
```

Expected: clean working tree after commits. If verification required fixes, commit them with:

```bash
git add src/polybot tests configs docs
git commit -m "fix: complete paper analytics verification"
```

---

## Self-Review Notes

- Spec coverage: event trade limits, paper journal, evaluation, analytics API, dashboard graph, error handling, and full verification are covered.
- Scope control: this plan does not implement external historical replay or Data API reconciliation; it builds the paper journal foundation first.
- Type consistency: `PaperTrade`, `record_paper_trade`, `evaluate_open_paper_trades`, and `paper_analytics` are introduced before bot/dashboard tasks use them.
- UI choice: the graph uses inline SVG in `app.js`, avoiding a new dependency.
