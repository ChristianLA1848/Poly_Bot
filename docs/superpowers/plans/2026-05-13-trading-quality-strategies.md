# Trading Quality Strategies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a better strategy layer with market snapshots, structured decision reasons, selectable strategies, a BTC 5-minute late-window strategy, and a conservative longer-window trend strategy.

**Architecture:** Keep the bot runner as the orchestration point, but move strategy inputs into a serializable `MarketSnapshot`. Strategies are loaded through a registry with metadata and compatibility checks. Decisions remain the storage/execution contract, extended with reason codes and edge fields for dashboard visibility.

**Tech Stack:** Python 3.14, dataclasses, Pydantic config models, FastAPI dashboard, SQLite state store, pytest, Ruff.

---

## File Structure

- Modify `src/polybot/models.py`: add `MarketProfile`, `MarketSnapshot`, and extra `Decision` fields.
- Modify `src/polybot/strategies/base.py`: add registry metadata, snapshot builder, compatibility helpers, and keep `load_strategy()` as the public loader.
- Modify `src/polybot/strategies/baseline_momentum.py`: make baseline consume `MarketSnapshot` through `StrategyContext`.
- Create `src/polybot/strategies/late_window_5m.py`: new specialized BTC 5-minute strategy.
- Modify `src/polybot/strategies/late_window.py`: keep compatibility alias around `LateWindow5mStrategy`.
- Create `src/polybot/strategies/trend_following.py`: conservative longer-window strategy skeleton with explicit incompatibility for BTC 5-minute markets.
- Modify `src/polybot/bot.py`: build the snapshot before strategy decision.
- Modify `src/polybot/config.py`: allow `late_window_5m` and `trend_following`.
- Modify `src/polybot/state_store.py`: dashboard snapshots already store full decision payloads, but defaults/tests should cover new fields.
- Modify `src/polybot/dashboard/static/index.html`: add compact strategy metrics placeholders.
- Modify `src/polybot/dashboard/static/app.js`: render reason code, edge, market probability, estimated probability, and confidence.
- Modify `src/polybot/dashboard/static/styles.css`: style compact metrics without changing the dashboard layout.
- Modify tests under `tests/`: add targeted unit coverage for each task.

---

### Task 1: Add Market Snapshot Model

**Files:**
- Modify: `src/polybot/models.py`
- Modify: `src/polybot/strategies/base.py`
- Test: `tests/test_strategies.py`

- [ ] **Step 1: Write failing snapshot test**

Add this test to `tests/test_strategies.py`:

```python
def test_strategy_context_builds_market_snapshot():
    now = datetime(2026, 5, 12, 21, 4, 20, tzinfo=UTC)
    market = _market(end_offset=timedelta(minutes=5))
    context = _context(
        price=100.25,
        reference=100.0,
        market=market,
        now=now,
        up_ask=0.84,
        down_ask=0.18,
    )

    snapshot = context.snapshot

    assert snapshot.market_profile == "btc_5m"
    assert snapshot.seconds_remaining == 40.0
    assert snapshot.window_seconds == 300.0
    assert snapshot.target_price == 100.0
    assert snapshot.btc_price == 100.25
    assert snapshot.delta == 0.25
    assert snapshot.delta_pct == 0.25
    assert snapshot.up_ask == 0.84
    assert snapshot.down_ask == 0.18
    assert snapshot.max_spread == 0.02
    assert snapshot.feed_fresh is True
    assert snapshot.source_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_strategies.py::test_strategy_context_builds_market_snapshot -v
```

Expected: FAIL with an attribute error because `StrategyContext.snapshot` does not exist.

- [ ] **Step 3: Add snapshot dataclass**

In `src/polybot/models.py`, add this near `Market`:

```python
@dataclass(frozen=True)
class MarketSnapshot:
    market_id: str
    slug: str
    question: str
    market_profile: str
    start_time: datetime | None
    end_time: datetime
    accepting_orders: bool
    seconds_elapsed: float | None
    seconds_remaining: float
    window_seconds: float | None
    target_price: float
    btc_price: float
    delta: float
    delta_pct: float
    up_token_id: str
    down_token_id: str
    up_bid: float
    up_ask: float
    down_bid: float
    down_ask: float
    up_spread: float
    down_spread: float
    max_spread: float
    up_bid_size: float
    up_ask_size: float
    down_bid_size: float
    down_ask_size: float
    feed_fresh: bool
    feed_max_deviation_bps: float
    source_count: int
```

- [ ] **Step 4: Build snapshot in StrategyContext**

In `src/polybot/strategies/base.py`, import `field` and `MarketSnapshot`, then update `StrategyContext`:

```python
@dataclass(frozen=True)
class StrategyContext:
    market: Market
    reference_start_price: float
    feed: FeedAggregate
    up_book: OrderbookSnapshot
    down_book: OrderbookSnapshot
    now: datetime
    snapshot: MarketSnapshot = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot", build_market_snapshot(self))
```

Also add these helpers in `src/polybot/strategies/base.py`:

```python
def classify_market_profile(market: Market) -> str:
    duration = (market.end_time - market.start_time).total_seconds() if market.start_time else None
    if market.slug.startswith("btc-updown-5m-") or duration == 300:
        return "btc_5m"
    if "bitcoin" in market.question.lower() or "btc" in market.slug.lower():
        return "longer_crypto"
    return "all_crypto"


def build_market_snapshot(context: StrategyContext) -> MarketSnapshot:
    market = context.market
    seconds_remaining = (market.end_time - context.now).total_seconds()
    seconds_elapsed = None
    window_seconds = None
    if market.start_time is not None:
        seconds_elapsed = (context.now - market.start_time).total_seconds()
        window_seconds = (market.end_time - market.start_time).total_seconds()

    delta = round(context.feed.reference_price - context.reference_start_price, 6)
    delta_pct = round((delta / context.reference_start_price) * 100, 6)

    return MarketSnapshot(
        market_id=market.market_id,
        slug=market.slug,
        question=market.question,
        market_profile=classify_market_profile(market),
        start_time=market.start_time,
        end_time=market.end_time,
        accepting_orders=market.accepting_orders,
        seconds_elapsed=seconds_elapsed,
        seconds_remaining=seconds_remaining,
        window_seconds=window_seconds,
        target_price=context.reference_start_price,
        btc_price=context.feed.reference_price,
        delta=delta,
        delta_pct=delta_pct,
        up_token_id=market.up_token_id,
        down_token_id=market.down_token_id,
        up_bid=context.up_book.best_bid,
        up_ask=context.up_book.best_ask,
        down_bid=context.down_book.best_bid,
        down_ask=context.down_book.best_ask,
        up_spread=context.up_book.spread,
        down_spread=context.down_book.spread,
        max_spread=max(context.up_book.spread, context.down_book.spread),
        up_bid_size=context.up_book.bid_size,
        up_ask_size=context.up_book.ask_size,
        down_bid_size=context.down_book.bid_size,
        down_ask_size=context.down_book.ask_size,
        feed_fresh=context.feed.fresh,
        feed_max_deviation_bps=context.feed.max_deviation_bps,
        source_count=len(context.feed.prices),
    )
```

- [ ] **Step 5: Run snapshot test**

Run:

```bash
uv run pytest tests/test_strategies.py::test_strategy_context_builds_market_snapshot -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/polybot/models.py src/polybot/strategies/base.py tests/test_strategies.py
git commit -m "feat: add strategy market snapshot"
```

---

### Task 2: Add Structured Decision Fields

**Files:**
- Modify: `src/polybot/models.py`
- Modify: `src/polybot/strategies/baseline_momentum.py`
- Modify: `src/polybot/strategies/late_window.py`
- Test: `tests/test_strategies.py`
- Test: `tests/test_state_store.py`

- [ ] **Step 1: Write failing decision metadata test**

Add this test to `tests/test_strategies.py`:

```python
def test_strategy_decision_includes_reason_code_and_edge_fields():
    decision = load_strategy("baseline_momentum").decide(_context())

    assert decision.reason_code == "momentum_up"
    assert decision.market_probability == 0.62
    assert decision.edge == pytest.approx(decision.estimated_probability - 0.62)
    assert decision.to_dict()["reason_code"] == "momentum_up"
    assert "edge" in decision.to_dict()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_strategies.py::test_strategy_decision_includes_reason_code_and_edge_fields -v
```

Expected: FAIL because `Decision.reason_code`, `market_probability`, and `edge` do not exist.

- [ ] **Step 3: Extend Decision dataclass**

In `src/polybot/models.py`, add optional defaults at the end of `Decision`:

```python
    reason_code: str = ""
    market_probability: float | None = None
    edge: float | None = None
```

Keep these fields at the end so existing positional test construction remains valid.

- [ ] **Step 4: Update baseline decision helpers**

In `src/polybot/strategies/baseline_momentum.py`, update `_no_trade()` signature:

```python
def _no_trade(
    strategy: str,
    context: StrategyContext,
    *,
    reason: str,
    reason_code: str,
    estimated_probability: float = 0.5,
    expected_return: float = 0.0,
    market_probability: float | None = None,
    edge: float | None = None,
) -> Decision:
```

Inside the returned `Decision`, add:

```python
        reason_code=reason_code,
        market_probability=market_probability,
        edge=edge,
```

Update existing `_no_trade()` calls:

```python
reason_code="invalid_reference"
reason_code="delta_too_small"
```

In the buy path, compute market probability and edge:

```python
market_probability = book.best_ask
edge = estimated_probability - market_probability
```

Add these fields to the buy `Decision`:

```python
            reason_code="momentum_up" if action == DecisionAction.BUY_UP else "momentum_down",
            market_probability=market_probability,
            edge=edge,
```

- [ ] **Step 5: Update late_window no-trade calls**

In `src/polybot/strategies/late_window.py`, add reason codes to existing `_no_trade()` calls:

```python
reason_code="too_early"
reason_code="invalid_reference"
reason_code="edge_too_low"
reason_code="return_out_of_range"
```

For return-band no-trade, also pass:

```python
market_probability=book.best_ask,
edge=estimated_probability - book.best_ask,
```

In the accepted decision, add:

```python
            reason_code="late_window_high_confidence",
            market_probability=book.best_ask,
            edge=estimated_probability - book.best_ask,
```

- [ ] **Step 6: Run strategy tests and adjust expected reason strings only where needed**

Run:

```bash
uv run pytest tests/test_strategies.py -q
```

Expected: PASS. Existing tests can keep human-readable `reason` assertions unchanged.

- [ ] **Step 7: Run state store tests**

Run:

```bash
uv run pytest tests/test_state_store.py -q
```

Expected: PASS because `Decision.to_dict()` serializes the new fields automatically.

- [ ] **Step 8: Commit**

```bash
git add src/polybot/models.py src/polybot/strategies/baseline_momentum.py src/polybot/strategies/late_window.py tests/test_strategies.py
git commit -m "feat: add structured decision metadata"
```

---

### Task 3: Add Strategy Registry Metadata And Config Choices

**Files:**
- Modify: `src/polybot/config.py`
- Modify: `src/polybot/strategies/base.py`
- Test: `tests/test_config.py`
- Test: `tests/test_strategies.py`

- [ ] **Step 1: Write failing registry tests**

Add to `tests/test_strategies.py`:

```python
def test_strategy_registry_lists_available_strategies():
    from polybot.strategies.base import list_strategy_metadata

    metadata = {item.name: item for item in list_strategy_metadata()}

    assert metadata["baseline_momentum"].label == "Baseline Momentum"
    assert metadata["late_window_5m"].market_profiles == ("btc_5m",)
    assert metadata["trend_following"].market_profiles == ("longer_crypto",)


def test_late_window_alias_loads_late_window_5m_strategy():
    strategy = load_strategy("late_window")

    assert strategy.name == "late_window_5m"
```

