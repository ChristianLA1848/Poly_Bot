# Dashboard Control UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tabbed dashboard that shows BTC price and event target value, edits bot settings, and starts/stops a continuous paper or live bot loop.

**Architecture:** Add small dashboard services around the existing `BotRunner`: persistent runtime/feed state in `StateStore`, persisted editable settings validated through `BotConfig`, and one in-process async controller for start/stop. The FastAPI app injects these services and exposes JSON endpoints used by a vanilla JS tabbed UI.

**Tech Stack:** Python 3.14, FastAPI, Pydantic, SQLite, Typer, vanilla HTML/CSS/JS, pytest, Ruff.

---

## File Structure

- Modify `src/polybot/state_store.py`: persist runtime status, feed status, target price, and settings JSON.
- Modify `src/polybot/bot.py`: record BTC feed and event target after market/feed are known.
- Create `src/polybot/dashboard/control.py`: dashboard-owned `BotControlService` with start/stop loop and runtime state.
- Modify `src/polybot/dashboard/app.py`: inject config/settings/control service and expose start/stop/settings endpoints.
- Modify `src/polybot/cli.py`: pass loaded config and runtime paths into dashboard app.
- Modify `src/polybot/dashboard/static/index.html`: add Monitor, Settings, and Logs tabs.
- Modify `src/polybot/dashboard/static/app.js`: render tabs, settings form, BTC/target fields, and start/stop actions.
- Modify `src/polybot/dashboard/static/styles.css`: responsive tab, form, and control styling.
- Add/modify tests in `tests/test_state_store.py`, `tests/test_bot_loop.py`, `tests/test_dashboard_control.py`, and `tests/test_dashboard.py`.

---

### Task 1: Persist Runtime, Feed, and Target State

**Files:**
- Modify: `src/polybot/state_store.py`
- Test: `tests/test_state_store.py`

- [ ] **Step 1: Write failing runtime state tests**

Add to `tests/test_state_store.py`:

```python
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
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_state_store.py::test_state_store_empty_snapshot_includes_runtime_and_feed_defaults tests/test_state_store.py::test_state_store_records_runtime_status tests/test_state_store.py::test_state_store_records_feed_status_with_target_delta -v
```

Expected: fail because `runtime_status`, `feed_status`, and the record methods do not exist.

- [ ] **Step 3: Implement minimal persistence**

In `src/polybot/state_store.py`, add `DEFAULT_RUNTIME_STATUS`, `DEFAULT_FEED_STATUS`, tables `runtime_status` and `feed_status`, plus:

```python
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
    delta = feed.reference_price - target_price if target_price is not None else None
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
```

Use the same singleton table pattern as `market_status`. Update `dashboard_snapshot()` to include both payloads.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/test_state_store.py -v
```

Expected: all `test_state_store.py` tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/polybot/state_store.py tests/test_state_store.py
git commit -m "feat: persist dashboard runtime feed state"
```

---

### Task 2: Record BTC Price and Event Target from Bot Cycles

**Files:**
- Modify: `src/polybot/bot.py`
- Test: `tests/test_bot_loop.py`

- [ ] **Step 1: Write failing bot-loop test**

Add to `tests/test_bot_loop.py`:

```python
@pytest.mark.asyncio
async def test_bot_runner_records_feed_and_target_status(tmp_path):
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FakeOrderbookClient(),
        execution=FakeExecution(),
        store_path=tmp_path / "bot.sqlite3",
        reference_start_price=100.0,
        latest_feed=_feed(),
    )

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    assert runner.store.dashboard_snapshot()["feed_status"] == {
        "btc_price": 101.0,
        "fresh": True,
        "max_deviation_bps": 0,
        "created_at": "2026-05-12T21:03:00+00:00",
        "target_price": 100.0,
        "delta": 1.0,
        "delta_pct": 1.0,
    }
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_bot_loop.py::test_bot_runner_records_feed_and_target_status -v
```

Expected: fail because `BotRunner` does not write feed status.

- [ ] **Step 3: Implement minimal recording**

In `BotRunner.run_once()`, after `reference_start_price` is set and before orderbook fetches, add:

```python
if self.reference_start_price is None:
    self.reference_start_price = self.latest_feed.reference_price
self.store.record_feed_status(self.latest_feed, self.reference_start_price)
```

Keep existing behavior for missing feed and market-not-found paths.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/test_bot_loop.py::test_bot_runner_records_feed_and_target_status tests/test_bot_loop.py -v
```

Expected: selected test and all bot-loop tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/polybot/bot.py tests/test_bot_loop.py
git commit -m "feat: record btc target status"
```

---

### Task 3: Persist Editable Dashboard Settings

**Files:**
- Modify: `src/polybot/state_store.py`
- Test: `tests/test_state_store.py`

