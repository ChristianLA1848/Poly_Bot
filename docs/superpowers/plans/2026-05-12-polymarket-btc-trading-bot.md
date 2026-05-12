# Polymarket BTC Trading Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working private Polymarket BTC 5-minute Up/Down trading bot with paper/live execution, strategy selection, risk gates, staking modes, position tracking, persistence, and a local dashboard.

**Architecture:** Create a modular Python application under `src/polybot` with clear interfaces for market discovery, feeds, strategies, risk, staking, execution, persistence, and dashboard. The bot loop runs as an async service, persists events to SQLite/JSONL, and exposes a FastAPI dashboard and control API.

**Tech Stack:** Python 3.12, `uv`, FastAPI, Typer, Pydantic Settings, httpx, websockets, pytest, pytest-asyncio, sqlite3, official Polymarket Python SDK when available.

---

## File Structure

- `pyproject.toml`: project metadata, dependencies, console script, pytest config.
- `.env.example`: documented secret and runtime variables.
- `configs/bot.example.toml`: non-secret bot configuration.
- `src/polybot/__init__.py`: package marker.
- `src/polybot/cli.py`: Typer CLI for running bot, dashboard, config checks, and one-shot discovery.
- `src/polybot/config.py`: Pydantic settings and TOML config loader.
- `src/polybot/models.py`: shared dataclasses/enums for markets, feeds, decisions, orders, positions, P/L, and bot status.
- `src/polybot/state_store.py`: SQLite schema and repository functions.
- `src/polybot/audit_log.py`: JSONL append-only audit logging.
- `src/polybot/market_discovery.py`: Gamma API market discovery and parsing.
- `src/polybot/price_feeds.py`: BTC feed aggregation and validation.
- `src/polybot/orderbook.py`: CLOB orderbook REST client and snapshot parser.
- `src/polybot/strategies/base.py`: strategy protocol and registry.
- `src/polybot/strategies/baseline_momentum.py`: baseline strategy.
- `src/polybot/strategies/late_window.py`: late-window strategy.
- `src/polybot/risk.py`: risk-gate checks.
- `src/polybot/staking.py`: fixed, fractional Kelly, and confidence tier staking.
- `src/polybot/execution/base.py`: execution protocol.
- `src/polybot/execution/paper.py`: paper execution engine.
- `src/polybot/execution/live.py`: Polymarket live execution wrapper.
- `src/polybot/positions.py`: position manager and exit checks.
- `src/polybot/bot.py`: async orchestration loop.
- `src/polybot/dashboard/app.py`: FastAPI app and JSON endpoints.
- `src/polybot/dashboard/static/index.html`: dashboard shell.
- `src/polybot/dashboard/static/app.js`: dashboard polling and control actions.
- `src/polybot/dashboard/static/styles.css`: dashboard styling.
- `tests/`: focused unit and integration tests.

## Task 1: Project Scaffold and Configuration

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `configs/bot.example.toml`
- Create: `src/polybot/__init__.py`
- Create: `src/polybot/config.py`
- Create: `src/polybot/cli.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Initialize git repository**

Run: `git init`

Expected: repository initialized in `/Users/christianlabusch/Documents/Codex_Polymarket`.

- [ ] **Step 2: Write failing configuration tests**

Create `tests/test_config.py`:

```python
from pathlib import Path

from polybot.config import BotConfig, load_bot_config


def test_load_bot_config_from_toml(tmp_path: Path):
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(
        """
[bot]
mode = "paper"
cycle_seconds = 1.0

[risk]
max_stake = 10.0
max_daily_loss = 25.0
max_spread = 0.04
min_liquidity = 100.0
min_edge = 0.03
max_feed_age_ms = 2500
max_feed_deviation_bps = 20

[strategy]
name = "baseline_momentum"

[staking]
mode = "fixed"
fixed_stake = 5.0
kelly_fraction = 0.25

[exit]
mode = "hold_to_resolution"
""",
        encoding="utf-8",
    )

    cfg = load_bot_config(cfg_path)

    assert isinstance(cfg, BotConfig)
    assert cfg.bot.mode == "paper"
    assert cfg.risk.max_stake == 10.0
    assert cfg.strategy.name == "baseline_momentum"
    assert cfg.staking.fixed_stake == 5.0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`

Expected: FAIL with `ModuleNotFoundError` for `polybot` or missing `load_bot_config`.

- [ ] **Step 4: Add project metadata and dependencies**

Create `pyproject.toml`:

```toml
[project]
name = "polymarket-btc-bot"
version = "0.1.0"
description = "Private Polymarket BTC 5-minute event trading bot"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.30.0",
  "typer>=0.12.0",
  "pydantic>=2.8.0",
  "pydantic-settings>=2.4.0",
  "httpx>=0.27.0",
  "websockets>=12.0",
  "python-dotenv>=1.0.1",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2.0",
  "pytest-asyncio>=0.23.0",
  "ruff>=0.5.0",
]
trading = [
  "py-clob-client-v2>=0.23.0",
]

[project.scripts]
polybot = "polybot.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/polybot"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 5: Add config files**

Create `.env.example`:

```bash
POLYBOT_CONFIG=configs/bot.example.toml
POLYBOT_DB_PATH=./data/polybot.sqlite3
POLYBOT_AUDIT_LOG_PATH=./data/audit.jsonl
POLYMARKET_PRIVATE_KEY=0x0000000000000000000000000000000000000000000000000000000000000000
POLYMARKET_API_KEY=
POLYMARKET_API_SECRET=
POLYMARKET_API_PASSPHRASE=
POLYMARKET_FUNDER_ADDRESS=
```

Create `configs/bot.example.toml`:

```toml
[bot]
mode = "paper"
cycle_seconds = 1.0
dashboard_host = "127.0.0.1"
dashboard_port = 8787

[risk]
max_stake = 10.0
max_daily_loss = 25.0
max_spread = 0.04
min_liquidity = 100.0
min_edge = 0.03
max_feed_age_ms = 2500
max_feed_deviation_bps = 20
max_open_positions = 1
max_open_orders = 2

[strategy]
name = "baseline_momentum"

[staking]
mode = "fixed"
fixed_stake = 5.0
kelly_fraction = 0.25
low_confidence_stake = 2.0
medium_confidence_stake = 5.0
high_confidence_stake = 10.0

[exit]
mode = "hold_to_resolution"
profit_target = 0.08
stop_loss = 0.05

[late_window]
min_seconds_remaining = 20
max_seconds_remaining = 60
min_expected_return = 0.01
max_expected_return = 0.10
min_confidence = 0.80
```