Add to `tests/test_config.py`:

```python
def test_strategy_config_accepts_new_strategy_names():
    base = _valid_config_data()

    for name in ["baseline_momentum", "late_window", "late_window_5m", "trend_following"]:
        data = base | {"strategy": {"name": name}}
        assert BotConfig.model_validate(data).strategy.name == name
```

If `_valid_config_data()` does not exist, create it in `tests/test_config.py` by copying the existing valid config payload used by current config tests.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_strategies.py::test_strategy_registry_lists_available_strategies tests/test_strategies.py::test_late_window_alias_loads_late_window_5m_strategy tests/test_config.py::test_strategy_config_accepts_new_strategy_names -v
```

Expected: FAIL because registry metadata and config choices do not exist.

- [ ] **Step 3: Add strategy metadata**

In `src/polybot/strategies/base.py`, add:

```python
@dataclass(frozen=True)
class StrategyMetadata:
    name: str
    label: str
    market_profiles: tuple[str, ...]
    description: str


STRATEGY_METADATA = {
    "baseline_momentum": StrategyMetadata(
        name="baseline_momentum",
        label="Baseline Momentum",
        market_profiles=("btc_5m", "longer_crypto", "all_crypto"),
        description="Momentum strategy using current BTC delta against target.",
    ),
    "late_window_5m": StrategyMetadata(
        name="late_window_5m",
        label="Late Window 5m",
        market_profiles=("btc_5m",),
        description="Trades BTC 5-minute windows late when confidence and return align.",
    ),
    "trend_following": StrategyMetadata(
        name="trend_following",
        label="Trend Following",
        market_profiles=("longer_crypto",),
        description="Conservative trend strategy for longer crypto windows.",
    ),
}


STRATEGY_ALIASES = {"late_window": "late_window_5m"}


def normalize_strategy_name(name: str) -> str:
    return STRATEGY_ALIASES.get(name, name)


def list_strategy_metadata() -> tuple[StrategyMetadata, ...]:
    return tuple(STRATEGY_METADATA.values())


def strategy_supports_market(name: str, market_profile: str) -> bool:
    metadata = STRATEGY_METADATA[normalize_strategy_name(name)]
    return market_profile in metadata.market_profiles
```

- [ ] **Step 4: Update load_strategy**

Replace `load_strategy()` in `src/polybot/strategies/base.py` with:

```python
def load_strategy(name: str) -> Strategy:
    normalized = normalize_strategy_name(name)
    if normalized == "baseline_momentum":
        from polybot.strategies.baseline_momentum import BaselineMomentumStrategy

        return BaselineMomentumStrategy()
    if normalized == "late_window_5m":
        from polybot.strategies.late_window_5m import LateWindow5mStrategy

        return LateWindow5mStrategy()
    if normalized == "trend_following":
        from polybot.strategies.trend_following import TrendFollowingStrategy

        return TrendFollowingStrategy()
    raise ValueError(f"Unknown strategy: {name}")
```

- [ ] **Step 5: Expand config Literal**

In `src/polybot/config.py`, update `StrategySection`:

```python
class StrategySection(BaseModel):
    name: Literal[
        "baseline_momentum",
        "late_window",
        "late_window_5m",
        "trend_following",
    ] = "baseline_momentum"
```

- [ ] **Step 6: Add temporary strategy modules for import**

Create `src/polybot/strategies/late_window_5m.py`:

```python
from polybot.strategies.late_window import LateWindowStrategy


class LateWindow5mStrategy(LateWindowStrategy):
    name = "late_window_5m"
```

Create `src/polybot/strategies/trend_following.py`:

```python
from polybot.models import DecisionAction
from polybot.strategies.baseline_momentum import _no_trade
from polybot.strategies.base import StrategyContext


class TrendFollowingStrategy:
    name = "trend_following"

    def decide(self, context: StrategyContext):
        return _no_trade(
            self.name,
            context,
            reason="trend following requires a longer crypto market",
            reason_code="trend_not_supported_for_market",
            estimated_probability=0.5,
            expected_return=0.0,
        )