- [ ] **Step 1: Write failing settings tests**

Add to `tests/test_state_store.py`:

```python
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
```

Add a helper in the same test file:

```python
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
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_state_store.py::test_state_store_returns_default_settings_when_unset tests/test_state_store.py::test_state_store_records_settings_payload -v
```

Expected: fail because settings persistence methods do not exist.

- [ ] **Step 3: Implement settings storage**

Add a singleton `settings` table and methods:

```python
def get_settings(self, default_config: BotConfig) -> dict[str, Any]:
    with self.connect() as conn:
        row = conn.execute("SELECT payload FROM settings WHERE id = 1").fetchone()
    if row is None:
        return default_config.model_dump(mode="json")
    return json.loads(row["payload"])


def record_settings(self, config: BotConfig) -> None:
    self._upsert_singleton_payload("settings", config.model_dump(mode="json"))
```

Import `BotConfig` in `state_store.py`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/test_state_store.py -v
```

Expected: all state store tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/polybot/state_store.py tests/test_state_store.py
git commit -m "feat: persist dashboard settings"
```

---

### Task 4: Add Dashboard Bot Control Service

**Files:**
- Create: `src/polybot/dashboard/control.py`
- Test: `tests/test_dashboard_control.py`

- [ ] **Step 1: Write failing control service tests**

Create `tests/test_dashboard_control.py`:

```python
from datetime import UTC, datetime

import pytest

from polybot.config import BotConfig, BotSection, ExitSection, LateWindowSection, RiskSection, StakingSection, StrategySection
from polybot.dashboard.control import BotControlService
from polybot.models import FeedAggregate, FeedPrice
from polybot.state_store import StateStore


def config_for_control(cycle_seconds: float = 0.01) -> BotConfig:
    return BotConfig(
        bot=BotSection(mode="paper", cycle_seconds=cycle_seconds),
        risk=RiskSection(max_stake=10, max_daily_loss=25, max_spread=0.04, min_liquidity=100, min_edge=0.03, max_feed_age_ms=2500, max_feed_deviation_bps=20),
        strategy=StrategySection(name="baseline_momentum"),
        staking=StakingSection(mode="fixed", fixed_stake=5),
        exit=ExitSection(mode="hold_to_resolution"),
        late_window=LateWindowSection(),
    )


@pytest.mark.asyncio
async def test_control_service_start_and_stop_records_runtime_status(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    cycles = {"count": 0}

    async def fake_run_once(cfg, store_path, audit_log_path):
        cycles["count"] += 1
        store.record_feed_status(
            FeedAggregate(101.0, [FeedPrice("test", "BTC-USD", 101.0, 1)], 0, True, datetime(2026, 5, 13, tzinfo=UTC)),
            target_price=100.0,
        )

    service = BotControlService(
        store=store,
        default_config=config_for_control(),
        store_path=tmp_path / "bot.sqlite3",
        audit_log_path=tmp_path / "audit.jsonl",
        run_once=fake_run_once,
    )

    start_status = await service.start()
    await service.stop()

    assert start_status["state"] in {"starting", "running"}
    assert cycles["count"] >= 1
    assert store.dashboard_snapshot()["runtime_status"]["state"] == "stopped"


@pytest.mark.asyncio
async def test_control_service_start_is_idempotent(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()

    async def fake_run_once(cfg, store_path, audit_log_path):
        return None

    service = BotControlService(store, config_for_control(), tmp_path / "bot.sqlite3", tmp_path / "audit.jsonl", fake_run_once)

    first = await service.start()
    second = await service.start()
    await service.stop()

    assert first["state"] in {"starting", "running"}
    assert second["state"] in {"starting", "running"}
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_dashboard_control.py -v
```

Expected: fail because `polybot.dashboard.control` does not exist.

- [ ] **Step 3: Implement control service**

Create `src/polybot/dashboard/control.py` with:

```python
from collections.abc import Awaitable, Callable
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from polybot.config import BotConfig
from polybot.state_store import StateStore

RunOnce = Callable[[BotConfig, str | Path, str | Path | None], Awaitable[None]]


class BotControlService:
    def __init__(
        self,
        store: StateStore,
        default_config: BotConfig,
        store_path: str | Path,
        audit_log_path: str | Path | None,
        run_once: RunOnce,
    ) -> None:
        self.store = store
        self.default_config = default_config
        self.store_path = store_path
        self.audit_log_path = audit_log_path
        self.run_once = run_once
        self._task: asyncio.Task[None] | None = None
        self._stop_requested = asyncio.Event()

    def status(self) -> dict[str, Any]:
        return self.store.dashboard_snapshot()["runtime_status"]

    async def start(self) -> dict[str, Any]:
        if self._task is not None and not self._task.done():
            return self.status()
        self._stop_requested.clear()
        self.store.record_runtime_status("starting", "Bot loop starting.", datetime.now(tz=UTC))
        self._task = asyncio.create_task(self._run_loop())
        await asyncio.sleep(0)
        return self.status()

    async def stop(self) -> dict[str, Any]:
        if self._task is None or self._task.done():
            self.store.record_runtime_status("stopped", "Bot is stopped.", datetime.now(tz=UTC))
            return self.status()
        self.store.record_runtime_status("stopping", "Stopping after current cycle.", datetime.now(tz=UTC))
        self._stop_requested.set()
        await self._task
        return self.status()

    async def _run_loop(self) -> None:
        config = BotConfig.model_validate(self.store.get_settings(self.default_config))
        self.store.record_runtime_status("running", "Bot loop running.", datetime.now(tz=UTC))
        while not self._stop_requested.is_set():
            try:
                await self.run_once(config, self.store_path, self.audit_log_path)
            except Exception as exc:
                self.store.record_runtime_status("error", "Bot loop error.", datetime.now(tz=UTC), str(exc))
            await asyncio.sleep(config.bot.cycle_seconds)
        self.store.record_runtime_status("stopped", "Bot is stopped.", datetime.now(tz=UTC))
```

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/test_dashboard_control.py -v
```

Expected: control service tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/polybot/dashboard/control.py tests/test_dashboard_control.py
git commit -m "feat: add dashboard bot control service"
```

---

### Task 5: Expose Settings and Bot Control API

**Files:**
- Modify: `src/polybot/dashboard/app.py`
- Modify: `src/polybot/cli.py`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing API tests**

Add to `tests/test_dashboard.py`:

```python
def test_dashboard_settings_get_and_put(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    cfg = dashboard_config_for_test()
    app = create_dashboard_app(store, default_config=cfg, control_service=None)
    client = TestClient(app)

    settings = client.get("/api/settings").json()
    settings["bot"]["mode"] = "live"
    response = client.put("/api/settings", json=settings)

    assert response.status_code == 200
    assert response.json()["bot"]["mode"] == "live"


def test_dashboard_settings_reject_invalid_payload(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    cfg = dashboard_config_for_test()
    app = create_dashboard_app(store, default_config=cfg, control_service=None)
    client = TestClient(app)

    response = client.put("/api/settings", json={"bot": {"mode": "invalid"}})

    assert response.status_code == 422


def test_dashboard_start_stop_routes_call_control_service(tmp_path):
    class FakeControl:
        async def start(self):
            return {"state": "running", "message": "Bot loop running."}

        async def stop(self):
            return {"state": "stopped", "message": "Bot is stopped."}

    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    app = create_dashboard_app(store, dashboard_config_for_test(), FakeControl())
    client = TestClient(app)

    assert client.post("/api/bot/start").json()["state"] == "running"
    assert client.post("/api/bot/stop").json()["state"] == "stopped"
```

Add a local helper matching Task 3 config values.

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_dashboard.py::test_dashboard_settings_get_and_put tests/test_dashboard.py::test_dashboard_settings_reject_invalid_payload tests/test_dashboard.py::test_dashboard_start_stop_routes_call_control_service -v
```

Expected: fail because app signature/routes do not exist.

- [ ] **Step 3: Implement API**

Change `create_dashboard_app` signature to:

```python
def create_dashboard_app(
    store: StateStore,
    default_config: BotConfig | None = None,
    control_service: Any | None = None,
) -> FastAPI:
```

Add routes:

```python
@dashboard.get("/api/settings")
def get_settings() -> dict[str, Any]:
    if default_config is None:
        return {}
    return store.get_settings(default_config)


@dashboard.put("/api/settings")
def put_settings(payload: dict[str, Any]) -> dict[str, Any]:
    config = BotConfig.model_validate(payload)
    store.record_settings(config)
    return config.model_dump(mode="json")


@dashboard.post("/api/bot/start")
async def start_bot() -> dict[str, Any]:
    if control_service is None:
        raise HTTPException(status_code=503, detail="Bot control is unavailable.")
    return await control_service.start()


@dashboard.post("/api/bot/stop")
async def stop_bot() -> dict[str, Any]:
    if control_service is None:
        raise HTTPException(status_code=503, detail="Bot control is unavailable.")
    return await control_service.stop()
```

Update `snapshot()` to include `settings` when `default_config` is present.

In `src/polybot/cli.py`, instantiate `BotControlService(store, cfg, settings.db_path, settings.audit_log_path, _run_one_cycle)` and pass it to `create_dashboard_app`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/test_dashboard.py -v
```