- [ ] **Step 6: Implement config loader and CLI skeleton**

Create `src/polybot/__init__.py`:

```python
__all__ = ["__version__"]
__version__ = "0.1.0"
```

Create `src/polybot/config.py`:

```python
from pathlib import Path
import tomllib

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POLYBOT_", env_file=".env", extra="ignore")

    config: str = "configs/bot.example.toml"
    db_path: str = "./data/polybot.sqlite3"
    audit_log_path: str = "./data/audit.jsonl"


class BotSection(BaseModel):
    mode: str = "paper"
    cycle_seconds: float = 1.0
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8787


class RiskSection(BaseModel):
    max_stake: float
    max_daily_loss: float
    max_spread: float
    min_liquidity: float
    min_edge: float
    max_feed_age_ms: int
    max_feed_deviation_bps: int
    max_open_positions: int = 1
    max_open_orders: int = 2


class StrategySection(BaseModel):
    name: str = "baseline_momentum"


class StakingSection(BaseModel):
    mode: str = "fixed"
    fixed_stake: float = 5.0
    kelly_fraction: float = Field(default=0.25, ge=0.0, le=1.0)
    low_confidence_stake: float = 2.0
    medium_confidence_stake: float = 5.0
    high_confidence_stake: float = 10.0


class ExitSection(BaseModel):
    mode: str = "hold_to_resolution"
    profit_target: float = 0.08
    stop_loss: float = 0.05


class LateWindowSection(BaseModel):
    min_seconds_remaining: int = 20
    max_seconds_remaining: int = 60
    min_expected_return: float = 0.01
    max_expected_return: float = 0.10
    min_confidence: float = 0.80


class BotConfig(BaseModel):
    bot: BotSection
    risk: RiskSection
    strategy: StrategySection
    staking: StakingSection
    exit: ExitSection
    late_window: LateWindowSection = Field(default_factory=LateWindowSection)


def load_bot_config(path: str | Path) -> BotConfig:
    config_path = Path(path)
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return BotConfig.model_validate(data)
```

Create `src/polybot/cli.py`:

```python
from pathlib import Path

import typer

from polybot.config import RuntimeSettings, load_bot_config

app = typer.Typer(help="Polymarket BTC event trading bot")


@app.command()
def check_config(config: Path | None = None) -> None:
    settings = RuntimeSettings()
    cfg = load_bot_config(config or settings.config)
    typer.echo(cfg.model_dump_json(indent=2))


@app.command()
def run() -> None:
    typer.echo("Bot runner will be enabled after core tasks are implemented.")


@app.command()
def dashboard() -> None:
    typer.echo("Dashboard runner will be enabled after dashboard tasks are implemented.")
```

- [ ] **Step 7: Run configuration tests**

Run: `uv run pytest tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .env.example configs/bot.example.toml src/polybot/__init__.py src/polybot/config.py src/polybot/cli.py tests/test_config.py
git commit -m "chore: scaffold bot project and config"
```

## Task 2: Shared Models and Persistence

**Files:**
- Create: `src/polybot/models.py`
- Create: `src/polybot/state_store.py`
- Create: `src/polybot/audit_log.py`
- Test: `tests/test_state_store.py`

- [ ] **Step 1: Write failing persistence tests**

Create `tests/test_state_store.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_state_store.py -v`

Expected: FAIL because `polybot.models` or `StateStore` does not exist.

- [ ] **Step 3: Implement shared models**

Create `src/polybot/models.py`:

```python
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class DecisionAction(StrEnum):
    BUY_UP = "BUY_UP"
    BUY_DOWN = "BUY_DOWN"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"


class ExecutionMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


@dataclass(frozen=True)
class Market:
    market_id: str
    question: str
    slug: str
    up_token_id: str
    down_token_id: str
    start_time: datetime | None
    end_time: datetime
    tick_size: float
    min_size: float
    accepting_orders: bool


@dataclass(frozen=True)
class FeedPrice:
    source: str
    symbol: str
    value: float
    timestamp_ms: int


@dataclass(frozen=True)
class FeedAggregate:
    reference_price: float
    prices: list[FeedPrice]
    max_deviation_bps: float
    fresh: bool
    created_at: datetime


@dataclass(frozen=True)
class OrderbookSnapshot:
    market_id: str
    token_id: str
    best_bid: float
    best_ask: float
    spread: float
    bid_size: float
    ask_size: float
    timestamp_ms: int


@dataclass(frozen=True)
class Decision:
    strategy: str
    action: DecisionAction
    market_id: str
    token_id: str
    target_price: float
    estimated_probability: float
    confidence: float
    expected_return: float
    max_slippage: float
    reason: str
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        data["created_at"] = self.created_at.isoformat()
        return data


@dataclass(frozen=True)
class BotEvent:
    level: str
    message: str
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data
```

- [ ] **Step 4: Implement SQLite store and audit log**

Create `src/polybot/state_store.py`:

```python
from pathlib import Path
import json
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
```

Create `src/polybot/audit_log.py`:

```python
from pathlib import Path
import json
from typing import Any


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event_type: str, payload: dict[str, Any]) -> None:
        record = {"type": event_type, "payload": payload}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
```

- [ ] **Step 5: Run persistence tests**

Run: `uv run pytest tests/test_state_store.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/polybot/models.py src/polybot/state_store.py src/polybot/audit_log.py tests/test_state_store.py
git commit -m "feat: add models and local persistence"
```

## Task 3: Market Discovery and Orderbook Readers

**Files:**
- Create: `src/polybot/market_discovery.py`
- Create: `src/polybot/orderbook.py`
- Test: `tests/test_market_discovery.py`
- Test: `tests/test_orderbook.py`

- [ ] **Step 1: Write failing parser tests**

Create `tests/test_market_discovery.py`:

```python
from polybot.market_discovery import parse_btc_market


def test_parse_btc_market_extracts_tokens():
    payload = {
        "id": "100",
        "conditionId": "0xabc",
        "question": "Bitcoin Up or Down - May 12, 9:00PM ET",
        "slug": "bitcoin-up-or-down-may-12-9pm-et",
        "endDateIso": "2026-05-12T21:05:00Z",
        "startDateIso": "2026-05-12T21:00:00Z",
        "outcomes": '["Up", "Down"]',
        "clobTokenIds": '["111", "222"]',
        "orderPriceMinTickSize": 0.01,
        "orderMinSize": 5,
        "acceptingOrders": True,
    }

    market = parse_btc_market(payload)

    assert market.market_id == "0xabc"
    assert market.up_token_id == "111"
    assert market.down_token_id == "222"
    assert market.tick_size == 0.01
    assert market.accepting_orders is True
```