```

Remove the unused `DecisionAction` import if Ruff flags it.

- [ ] **Step 7: Run registry and config tests**

Run:

```bash
uv run pytest tests/test_strategies.py::test_strategy_registry_lists_available_strategies tests/test_strategies.py::test_late_window_alias_loads_late_window_5m_strategy tests/test_config.py::test_strategy_config_accepts_new_strategy_names -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/polybot/config.py src/polybot/strategies/base.py src/polybot/strategies/late_window_5m.py src/polybot/strategies/trend_following.py tests/test_config.py tests/test_strategies.py
git commit -m "feat: add strategy registry metadata"
```

---

### Task 4: Implement Late Window 5m Strategy With Snapshot

**Files:**
- Modify: `src/polybot/strategies/late_window_5m.py`
- Modify: `src/polybot/strategies/late_window.py`
- Test: `tests/test_strategies.py`

- [ ] **Step 1: Add failing late-window reason tests**

Add these tests to `tests/test_strategies.py`:

```python
def test_late_window_5m_rejects_missing_target_price():
    context = _context(reference=0.0, now=datetime(2026, 5, 12, 21, 4, 20, tzinfo=UTC))

    decision = load_strategy("late_window_5m").decide(context)

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason_code == "target_missing"


def test_late_window_5m_rejects_non_btc_5m_market():
    now = datetime(2026, 5, 12, 21, 0, tzinfo=UTC)
    market = Market(
        "m",
        "Bitcoin Up or Down - 1h",
        "btc-updown-1h",
        "up",
        "down",
        now,
        now + timedelta(hours=1),
        0.01,
        5.0,
        True,
    )

    decision = load_strategy("late_window_5m").decide(
        _context(market=market, now=now + timedelta(minutes=55))
    )

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason_code == "strategy_not_supported"


def test_late_window_5m_buys_up_with_reason_code_and_edge():
    decision = load_strategy("late_window_5m").decide(
        _context(
            reference=100.0,
            price=100.2,
            now=datetime(2026, 5, 12, 21, 4, 20, tzinfo=UTC),
            up_ask=0.84,
        )
    )

    assert decision.action == DecisionAction.BUY_UP
    assert decision.reason_code == "late_window_high_confidence"
    assert decision.market_probability == 0.84
    assert decision.edge == pytest.approx(decision.estimated_probability - 0.84)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_strategies.py::test_late_window_5m_rejects_missing_target_price tests/test_strategies.py::test_late_window_5m_rejects_non_btc_5m_market tests/test_strategies.py::test_late_window_5m_buys_up_with_reason_code_and_edge -v
```

Expected: at least one FAIL because `late_window_5m` is still a thin alias.

- [ ] **Step 3: Implement snapshot-based late strategy**

Replace `src/polybot/strategies/late_window_5m.py` with:

```python
from polybot.models import Decision, DecisionAction
from polybot.strategies.baseline_momentum import _expected_return, _no_trade
from polybot.strategies.base import StrategyContext


