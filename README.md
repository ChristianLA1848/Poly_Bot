# Polymarket BTC Bot

Private bot for Polymarket BTC 5-minute Up/Down events. The bot discovers the current 5-minute BTC event from the `btc-updown-5m-<timestamp>` slug, reads BTC price feeds, evaluates the selected strategy, applies risk/staking rules, and can run in paper or live mode from the local dashboard.

## What The Software Does

- Trades the current BTC 5-minute Up/Down event window.
- Calculates the active event slug from the current UTC 5-minute window.
- Shows BTC price, event target/reference value, market status, runtime status, decisions, and events in a local dashboard.
- Lets you start/stop the bot from the dashboard.
- Lets you edit paper/live mode, strategy, staking, risk, and late-window settings from the dashboard.
- Supports paper execution by default and live execution when Polymarket credentials are configured.

## Requirements

- macOS/Linux shell
- Python managed by `uv`
- Internet access for Polymarket Gamma/CLOB APIs and BTC price feeds
- For live trading only: Polymarket wallet/API credentials and funded account

Install `uv` if it is not available:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## First Setup

Install dependencies:

```sh
uv sync --extra dev
```

Create local files:

```sh
cp .env.example .env
cp configs/bot.example.toml configs/bot.local.toml
```

Keep real credentials only in `.env`. Do not commit `.env` or `configs/bot.local.toml`.

## Required Local Information

### Runtime Environment

The `.env` file controls local paths and live trading credentials:

```sh
POLYBOT_CONFIG=configs/bot.local.toml
POLYBOT_DB_PATH=./data/polybot.sqlite3
POLYBOT_AUDIT_LOG_PATH=./data/audit.jsonl
```

### Live Trading Credentials

Live mode needs these values in `.env`:

```sh
POLYMARKET_PRIVATE_KEY=
POLYMARKET_API_KEY=
POLYMARKET_API_SECRET=
POLYMARKET_API_PASSPHRASE=
POLYMARKET_FUNDER_ADDRESS=
```

Paper mode does not need real Polymarket credentials.

## Configuration

Edit `configs/bot.local.toml`.

Important fields:

```toml
[bot]
mode = "paper"          # paper or live
cycle_seconds = 1.0
dashboard_host = "127.0.0.1"
dashboard_port = 8787

[strategy]
name = "baseline_momentum"  # baseline_momentum or late_window

[staking]
mode = "fixed"              # fixed, fractional_kelly, confidence_tiering
fixed_stake = 5.0
kelly_fraction = 0.25

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
```

Validate configuration:

```sh
uv run polybot check-config --config configs/bot.local.toml
```

## Starting The Dashboard

Start the local dashboard:

```sh
uv run polybot dashboard --config configs/bot.local.toml
```

Open:

[http://127.0.0.1:8787](http://127.0.0.1:8787)

The dashboard has three tabs:

- **Monitor**: BTC price, target price, delta, market status, P/L, Start/Stop.
- **Settings**: mode, strategy, staking, risk, and late-window settings.
- **Logs**: recent decisions and recent bot events.

Settings saved in the dashboard apply to the next bot start. Stop and restart the bot loop after changing important settings.

## Running The Bot

### Dashboard Mode

1. Start the dashboard.
2. Open the **Settings** tab.
3. Choose `paper` or `live`.
4. Save settings.
5. Open the **Monitor** tab.
6. Click **Start**.
7. Click **Stop** to stop after the current cycle.

### One Cycle From CLI

Useful for testing:

```sh
uv run polybot run --config configs/bot.local.toml
```

This runs a single bot cycle and exits.

## Restarting

### Restart Bot Loop Only

In the dashboard:

1. Click **Stop**.
2. Wait until status is `stopped`.
3. Click **Start**.

### Restart Dashboard Process

In the terminal running the dashboard:

```sh
Ctrl+C
uv run polybot dashboard --config configs/bot.local.toml
```

### If Port 8787 Is Busy

Either stop the existing dashboard process or change this in `configs/bot.local.toml`:

```toml
[bot]
dashboard_port = 8788
```

Then restart the dashboard.

## Current 5-Minute Event Discovery

The bot always targets the current UTC 5-minute BTC event slug:

```text
btc-updown-5m-<window_start_timestamp>
```

Example:

```text
btc-updown-5m-1778690100
```

That timestamp is the start of the 5-minute window. The bot calls Gamma directly with:

```text
/markets?slug=btc-updown-5m-...&closed=false
```

This avoids stale BTC markets from the generic market listing.

## Common Dashboard Statuses

- `stopped`: bot loop is not running.
- `starting`: dashboard requested a bot start.
- `running`: bot loop is active.
- `stopping`: bot will stop after the current cycle.
- `error`: bot loop hit an error; check Recent Events.
- `market not found`: current 5-minute slug was not available from Gamma.
- `market not accepting orders`: current market exists, but Polymarket does not currently accept orders for it.
- `risk gate blocked: ...`: strategy wanted a trade, but risk rules blocked it.

## Live Mode Checklist

Before using `live`:

1. `.env` contains all `POLYMARKET_*` values.
2. Wallet/funder address has sufficient funds.
3. `configs/bot.local.toml` has `mode = "live"`.
4. Risk values are intentionally small at first.
5. Dashboard settings match the local config or have been saved before starting.
6. Run:

```sh
uv run polybot check-config --config configs/bot.local.toml
```

## Useful Verification Commands

Run tests:

```sh
uv run pytest -q
```

Run lint:

```sh
uv run ruff check .
```

Check JavaScript syntax:

```sh
node --check src/polybot/dashboard/static/app.js
```

## Local Data

Runtime data is stored under `./data/` by default:

- `data/polybot.sqlite3`: decisions, events, market status, feed status, runtime status, settings.
- `data/audit.jsonl`: audit trail for decisions, risk blocks, warnings, and order results.

These files are local runtime artifacts and are not required for a fresh install.