Create `tests/test_orderbook.py`:

```python
from polybot.orderbook import parse_orderbook


def test_parse_orderbook_best_bid_ask():
    payload = {
        "market": "0xabc",
        "asset_id": "111",
        "bids": [{"price": "0.48", "size": "40"}],
        "asks": [{"price": "0.52", "size": "30"}],
        "timestamp": "1760000000000",
    }

    book = parse_orderbook(payload)

    assert book.best_bid == 0.48
    assert book.best_ask == 0.52
    assert book.spread == 0.04
    assert book.bid_size == 40.0
    assert book.ask_size == 30.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_market_discovery.py tests/test_orderbook.py -v`

Expected: FAIL because parser modules do not exist.

- [ ] **Step 3: Implement market discovery parser and client**

Create `src/polybot/market_discovery.py`:

```python
from datetime import datetime
import json
from typing import Any

import httpx

from polybot.models import Market

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"


def _loads_list(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return value
    return list(json.loads(value))


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_btc_market(payload: dict[str, Any]) -> Market:
    outcomes = _loads_list(payload["outcomes"])
    token_ids = _loads_list(payload["clobTokenIds"])
    token_by_outcome = {outcome.lower(): token for outcome, token in zip(outcomes, token_ids, strict=True)}
    return Market(
        market_id=payload["conditionId"],
        question=payload.get("question") or "",
        slug=payload.get("slug") or "",
        up_token_id=token_by_outcome["up"],
        down_token_id=token_by_outcome["down"],
        start_time=_parse_dt(payload["startDateIso"]) if payload.get("startDateIso") else None,
        end_time=_parse_dt(payload["endDateIso"]),
        tick_size=float(payload.get("orderPriceMinTickSize") or 0.01),
        min_size=float(payload.get("orderMinSize") or 5.0),
        accepting_orders=bool(payload.get("acceptingOrders")),
    )


class MarketDiscovery:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client or httpx.AsyncClient(base_url=GAMMA_BASE_URL, timeout=10.0)

    async def find_btc_5m_market(self) -> Market | None:
        response = await self.client.get(
            "/markets",
            params={
                "closed": "false",
                "active": "true",
                "limit": 100,
                "order": "endDate",
                "ascending": "true",
            },
        )
        response.raise_for_status()
        for item in response.json():
            text = f"{item.get('question', '')} {item.get('slug', '')}".lower()
            if "bitcoin" in text and "up-or-down" in text and item.get("clobTokenIds"):
                return parse_btc_market(item)
        return None
```

- [ ] **Step 4: Implement orderbook parser and client**

Create `src/polybot/orderbook.py`:

```python
from typing import Any

import httpx

from polybot.models import OrderbookSnapshot

CLOB_BASE_URL = "https://clob.polymarket.com"


def _best(levels: list[dict[str, str]], reverse: bool) -> tuple[float, float]:
    parsed = [(float(level["price"]), float(level["size"])) for level in levels]
    price, size = sorted(parsed, key=lambda row: row[0], reverse=reverse)[0]
    return price, size


def parse_orderbook(payload: dict[str, Any]) -> OrderbookSnapshot:
    best_bid, bid_size = _best(payload.get("bids", []), reverse=True)
    best_ask, ask_size = _best(payload.get("asks", []), reverse=False)
    return OrderbookSnapshot(
        market_id=payload["market"],
        token_id=payload["asset_id"],
        best_bid=best_bid,
        best_ask=best_ask,
        spread=round(best_ask - best_bid, 6),
        bid_size=bid_size,
        ask_size=ask_size,
        timestamp_ms=int(payload["timestamp"]),
    )


class OrderbookClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client or httpx.AsyncClient(base_url=CLOB_BASE_URL, timeout=10.0)

    async def get_book(self, token_id: str) -> OrderbookSnapshot:
        response = await self.client.get("/book", params={"token_id": token_id})
        response.raise_for_status()
        return parse_orderbook(response.json())
```

- [ ] **Step 5: Run parser tests**

Run: `uv run pytest tests/test_market_discovery.py tests/test_orderbook.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/polybot/market_discovery.py src/polybot/orderbook.py tests/test_market_discovery.py tests/test_orderbook.py
git commit -m "feat: add market discovery and orderbook readers"
```

## Task 4: Price Feed Aggregator

**Files:**
- Create: `src/polybot/price_feeds.py`
- Test: `tests/test_price_feeds.py`

- [ ] **Step 1: Write failing aggregator tests**

Create `tests/test_price_feeds.py`:

```python
from datetime import UTC, datetime

from polybot.models import FeedPrice
from polybot.price_feeds import aggregate_prices


def test_aggregate_prices_uses_median_and_deviation():
    prices = [
        FeedPrice("pm_binance", "btcusdt", 100.0, 1_000_000),
        FeedPrice("pm_chainlink", "btc/usd", 100.1, 1_000_010),
        FeedPrice("coinbase", "BTC-USD", 99.9, 1_000_020),
    ]

    agg = aggregate_prices(prices, now_ms=1_001_000, max_age_ms=2_500)

    assert agg.reference_price == 100.0
    assert agg.fresh is True
    assert agg.max_deviation_bps < 11
    assert agg.created_at.tzinfo == UTC


def test_aggregate_prices_marks_stale():
    prices = [FeedPrice("pm_binance", "btcusdt", 100.0, 1_000_000)]

    agg = aggregate_prices(prices, now_ms=1_010_000, max_age_ms=2_500)

    assert agg.fresh is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_price_feeds.py -v`

Expected: FAIL because `aggregate_prices` does not exist.

- [ ] **Step 3: Implement aggregator**

Create `src/polybot/price_feeds.py`:

```python
from datetime import UTC, datetime
from statistics import median

from polybot.models import FeedAggregate, FeedPrice


def aggregate_prices(prices: list[FeedPrice], now_ms: int, max_age_ms: int) -> FeedAggregate:
    if not prices:
        return FeedAggregate(0.0, [], 0.0, False, datetime.fromtimestamp(now_ms / 1000, tz=UTC))

    reference = float(median([price.value for price in prices]))
    max_deviation_bps = max(
        abs(price.value - reference) / reference * 10_000 for price in prices
    )
    fresh = all(now_ms - price.timestamp_ms <= max_age_ms for price in prices)
    return FeedAggregate(
        reference_price=reference,
        prices=prices,
        max_deviation_bps=max_deviation_bps,
        fresh=fresh,
        created_at=datetime.fromtimestamp(now_ms / 1000, tz=UTC),
    )
```