class LateWindow5mStrategy:
    name = "late_window_5m"
    min_seconds_remaining = 20
    max_seconds_remaining = 60
    min_delta_pct = 0.10
    min_expected_return = 0.01
    max_expected_return = 0.10

    def decide(self, context: StrategyContext) -> Decision:
        snapshot = context.snapshot
        if snapshot.market_profile != "btc_5m":
            return _no_trade(
                self.name,
                context,
                reason="late-window 5m strategy only supports BTC 5-minute markets",
                reason_code="strategy_not_supported",
            )
        if snapshot.target_price <= 0:
            return _no_trade(
                self.name,
                context,
                reason="target price missing",
                reason_code="target_missing",
            )
        if snapshot.seconds_remaining < self.min_seconds_remaining:
            return _no_trade(
                self.name,
                context,
                reason="too close to resolution",
                reason_code="too_late",
            )
        if snapshot.seconds_remaining > self.max_seconds_remaining:
            return _no_trade(
                self.name,
                context,
                reason="outside late window",
                reason_code="too_early",
            )
        if abs(snapshot.delta_pct) < self.min_delta_pct:
            return _no_trade(
                self.name,
                context,
                reason="late window edge too small",
                reason_code="edge_too_low",
            )

        if snapshot.delta > 0:
            book = context.up_book
            action = DecisionAction.BUY_UP
        else:
            book = context.down_book
            action = DecisionAction.BUY_DOWN

        estimated_probability = min(0.98, 0.80 + abs(snapshot.delta_pct / 100) * 30)
        market_probability = book.best_ask
        expected_return = _expected_return(estimated_probability, book)
        edge = estimated_probability - market_probability
        if expected_return < self.min_expected_return or expected_return > self.max_expected_return:
            return _no_trade(
                self.name,
                context,
                reason="expected return outside late-window band",
                reason_code="return_out_of_range",
                estimated_probability=estimated_probability,
                expected_return=expected_return,
                market_probability=market_probability,
                edge=edge,
            )

        return Decision(
            strategy=self.name,
            action=action,
            market_id=context.market.market_id,
            token_id=book.token_id,
            target_price=book.best_ask,
            estimated_probability=estimated_probability,
            confidence=estimated_probability,
            expected_return=expected_return,
            max_slippage=0.005,
            reason="late-window probability and return accepted",
            created_at=context.now,
            reason_code="late_window_high_confidence",
            market_probability=market_probability,
            edge=edge,
        )
```

- [ ] **Step 4: Keep compatibility alias**

Replace `src/polybot/strategies/late_window.py` with:

```python
from polybot.strategies.late_window_5m import LateWindow5mStrategy


class LateWindowStrategy(LateWindow5mStrategy):
    name = "late_window_5m"
```

- [ ] **Step 5: Run late-window tests**

Run:

```bash
uv run pytest tests/test_strategies.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/polybot/strategies/late_window_5m.py src/polybot/strategies/late_window.py tests/test_strategies.py
git commit -m "feat: refine btc late-window strategy"
```

---

### Task 5: Implement Conservative Trend Following Strategy

**Files:**
- Modify: `src/polybot/strategies/trend_following.py`
- Test: `tests/test_strategies.py`

- [ ] **Step 1: Add failing trend tests**

Add to `tests/test_strategies.py`:

```python
def test_trend_following_rejects_btc_5m_market():
    decision = load_strategy("trend_following").decide(_context())

    assert decision.action == DecisionAction.NO_TRADE
    assert decision.reason_code == "trend_not_supported_for_market"


def test_trend_following_buys_up_on_longer_market_momentum():
    now = datetime(2026, 5, 12, 21, 0, tzinfo=UTC)
    market = Market(
        "m",
        "Bitcoin Up or Down - 1h",
        "btc-updown-1h",
        "up",
        "down",
        now,
        now + timedelta(hours=1),
        0.01,
        5.0,
        True,
    )

    decision = load_strategy("trend_following").decide(
        _context(
            market=market,
            reference=100.0,
            price=101.5,
            now=now + timedelta(minutes=10),
            up_ask=0.58,
        )
    )

    assert decision.action == DecisionAction.BUY_UP
    assert decision.reason_code == "trend_confirmed"
    assert decision.edge is not None
    assert decision.edge > 0
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_strategies.py::test_trend_following_rejects_btc_5m_market tests/test_strategies.py::test_trend_following_buys_up_on_longer_market_momentum -v
```

Expected: second test FAILS because trend strategy always returns no trade.

- [ ] **Step 3: Implement conservative trend strategy**

Replace `src/polybot/strategies/trend_following.py` with:

```python
from polybot.models import Decision, DecisionAction
from polybot.strategies.baseline_momentum import _expected_return, _no_trade
from polybot.strategies.base import StrategyContext