Expected: dashboard tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/polybot/dashboard/app.py src/polybot/cli.py tests/test_dashboard.py
git commit -m "feat: expose dashboard control api"
```

---

### Task 6: Build Tabbed Dashboard UI

**Files:**
- Modify: `src/polybot/dashboard/static/index.html`
- Modify: `src/polybot/dashboard/static/app.js`
- Modify: `src/polybot/dashboard/static/styles.css`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing HTML test**

Add to `tests/test_dashboard.py`:

```python
def test_dashboard_root_contains_tabs_controls_and_settings(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    app = create_dashboard_app(store, dashboard_config_for_test(), control_service=None)
    client = TestClient(app)

    html = client.get("/").text

    assert 'data-tab-target="monitor"' in html
    assert 'data-tab-target="settings"' in html
    assert 'data-tab-target="logs"' in html
    assert 'id="start-bot"' in html
    assert 'id="stop-bot"' in html
    assert 'id="btc-price"' in html
    assert 'id="target-price"' in html
    assert 'name="bot.mode"' in html
    assert 'name="strategy.name"' in html
    assert 'name="staking.mode"' in html
```

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_dashboard.py::test_dashboard_root_contains_tabs_controls_and_settings -v
```

Expected: fail because the static HTML has no tabs/settings controls.

- [ ] **Step 3: Implement HTML/CSS/JS**

In `index.html`, add:

```html
<nav class="tabs" aria-label="Dashboard tabs">
  <button class="tab is-active" data-tab-target="monitor">Monitor</button>
  <button class="tab" data-tab-target="settings">Settings</button>
  <button class="tab" data-tab-target="logs">Logs</button>
</nav>
```

Create tab panels:

```html
<section class="tab-panel is-active" data-tab-panel="monitor">...</section>
<section class="tab-panel" data-tab-panel="settings">...</section>
<section class="tab-panel" data-tab-panel="logs">...</section>
```

Move the existing metrics, market panel, decisions, and events into Monitor/Logs. Add IDs `btc-price`, `target-price`, `target-delta`, `start-bot`, `stop-bot`, and a form `id="settings-form"` with names from the test.

In `app.js`, add tab switching:

```javascript
for (const tab of document.querySelectorAll("[data-tab-target]")) {
  tab.addEventListener("click", () => {
    const target = tab.dataset.tabTarget;
    document.querySelectorAll("[data-tab-target]").forEach((item) => item.classList.toggle("is-active", item === tab));
    document.querySelectorAll("[data-tab-panel]").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.tabPanel === target));
  });
}
```

Render feed status:

```javascript
function renderFeedStatus(feed) {
  btcPrice.textContent = formatCurrency(feed?.btc_price);
  targetPrice.textContent = feed?.target_price ? formatCurrency(feed.target_price) : "-";
  targetDelta.textContent = feed?.delta_pct ? `${feed.delta_pct.toFixed(3)}%` : "-";
}
```

Add start/stop fetch handlers:

```javascript
startBotButton.addEventListener("click", async () => {
  await fetch("/api/bot/start", { method: "POST" });
  await refreshSnapshot();
});
stopBotButton.addEventListener("click", async () => {
  await fetch("/api/bot/stop", { method: "POST" });
  await refreshSnapshot();
});
```

Add settings load/save using `GET /api/settings` and `PUT /api/settings`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/test_dashboard.py -v
```

Expected: dashboard tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/polybot/dashboard/static/index.html src/polybot/dashboard/static/app.js src/polybot/dashboard/static/styles.css tests/test_dashboard.py
git commit -m "feat: add tabbed dashboard controls"
```

---

### Task 7: Full Verification and Browser Check

**Files:**
- Review: all modified files

- [ ] **Step 1: Run full tests**

Run:

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Run Ruff**

Run:

```bash
uv run ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 3: Run dashboard locally**

Run:

```bash
uv run polybot dashboard --config configs/bot.example.toml
```

If port `8787` is busy, use a small Python launcher on port `8788` with `create_dashboard_app`.

- [ ] **Step 4: Browser verification**

Open the dashboard and verify:

- Monitor tab shows BTC price, target value, delta, market status, P/L, decisions, and recent events.
- Settings tab shows editable mode, strategy, staking, risk, and late-window fields.
- Logs tab shows decisions and events.
- Start button changes runtime state to running or an explicit error.
- Stop button returns runtime state to stopped.

- [ ] **Step 5: Final commit and push**

If any verification fixes were needed, commit them:

```bash
git add .
git commit -m "fix: polish dashboard control ui"
```

Then push:

```bash
git push
```

---

## Self-Review

- Spec coverage: Monitor values, Settings editing, Logs split, start/stop runtime control, paper/live mode support, validation, and verification are all mapped to tasks.
- Placeholder scan: no TBD/TODO/fill-in instructions remain; code snippets define concrete names and expected behavior.
- Type consistency: `runtime_status`, `feed_status`, `BotControlService`, `create_dashboard_app`, and settings methods use the same names across tasks.