- [ ] **Step 4: Run aggregator tests**

Run: `uv run pytest tests/test_price_feeds.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/polybot/price_feeds.py tests/test_price_feeds.py
git commit -m "feat: add BTC price feed aggregation"
```

## Task 5: Strategies

**Files:**
- Create: `src/polybot/strategies/__init__.py`
- Create: `src/polybot/strategies/base.py`
- Create: `src/polybot/strategies/baseline_momentum.py`
- Create: `src/polybot/strategies/late_window.py`
- Test: `tests/test_strategies.py`

- [ ] **Step 1: Write failing strategy tests**

Create `tests/test_strategies.py`:

```python
from datetime import UTC, datetime, timedelta

from polybot.models import FeedAggregate, FeedPrice, Market, OrderbookSnapshot, DecisionAction
from polybot.strategies.base import StrategyContext, load_strategy


def _market():
    now = datetime(2026, 5, 12, 21, 0, tzinfo=UTC)
    return Market("0xabc", "Bitcoin Up or Down", "btc-up-down", "up", "down", now, now + timedelta(minutes=5), 0.01, 5, True)


def _aggregate(price: float):
    now = datetime(2026, 5, 12, 21, 3, tzinfo=UTC)
    return FeedAggregate(price, [FeedPrice("a", "btc", price, 1)], 0.0, True, now)


def _book(token_id: str, bid: float, ask: float):
    return OrderbookSnapshot("0xabc", token_id, bid, ask, ask - bid, 200.0, 200.0, 1)


def test_baseline_strategy_buys_up_when_price_above_reference():
    ctx = StrategyContext(
        market=_market(),
        reference_start_price=100.0,
        feed=_aggregate(101.0),
        up_book=_book("up", 0.60, 0.62),
        down_book=_book("down", 0.38, 0.40),
        now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC),
    )

    decision = load_strategy("baseline_momentum").decide(ctx)

    assert decision.action == DecisionAction.BUY_UP
    assert decision.token_id == "up"
    assert decision.confidence > 0.5


def test_late_window_strategy_waits_outside_window():
    ctx = StrategyContext(
        market=_market(),
        reference_start_price=100.0,
        feed=_aggregate(101.0),
        up_book=_book("up", 0.92, 0.94),
        down_book=_book("down", 0.06, 0.08),
        now=datetime(2026, 5, 12, 21, 1, tzinfo=UTC),
    )

    decision = load_strategy("late_window").decide(ctx)

    assert decision.action == DecisionAction.NO_TRADE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_strategies.py -v`

Expected: FAIL because strategy modules do not exist.

- [ ] **Step 3: Implement strategy interface and registry**

Create `src/polybot/strategies/__init__.py`:

```python
from polybot.strategies.base import Strategy, StrategyContext, load_strategy

__all__ = ["Strategy", "StrategyContext", "load_strategy"]
```

Create `src/polybot/strategies/base.py`:

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from polybot.models import Decision, FeedAggregate, Market, OrderbookSnapshot


@dataclass(frozen=True)
class StrategyContext:
    market: Market
    reference_start_price: float
    feed: FeedAggregate
    up_book: OrderbookSnapshot
    down_book: OrderbookSnapshot
    now: datetime


class Strategy(Protocol):
    name: str

    def decide(self, context: StrategyContext) -> Decision:
        ...


def load_strategy(name: str) -> Strategy:
    if name == "baseline_momentum":
        from polybot.strategies.baseline_momentum import BaselineMomentumStrategy

        return BaselineMomentumStrategy()
    if name == "late_window":
        from polybot.strategies.late_window import LateWindowStrategy

        return LateWindowStrategy()
    raise ValueError(f"Unknown strategy: {name}")
```

- [ ] **Step 4: Implement baseline strategy**

Create `src/polybot/strategies/baseline_momentum.py`:

```python
from polybot.models import Decision, DecisionAction
from polybot.strategies.base import StrategyContext


class BaselineMomentumStrategy:
    name = "baseline_momentum"

    def decide(self, context: StrategyContext) -> Decision:
        delta = (context.feed.reference_price - context.reference_start_price) / context.reference_start_price
        if abs(delta) < 0.0005:
            return Decision(self.name, DecisionAction.NO_TRADE, context.market.market_id, "", 0.0, 0.5, 0.0, 0.0, 0.0, "price delta too small", context.now)

        if delta > 0:
            book = context.up_book
            action = DecisionAction.BUY_UP
        else:
            book = context.down_book
            action = DecisionAction.BUY_DOWN

        estimated_probability = min(0.95, max(0.05, 0.5 + abs(delta) * 40))
        target_price = book.best_ask
        expected_return = estimated_probability / target_price - 1 if target_price > 0 else 0.0
        confidence = min(0.99, 0.5 + abs(delta) * 50)

        return Decision(
            strategy=self.name,
            action=action,
            market_id=context.market.market_id,
            token_id=book.token_id,
            target_price=target_price,
            estimated_probability=estimated_probability,
            confidence=confidence,
            expected_return=expected_return,
            max_slippage=0.01,
            reason=f"btc delta {delta:.5f}",
            created_at=context.now,
        )
```

- [ ] **Step 5: Implement late-window strategy**

Create `src/polybot/strategies/late_window.py`:

```python
from polybot.models import Decision, DecisionAction
from polybot.strategies.base import StrategyContext


class LateWindowStrategy:
    name = "late_window"

    def decide(self, context: StrategyContext) -> Decision:
        seconds_remaining = (context.market.end_time - context.now).total_seconds()
        if seconds_remaining < 20 or seconds_remaining > 60:
            return Decision(self.name, DecisionAction.NO_TRADE, context.market.market_id, "", 0.0, 0.5, 0.0, 0.0, 0.0, "outside late window", context.now)

        delta = (context.feed.reference_price - context.reference_start_price) / context.reference_start_price
        if abs(delta) < 0.001:
            return Decision(self.name, DecisionAction.NO_TRADE, context.market.market_id, "", 0.0, 0.5, 0.0, 0.0, 0.0, "late window edge too small", context.now)

        book = context.up_book if delta > 0 else context.down_book
        action = DecisionAction.BUY_UP if delta > 0 else DecisionAction.BUY_DOWN
        estimated_probability = min(0.98, 0.80 + abs(delta) * 30)
        target_price = book.best_ask
        expected_return = estimated_probability / target_price - 1 if target_price > 0 else 0.0

        if expected_return < 0.01 or expected_return > 0.10:
            return Decision(self.name, DecisionAction.NO_TRADE, context.market.market_id, "", 0.0, estimated_probability, 0.0, expected_return, 0.0, "expected return outside late-window band", context.now)

        return Decision(self.name, action, context.market.market_id, book.token_id, target_price, estimated_probability, estimated_probability, expected_return, 0.005, "late-window probability and return accepted", context.now)