class TrendFollowingStrategy:
    name = "trend_following"
    min_delta_pct = 1.0
    min_seconds_elapsed = 300
    min_edge = 0.03

    def decide(self, context: StrategyContext) -> Decision:
        snapshot = context.snapshot
        if snapshot.market_profile == "btc_5m":
            return _no_trade(
                self.name,
                context,
                reason="trend following requires a longer crypto market",
                reason_code="trend_not_supported_for_market",
            )
        if snapshot.target_price <= 0:
            return _no_trade(
                self.name,
                context,
                reason="target price missing",
                reason_code="target_missing",
            )
        if snapshot.seconds_elapsed is not None and snapshot.seconds_elapsed < self.min_seconds_elapsed:
            return _no_trade(
                self.name,
                context,
                reason="not enough trend history in current window",
                reason_code="trend_history_too_short",
            )
        if abs(snapshot.delta_pct) < self.min_delta_pct:
            return _no_trade(
                self.name,
                context,
                reason="trend delta too small",
                reason_code="trend_delta_too_small",
            )

        if snapshot.delta > 0:
            book = context.up_book
            action = DecisionAction.BUY_UP
        else:
            book = context.down_book
            action = DecisionAction.BUY_DOWN

        estimated_probability = min(0.90, 0.55 + abs(snapshot.delta_pct) / 20)
        market_probability = book.best_ask
        edge = estimated_probability - market_probability
        expected_return = _expected_return(estimated_probability, book)
        if edge < self.min_edge:
            return _no_trade(
                self.name,
                context,
                reason="trend edge too low",
                reason_code="edge_too_low",
                estimated_probability=estimated_probability,
                expected_return=expected_return,
                market_probability=market_probability,
                edge=edge,
            )

        return Decision(
            strategy=self.name,
            action=action,
            market_id=context.market.market_id,
            token_id=book.token_id,
            target_price=book.best_ask,
            estimated_probability=estimated_probability,
            confidence=min(0.90, estimated_probability),
            expected_return=expected_return,
            max_slippage=0.01,
            reason="trend confirmed with positive edge",
            created_at=context.now,
            reason_code="trend_confirmed",
            market_probability=market_probability,
            edge=edge,
        )
```

- [ ] **Step 4: Run trend tests**

Run:

```bash
uv run pytest tests/test_strategies.py::test_trend_following_rejects_btc_5m_market tests/test_strategies.py::test_trend_following_buys_up_on_longer_market_momentum -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/polybot/strategies/trend_following.py tests/test_strategies.py
git commit -m "feat: add conservative trend strategy"
```

---

### Task 6: Wire Dashboard Strategy Metadata And Decision Metrics

**Files:**
- Modify: `src/polybot/dashboard/app.py`
- Modify: `src/polybot/dashboard/static/index.html`
- Modify: `src/polybot/dashboard/static/app.js`
- Modify: `src/polybot/dashboard/static/styles.css`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Add failing dashboard API test**

Add to `tests/test_dashboard.py`:

```python
def test_dashboard_snapshot_includes_strategy_metadata(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    app = create_dashboard_app(store, dashboard_config_for_test(), control_service=None)
    client = TestClient(app)

    response = client.get("/api/snapshot")

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["strategy_metadata"]]
    assert names == ["baseline_momentum", "late_window_5m", "trend_following"]
```

- [ ] **Step 2: Add failing dashboard HTML test assertions**

In `test_dashboard_root_contains_tabs_controls_and_settings`, add:

```python
    assert 'id="strategy-reason-code"' in html
    assert 'id="strategy-edge"' in html
    assert 'id="strategy-confidence"' in html