```

- [ ] **Step 6: Run strategy tests**

Run: `uv run pytest tests/test_strategies.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/polybot/strategies tests/test_strategies.py
git commit -m "feat: add selectable trading strategies"
```

## Task 6: Risk Gate and Staking

**Files:**
- Create: `src/polybot/risk.py`
- Create: `src/polybot/staking.py`
- Test: `tests/test_risk_and_staking.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_risk_and_staking.py`:

```python
from datetime import UTC, datetime

from polybot.config import RiskSection, StakingSection
from polybot.models import Decision, DecisionAction, FeedAggregate, FeedPrice, OrderbookSnapshot
from polybot.risk import RiskGate
from polybot.staking import calculate_stake


def _decision(price=0.5, probability=0.6, expected_return=0.2):
    return Decision("s", DecisionAction.BUY_UP, "m", "up", price, probability, 0.8, expected_return, 0.01, "ok", datetime(2026, 5, 12, tzinfo=UTC))


def _risk():
    return RiskSection(max_stake=10, max_daily_loss=25, max_spread=0.04, min_liquidity=100, min_edge=0.03, max_feed_age_ms=2500, max_feed_deviation_bps=20, max_open_positions=1, max_open_orders=2)


def test_risk_gate_accepts_clean_decision():
    feed = FeedAggregate(100, [FeedPrice("a", "btc", 100, 1)], 2, True, datetime(2026, 5, 12, tzinfo=UTC))
    book = OrderbookSnapshot("m", "up", 0.49, 0.50, 0.01, 200, 200, 1)

    result = RiskGate(_risk()).evaluate(_decision(), feed, book, today_pnl=0, open_positions=0, open_orders=0)

    assert result.accepted is True
    assert result.reason == "accepted"


def test_risk_gate_blocks_wide_spread():
    feed = FeedAggregate(100, [FeedPrice("a", "btc", 100, 1)], 2, True, datetime(2026, 5, 12, tzinfo=UTC))
    book = OrderbookSnapshot("m", "up", 0.40, 0.50, 0.10, 200, 200, 1)

    result = RiskGate(_risk()).evaluate(_decision(), feed, book, today_pnl=0, open_positions=0, open_orders=0)

    assert result.accepted is False
    assert result.reason == "spread too high"


def test_fractional_kelly_is_capped():
    stake = calculate_stake(
        StakingSection(mode="fractional_kelly", fixed_stake=5, kelly_fraction=0.25),
        _decision(price=0.50, probability=0.60),
        max_stake=10,
    )

    assert stake == 5.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_risk_and_staking.py -v`

Expected: FAIL because risk and staking modules do not exist.

- [ ] **Step 3: Implement risk gate**

Create `src/polybot/risk.py`:

```python
from dataclasses import dataclass

from polybot.config import RiskSection
from polybot.models import Decision, DecisionAction, FeedAggregate, OrderbookSnapshot


@dataclass(frozen=True)
class RiskResult:
    accepted: bool
    reason: str


class RiskGate:
    def __init__(self, config: RiskSection):
        self.config = config

    def evaluate(
        self,
        decision: Decision,
        feed: FeedAggregate,
        book: OrderbookSnapshot,
        today_pnl: float,
        open_positions: int,
        open_orders: int,
    ) -> RiskResult:
        if decision.action == DecisionAction.NO_TRADE:
            return RiskResult(False, "strategy returned no trade")
        if not feed.fresh:
            return RiskResult(False, "feed stale")
        if feed.max_deviation_bps > self.config.max_feed_deviation_bps:
            return RiskResult(False, "feed deviation too high")
        if book.spread > self.config.max_spread:
            return RiskResult(False, "spread too high")
        if min(book.bid_size, book.ask_size) < self.config.min_liquidity:
            return RiskResult(False, "liquidity too low")
        market_implied = decision.target_price
        if decision.estimated_probability - market_implied < self.config.min_edge:
            return RiskResult(False, "edge too low")
        if today_pnl <= -abs(self.config.max_daily_loss):
            return RiskResult(False, "daily loss limit hit")
        if open_positions >= self.config.max_open_positions:
            return RiskResult(False, "too many open positions")
        if open_orders >= self.config.max_open_orders:
            return RiskResult(False, "too many open orders")
        return RiskResult(True, "accepted")
```

- [ ] **Step 4: Implement staking**

Create `src/polybot/staking.py`:

```python
from polybot.config import StakingSection
from polybot.models import Decision


def calculate_stake(config: StakingSection, decision: Decision, max_stake: float) -> float:
    if config.mode == "fixed":
        return min(config.fixed_stake, max_stake)
    if config.mode == "fractional_kelly":
        price = decision.target_price
        probability = decision.estimated_probability
        if price <= 0 or price >= 1:
            return 0.0
        b = (1 - price) / price
        q = 1 - probability
        kelly_fraction = max(0.0, (b * probability - q) / b)
        stake = max_stake * kelly_fraction * config.kelly_fraction
        return round(min(stake, max_stake), 2)
    if config.mode == "confidence_tiering":
        if decision.confidence >= 0.80:
            return min(config.high_confidence_stake, max_stake)
        if decision.confidence >= 0.65:
            return min(config.medium_confidence_stake, max_stake)
        return min(config.low_confidence_stake, max_stake)
    raise ValueError(f"Unknown staking mode: {config.mode}")
```

- [ ] **Step 5: Run risk and staking tests**

Run: `uv run pytest tests/test_risk_and_staking.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/polybot/risk.py src/polybot/staking.py tests/test_risk_and_staking.py
git commit -m "feat: add risk gate and staking"
```

## Task 7: Execution Engines

**Files:**
- Create: `src/polybot/execution/__init__.py`
- Create: `src/polybot/execution/base.py`
- Create: `src/polybot/execution/paper.py`
- Create: `src/polybot/execution/live.py`
- Test: `tests/test_execution.py`

- [ ] **Step 1: Write failing paper execution tests**

Create `tests/test_execution.py`:

```python
from datetime import UTC, datetime

import pytest

from polybot.execution.paper import PaperExecutionEngine
from polybot.models import Decision, DecisionAction


@pytest.mark.asyncio
async def test_paper_execution_records_buy():
    engine = PaperExecutionEngine()
    decision = Decision("s", DecisionAction.BUY_UP, "m", "up", 0.50, 0.60, 0.8, 0.2, 0.01, "ok", datetime(2026, 5, 12, tzinfo=UTC))

    result = await engine.place_order(decision, stake=5.0)

    assert result["mode"] == "paper"
    assert result["status"] == "filled"
    assert result["shares"] == 10.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_execution.py -v`

Expected: FAIL because execution modules do not exist.

- [ ] **Step 3: Implement execution protocol and paper engine**

Create `src/polybot/execution/__init__.py`:

```python
from polybot.execution.paper import PaperExecutionEngine

__all__ = ["PaperExecutionEngine"]
```

Create `src/polybot/execution/base.py`:

```python
from typing import Any, Protocol

from polybot.models import Decision


class ExecutionEngine(Protocol):
    async def place_order(self, decision: Decision, stake: float) -> dict[str, Any]:
        ...

    async def cancel_all(self) -> dict[str, Any]:
        ...
```

Create `src/polybot/execution/paper.py`:

```python
from typing import Any

from polybot.models import Decision


class PaperExecutionEngine:
    async def place_order(self, decision: Decision, stake: float) -> dict[str, Any]:
        shares = round(stake / decision.target_price, 6) if decision.target_price > 0 else 0.0
        return {
            "mode": "paper",
            "status": "filled",
            "market_id": decision.market_id,
            "token_id": decision.token_id,
            "price": decision.target_price,
            "stake": stake,
            "shares": shares,
        }

    async def cancel_all(self) -> dict[str, Any]:
        return {"mode": "paper", "status": "cancelled"}
```

- [ ] **Step 4: Implement live execution wrapper with dependency injection**

Create `src/polybot/execution/live.py`:

```python
from typing import Any

from polybot.models import Decision


class LiveExecutionEngine:
    def __init__(self, clob_client: Any):
        self.clob_client = clob_client

    async def place_order(self, decision: Decision, stake: float) -> dict[str, Any]:
        size = round(stake / decision.target_price, 6)
        if hasattr(self.clob_client, "create_and_post_order"):
            response = self.clob_client.create_and_post_order(
                token_id=decision.token_id,
                price=decision.target_price,
                size=size,
                side="BUY",
            )
            return {"mode": "live", "status": "submitted", "response": response}
        raise RuntimeError("Configured CLOB client does not expose create_and_post_order")

    async def cancel_all(self) -> dict[str, Any]:
        if hasattr(self.clob_client, "cancel_all"):
            response = self.clob_client.cancel_all()
            return {"mode": "live", "status": "cancelled", "response": response}
        raise RuntimeError("Configured CLOB client does not expose cancel_all")
```

- [ ] **Step 5: Run execution tests**

Run: `uv run pytest tests/test_execution.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/polybot/execution tests/test_execution.py
git commit -m "feat: add paper and live execution engines"
```

## Task 8: Position Manager

**Files:**
- Create: `src/polybot/positions.py`
- Test: `tests/test_positions.py`

- [ ] **Step 1: Write failing position tests**

Create `tests/test_positions.py`:

```python
from polybot.positions import PositionManager


def test_position_manager_tracks_today_pnl():
    manager = PositionManager()
    manager.record_fill("m", "up", stake=5.0, shares=10.0, price=0.5)
    manager.mark_price("up", 0.6)

    assert manager.unrealized_pnl() == 1.0
    assert manager.open_positions_count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_positions.py -v`

Expected: FAIL because `PositionManager` does not exist.

- [ ] **Step 3: Implement position manager**

Create `src/polybot/positions.py`:

```python
from dataclasses import dataclass


@dataclass
class Position:
    market_id: str
    token_id: str
    stake: float
    shares: float
    entry_price: float
    mark_price: float


class PositionManager:
    def __init__(self):
        self.positions: dict[str, Position] = {}

    def record_fill(self, market_id: str, token_id: str, stake: float, shares: float, price: float) -> None:
        self.positions[token_id] = Position(market_id, token_id, stake, shares, price, price)

    def mark_price(self, token_id: str, price: float) -> None:
        if token_id in self.positions:
            self.positions[token_id].mark_price = price

    def unrealized_pnl(self) -> float:
        pnl = sum((position.mark_price - position.entry_price) * position.shares for position in self.positions.values())
        return round(pnl, 6)

    def open_positions_count(self) -> int:
        return len(self.positions)
```

- [ ] **Step 4: Run position tests**

Run: `uv run pytest tests/test_positions.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/polybot/positions.py tests/test_positions.py
git commit -m "feat: add position manager"
```

## Task 9: Bot Orchestration Loop

**Files:**
- Create: `src/polybot/bot.py`
- Modify: `src/polybot/cli.py`
- Test: `tests/test_bot_loop.py`

- [ ] **Step 1: Write failing orchestration test**

Create `tests/test_bot_loop.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest

from polybot.bot import BotRunner
from polybot.config import BotConfig, BotSection, ExitSection, LateWindowSection, RiskSection, StakingSection, StrategySection
from polybot.models import FeedAggregate, FeedPrice, Market, OrderbookSnapshot


class FakeMarketDiscovery:
    async def find_btc_5m_market(self):
        now = datetime(2026, 5, 12, 21, 0, tzinfo=UTC)
        return Market("m", "Bitcoin Up or Down", "slug", "up", "down", now, now + timedelta(minutes=5), 0.01, 5, True)


class FakeOrderbookClient:
    async def get_book(self, token_id):
        return OrderbookSnapshot("m", token_id, 0.49, 0.50, 0.01, 200, 200, 1)


class FakeExecution:
    def __init__(self):
        self.orders = []

    async def place_order(self, decision, stake):
        self.orders.append((decision, stake))
        return {"status": "filled", "shares": stake / decision.target_price, "stake": stake, "price": decision.target_price, "token_id": decision.token_id, "market_id": decision.market_id}

    async def cancel_all(self):
        return {"status": "cancelled"}