```

- [ ] **Step 3: Run dashboard tests to verify failure**

Run:

```bash
uv run pytest tests/test_dashboard.py::test_dashboard_snapshot_includes_strategy_metadata tests/test_dashboard.py::test_dashboard_root_contains_tabs_controls_and_settings -v
```

Expected: FAIL because API/HTML do not expose these fields yet.

- [ ] **Step 4: Add metadata to dashboard snapshot**

In `src/polybot/dashboard/app.py`, import `list_strategy_metadata`:

```python
from polybot.strategies.base import list_strategy_metadata
```

Where `/api/snapshot` response is assembled, add:

```python
        snapshot["strategy_metadata"] = [
            {
                "name": item.name,
                "label": item.label,
                "market_profiles": list(item.market_profiles),
                "description": item.description,
            }
            for item in list_strategy_metadata()
        ]
```

- [ ] **Step 5: Add dashboard placeholders**

In `src/polybot/dashboard/static/index.html`, add these fields to the monitor metrics area near the existing BTC/target/market cards:

```html
<div class="metric">
  <span>Reason</span>
  <strong id="strategy-reason-code">-</strong>
</div>
<div class="metric">
  <span>Edge</span>
  <strong id="strategy-edge">-</strong>
</div>
<div class="metric">
  <span>Confidence</span>
  <strong id="strategy-confidence">-</strong>
</div>
```

- [ ] **Step 6: Render latest decision metrics**

In `src/polybot/dashboard/static/app.js`, update the snapshot render function to compute:

```javascript
const latestDecision = (snapshot.recent_decisions || [])[0] || {};
setText("strategy-reason-code", latestDecision.reason_code || "-");
setText(
  "strategy-edge",
  latestDecision.edge === null || latestDecision.edge === undefined
    ? "-"
    : latestDecision.edge.toFixed(4)
);
setText(
  "strategy-confidence",
  latestDecision.confidence === null || latestDecision.confidence === undefined
    ? "-"
    : `${(latestDecision.confidence * 100).toFixed(1)}%`
);
```

Use the existing local helper for setting text if it already exists; otherwise add:

```javascript
function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}
```

- [ ] **Step 7: Style compact metrics**

In `src/polybot/dashboard/static/styles.css`, add only if no equivalent `.metric` style exists:

```css
.metric span {
  display: block;
  color: #667085;
  font-size: 0.875rem;
  font-weight: 700;
}

.metric strong {
  display: block;
  color: #14213d;
  font-size: 1.25rem;
  line-height: 1.4;
  margin-top: 0.25rem;
}
```

- [ ] **Step 8: Run dashboard tests and JS syntax check**

Run:

```bash
uv run pytest tests/test_dashboard.py -q
node --check src/polybot/dashboard/static/app.js
```

Expected: PASS and `node --check` exits 0.

- [ ] **Step 9: Commit**

```bash
git add src/polybot/dashboard/app.py src/polybot/dashboard/static/index.html src/polybot/dashboard/static/app.js src/polybot/dashboard/static/styles.css tests/test_dashboard.py
git commit -m "feat: show strategy decision metrics"
```

---

### Task 7: Full Verification

**Files:**
- Verify all modified files.

- [ ] **Step 1: Run complete test suite**

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

- [ ] **Step 3: Run dashboard JS syntax check**

Run:

```bash
node --check src/polybot/dashboard/static/app.js
```

Expected: no output and exit code 0.

- [ ] **Step 4: Run one bot cycle in paper config**

Run:

```bash
uv run polybot run --config configs/bot.local.toml
```

Expected: command exits 0 or records a clear market/feed/risk no-trade event without Python traceback.

- [ ] **Step 5: Commit final fixes if verification required changes**

If any verification command required a small fix:

```bash
git add src/polybot tests configs docs
git commit -m "fix: complete strategy quality verification"
```

If no files changed, do not create an empty commit.

---

## Self-Review Notes

- Spec coverage: snapshot, registry, late-window strategy, trend strategy, reason codes, dashboard visibility, and tests are covered.
- Scope kept to trading quality. Data API wallet reconciliation and setup simplification remain out of this plan.
- Type consistency: `MarketSnapshot`, `StrategyMetadata`, `reason_code`, `market_probability`, and `edge` are introduced before later tasks depend on them.
- Compatibility: `late_window` remains accepted as an alias while `late_window_5m` becomes the canonical strategy name.