def _config():
    return BotConfig(
        bot=BotSection(mode="paper", cycle_seconds=1),
        risk=RiskSection(max_stake=10, max_daily_loss=25, max_spread=0.04, min_liquidity=100, min_edge=0.03, max_feed_age_ms=2500, max_feed_deviation_bps=20),
        strategy=StrategySection(name="baseline_momentum"),
        staking=StakingSection(mode="fixed", fixed_stake=5),
        exit=ExitSection(mode="hold_to_resolution"),
        late_window=LateWindowSection(),
    )


@pytest.mark.asyncio
async def test_bot_runner_single_cycle_places_paper_order(tmp_path):
    execution = FakeExecution()
    runner = BotRunner(
        config=_config(),
        market_discovery=FakeMarketDiscovery(),
        orderbook_client=FakeOrderbookClient(),
        execution=execution,
        store_path=tmp_path / "bot.sqlite3",
        reference_start_price=100.0,
    )
    runner.latest_feed = FeedAggregate(101.0, [FeedPrice("a", "btc", 101.0, 1)], 0, True, datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    await runner.run_once(now=datetime(2026, 5, 12, 21, 3, tzinfo=UTC))

    assert len(execution.orders) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot_loop.py -v`

Expected: FAIL because `BotRunner` does not exist.

- [ ] **Step 3: Implement bot runner**

Create `src/polybot/bot.py`:

```python
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from polybot.config import BotConfig
from polybot.market_discovery import MarketDiscovery
from polybot.models import BotEvent, FeedAggregate
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
    ):
        self.config = config
        self.market_discovery = market_discovery or MarketDiscovery()
        self.orderbook_client = orderbook_client or OrderbookClient()
        self.execution = execution
        self.store = StateStore(store_path)
        self.store.initialize()
        self.positions = PositionManager()
        self.reference_start_price = reference_start_price
        self.latest_feed: FeedAggregate | None = None

    async def run_once(self, now: datetime | None = None) -> None:
        now = now or datetime.now(tz=UTC)
        if self.latest_feed is None:
            self.store.record_event(BotEvent("warning", "no feed aggregate available", now))
            return

        market = await self.market_discovery.find_btc_5m_market()
        if market is None:
            self.store.record_event(BotEvent("warning", "market not found", now))
            return
        if not market.accepting_orders:
            self.store.record_event(BotEvent("warning", "market not accepting orders", now))
            return

        if self.reference_start_price is None:
            self.reference_start_price = self.latest_feed.reference_price

        up_book = await self.orderbook_client.get_book(market.up_token_id)
        down_book = await self.orderbook_client.get_book(market.down_token_id)
        strategy = load_strategy(self.config.strategy.name)
        context = StrategyContext(market, self.reference_start_price, self.latest_feed, up_book, down_book, now)
        decision = strategy.decide(context)
        self.store.record_decision(decision)

        selected_book = up_book if decision.token_id == market.up_token_id else down_book
        risk_result = RiskGate(self.config.risk).evaluate(
            decision,
            self.latest_feed,
            selected_book,
            today_pnl=self.positions.unrealized_pnl(),
            open_positions=self.positions.open_positions_count(),
            open_orders=0,
        )
        if not risk_result.accepted:
            self.store.record_event(BotEvent("info", f"risk gate blocked: {risk_result.reason}", now))
            return

        stake = calculate_stake(self.config.staking, decision, self.config.risk.max_stake)
        if self.execution is None:
            self.store.record_event(BotEvent("error", "execution engine missing", now))
            return
        result = await self.execution.place_order(decision, stake)
        if result.get("status") == "filled":
            self.positions.record_fill(result["market_id"], result["token_id"], result["stake"], result["shares"], result["price"])
        self.store.record_event(BotEvent("info", f"order result: {result.get('status')}", now))
```

- [ ] **Step 4: Wire CLI run command to create paper runner**

Modify `src/polybot/cli.py` so it contains:

```python
from pathlib import Path
import asyncio

import typer

from polybot.bot import BotRunner
from polybot.config import RuntimeSettings, load_bot_config
from polybot.execution.paper import PaperExecutionEngine

app = typer.Typer(help="Polymarket BTC event trading bot")


@app.command()
def check_config(config: Path | None = None) -> None:
    settings = RuntimeSettings()
    cfg = load_bot_config(config or settings.config)
    typer.echo(cfg.model_dump_json(indent=2))


@app.command()
def run(config: Path | None = None) -> None:
    settings = RuntimeSettings()
    cfg = load_bot_config(config or settings.config)
    runner = BotRunner(cfg, execution=PaperExecutionEngine(), store_path=settings.db_path)
    asyncio.run(runner.run_once())
    typer.echo("Completed one bot cycle.")


@app.command()
def dashboard() -> None:
    typer.echo("Dashboard runner will be enabled after dashboard tasks are implemented.")
```

- [ ] **Step 5: Run bot loop tests**

Run: `uv run pytest tests/test_bot_loop.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/polybot/bot.py src/polybot/cli.py tests/test_bot_loop.py
git commit -m "feat: add bot orchestration loop"
```

## Task 10: Local Dashboard

**Files:**
- Create: `src/polybot/dashboard/__init__.py`
- Create: `src/polybot/dashboard/app.py`
- Create: `src/polybot/dashboard/static/index.html`
- Create: `src/polybot/dashboard/static/app.js`
- Create: `src/polybot/dashboard/static/styles.css`
- Modify: `src/polybot/cli.py`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing dashboard test**

Create `tests/test_dashboard.py`:

```python
from fastapi.testclient import TestClient

from polybot.dashboard.app import create_dashboard_app
from polybot.state_store import StateStore


def test_dashboard_health_and_snapshot(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    app = create_dashboard_app(store)
    client = TestClient(app)

    health = client.get("/api/health")
    snapshot = client.get("/api/snapshot")

    assert health.json() == {"status": "ok"}
    assert snapshot.status_code == 200
    assert "recent_decisions" in snapshot.json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dashboard.py -v`

Expected: FAIL because dashboard app does not exist.

- [ ] **Step 3: Implement FastAPI dashboard**

Create `src/polybot/dashboard/__init__.py`:

```python
from polybot.dashboard.app import create_dashboard_app

__all__ = ["create_dashboard_app"]
```

Create `src/polybot/dashboard/app.py`:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from polybot.state_store import StateStore


def create_dashboard_app(store: StateStore) -> FastAPI:
    app = FastAPI(title="Polymarket BTC Bot Dashboard")
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/snapshot")
    def snapshot() -> dict:
        data = store.dashboard_snapshot()
        data.setdefault("bot_status", "ready")
        data.setdefault("today_pnl", 0.0)
        return data

    return app
```

- [ ] **Step 4: Add dashboard frontend files**

Create `src/polybot/dashboard/static/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Polymarket BTC Bot</title>
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body>
    <main>
      <header>
        <h1>Polymarket BTC Bot</h1>
        <div id="status">Loading</div>
      </header>
      <section class="metrics">
        <article><span>Today P/L</span><strong id="today-pnl">0.00</strong></article>
        <article><span>Decisions</span><strong id="decision-count">0</strong></article>
        <article><span>Events</span><strong id="event-count">0</strong></article>
      </section>
      <section>
        <h2>Recent Decisions</h2>
        <table>
          <thead><tr><th>Time</th><th>Strategy</th><th>Action</th><th>Reason</th></tr></thead>
          <tbody id="decisions"></tbody>
        </table>
      </section>
      <section>
        <h2>Recent Events</h2>
        <ul id="events"></ul>
      </section>
    </main>
    <script src="/static/app.js"></script>
  </body>
</html>
```

Create `src/polybot/dashboard/static/app.js`:

```javascript
async function refresh() {
  const response = await fetch("/api/snapshot");
  const snapshot = await response.json();
  document.getElementById("status").textContent = snapshot.bot_status || "ready";
  document.getElementById("today-pnl").textContent = Number(snapshot.today_pnl || 0).toFixed(2);
  document.getElementById("decision-count").textContent = snapshot.recent_decisions.length;
  document.getElementById("event-count").textContent = snapshot.recent_events.length;

  document.getElementById("decisions").innerHTML = snapshot.recent_decisions.map((decision) => `
    <tr>
      <td>${decision.created_at}</td>
      <td>${decision.strategy}</td>
      <td>${decision.action}</td>
      <td>${decision.reason}</td>
    </tr>
  `).join("");

  document.getElementById("events").innerHTML = snapshot.recent_events.map((event) => `
    <li><strong>${event.level}</strong> ${event.message}</li>
  `).join("");
}

refresh();
setInterval(refresh, 2000);
```

Create `src/polybot/dashboard/static/styles.css`:

```css
:root {
  color-scheme: light;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #f6f7f9;
  color: #16181d;
}

body {
  margin: 0;
}

main {
  max-width: 1180px;
  margin: 0 auto;
  padding: 24px;
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #d9dee7;
  padding-bottom: 16px;
}

h1, h2 {
  margin: 0;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 20px 0;
}

article {
  background: white;
  border: 1px solid #d9dee7;
  border-radius: 8px;
  padding: 16px;
}

article span {
  display: block;
  color: #616b7c;
  font-size: 13px;
}

article strong {
  display: block;
  font-size: 28px;
  margin-top: 6px;
}

table {
  width: 100%;
  border-collapse: collapse;
  background: white;
}

th, td {
  padding: 10px;
  border-bottom: 1px solid #e5e9f0;
  text-align: left;
}

ul {
  background: white;
  border: 1px solid #d9dee7;
  border-radius: 8px;
  padding: 12px 24px;
}
```

- [ ] **Step 5: Wire dashboard CLI**

Modify `src/polybot/cli.py` dashboard command:

```python
@app.command()
def dashboard(config: Path | None = None) -> None:
    import uvicorn

    settings = RuntimeSettings()
    cfg = load_bot_config(config or settings.config)
    from polybot.dashboard.app import create_dashboard_app
    from polybot.state_store import StateStore

    store = StateStore(settings.db_path)
    store.initialize()
    uvicorn.run(create_dashboard_app(store), host=cfg.bot.dashboard_host, port=cfg.bot.dashboard_port)
```

- [ ] **Step 6: Run dashboard tests**

Run: `uv run pytest tests/test_dashboard.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/polybot/dashboard src/polybot/cli.py tests/test_dashboard.py
git commit -m "feat: add local dashboard"
```

## Task 11: End-to-End Verification and Documentation

**Files:**
- Create: `README.md`
- Modify: `src/polybot/cli.py`

- [ ] **Step 1: Add README**

Create `README.md`:

```markdown
# Polymarket BTC Bot

Private automated bot for Polymarket BTC 5-minute Up/Down events.

## Setup

```bash
uv sync --extra dev
cp .env.example .env
cp configs/bot.example.toml configs/bot.local.toml
```

## Check configuration

```bash
uv run polybot check-config --config configs/bot.local.toml
```

## Run one paper cycle

```bash
uv run polybot run --config configs/bot.local.toml
```

## Dashboard

```bash
uv run polybot dashboard --config configs/bot.local.toml
```

Open `http://127.0.0.1:8787`.

## Live Trading Variables

Live trading requires Polymarket credentials in `.env`:

- `POLYMARKET_PRIVATE_KEY`
- `POLYMARKET_API_KEY`
- `POLYMARKET_API_SECRET`
- `POLYMARKET_API_PASSPHRASE`
- `POLYMARKET_FUNDER_ADDRESS`
```

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest -v`

Expected: all tests PASS.

- [ ] **Step 3: Run lint**

Run: `uv run ruff check src tests`

Expected: PASS. If it fails on import ordering or formatting, run `uv run ruff check src tests --fix` and then rerun `uv run ruff check src tests`.

- [ ] **Step 4: Smoke test CLI**

Run: `uv run polybot check-config --config configs/bot.example.toml`

Expected: JSON configuration printed with `"mode": "paper"` and `"name": "baseline_momentum"`.

- [ ] **Step 5: Smoke test dashboard endpoint**

Run: `uv run polybot dashboard --config configs/bot.example.toml`

Expected: Uvicorn starts on `http://127.0.0.1:8787`. Stop it with `Ctrl-C` after loading the dashboard.

- [ ] **Step 6: Commit**

```bash
git add README.md src/polybot/cli.py
git commit -m "docs: add setup and verification guide"
```

## Self-Review Checklist

- Spec coverage: the plan covers config, market discovery, multi-feed aggregation, orderbook reading, strategies, risk gate, staking, execution, positions, persistence, dashboard, and documentation.
- Completeness scan: every task has concrete file paths, commands, and expected outcomes.
- Type consistency: strategy decisions, risk gate, staking, execution, and bot loop all use `Decision`, `FeedAggregate`, `OrderbookSnapshot`, and `BotConfig` consistently.
