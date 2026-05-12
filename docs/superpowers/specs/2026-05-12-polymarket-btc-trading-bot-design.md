# Polymarket BTC Event Trading Bot Design

Date: 2026-05-12

## Goal

Build a private automated trading system for Polymarket BTC 5-minute Up/Down events. The system must be immediately usable, support paper trading and live trading, expose a local visual dashboard, and be structured so additional strategies can be added later.

The bot watches current and upcoming BTC 5-minute markets, collects several BTC price feeds, reads Polymarket orderbook data, generates strategy decisions, applies a hard risk gate, and then either records a paper trade or places a live order.

## Primary Operating Modes

The bot supports two execution modes:

- Paper mode: records simulated orders, fills, positions, and P/L without sending orders to Polymarket.
- Live mode: places authenticated Polymarket CLOB orders through the official SDK and signs orders locally.

Live mode is implemented in the MVP and is configurable. The execution layer must keep credentials out of source control and read secrets from environment variables.

## Strategies

Trading logic is implemented through a strategy interface. Strategies produce structured decisions but never place orders directly.

Initial strategies:

- Baseline Momentum Strategy: evaluates direction, momentum, distance from the event reference price, remaining time, spread, liquidity, and orderbook state across the whole 5-minute window.
- Late-Window Strategy: only considers trades near the end of the market window when the likely outcome is sufficiently clear and the market price still offers an acceptable expected return, for example 1-10%.

Future strategies can be added by implementing the same interface and returning the same decision shape.

## Decision Shape

Each strategy returns a decision such as:

- action: BUY_UP, BUY_DOWN, SELL, or NO_TRADE
- market and token identifiers
- target limit price
- estimated probability
- confidence score
- expected return
- maximum slippage
- suggested hold or exit behavior
- reason text and diagnostic fields

The execution engine only receives decisions after they pass risk and staking checks.

## Architecture

The system is a modular Python service with a local browser dashboard.

Core components:

- Config Layer: loads `.env` secrets and YAML or TOML bot settings.
- Market Discovery: finds active and upcoming BTC 5-minute Up/Down markets through the Polymarket Gamma API and validates token IDs, start/end time, tick size, minimum order size, active status, and accepting-orders status.
- Price Feed Aggregator: subscribes to several BTC feeds, including Polymarket RTDS Binance BTCUSDT, Polymarket RTDS Chainlink BTC/USD, and an optional direct exchange feed such as Binance or Coinbase. It validates freshness, rejects outliers, and computes a reference price.
- Orderbook Feed: reads Polymarket CLOB book, best bid/ask, spread, liquidity, and recent prices through REST and/or WebSocket.
- Strategy Engine: loads the configured strategy and produces decisions.
- Risk & Staking Engine: validates decisions, calculates stake size, and blocks unsafe trades.
- Execution Engine: implements paper and live execution. Live execution uses the Polymarket SDK, local order signing, order posting, cancellation, and heartbeat handling.
- Position Manager: tracks open orders, fills, positions, hold-to-resolution behavior, managed exits, expiry, and P/L.
- Journal and State Store: writes trades, orders, strategy decisions, market snapshots, feed snapshots, P/L, and errors to SQLite. JSONL audit logs are also written for robustness.
- Local Dashboard: browser UI that shows current bot state and metrics and exposes safe controls.

## Dashboard

The dashboard is part of the MVP.

It shows:

- bot status: running, paused, paper, live, degraded, or error
- active strategy and exit mode
- current BTC reference price and individual feed status
- active market, remaining time, Up/Down prices, spread, and liquidity
- open orders and positions
- today's realized and unrealized P/L
- total P/L, win/loss count, drawdown, and recent trades
- recent strategy decisions and risk-gate blocks
- recent errors, feed stale warnings, order rejections, and heartbeat status

It provides controls for:

- start and pause bot
- select paper or live mode
- select strategy
- select staking mode
- select exit mode
- set maximum stake and loss limits
- cancel all open orders

## Risk Gate

The risk gate is the last mandatory checkpoint before any order is submitted.

It blocks trades when:

- price feeds are stale
- BTC feeds disagree beyond configured tolerance
- required WebSocket or REST data is unavailable
- spread is too high
- orderbook liquidity is too low
- market metadata is missing or inconsistent
- trade is too close to expiry, unless the selected strategy explicitly supports late-window trading
- estimated probability does not exceed market-implied probability by the required edge
- expected return is below the configured threshold
- stake would exceed configured caps
- daily loss or drawdown limit has been hit
- too many positions or orders are already open
- cooldown after a losing streak is active

Risk limits include:

- maximum stake per trade
- maximum daily loss
- maximum open positions
- maximum open orders
- minimum feed freshness
- maximum feed deviation
- minimum expected edge
- maximum spread
- minimum liquidity

## Staking

The MVP supports three staking modes:

- Fixed Stake: uses a configured amount per trade.
- Fractional Kelly: uses estimated probability and market price to compute Kelly sizing, then applies a fraction such as 25% Kelly and hard caps.
- Confidence Tiering: maps low, medium, and high confidence decisions to configured stake levels.

All staking modes are capped by the risk gate.

## Exit Modes

The MVP supports two exit modes:

- Hold-to-Resolution: enter a position and hold it until market resolution.
- Managed Exit: monitor the position and attempt to sell before expiry when exit conditions trigger.

Managed exit conditions may include:

- signal reversal
- confidence drop
- profit target reached
- stop loss reached
- spread or liquidity deterioration
- time-based exit

## Data Flow

1. Market Discovery finds the current or next BTC 5-minute Up/Down event.
2. Price feeds update the BTC reference price and feed health.
3. Orderbook data updates Polymarket prices, spread, and liquidity.
4. Strategy Engine receives market state, BTC reference price, remaining time, and orderbook data.
5. Strategy Engine returns a decision.
6. Risk & Staking Engine validates the decision and calculates stake size.
7. Execution Engine records a paper trade or places a live order.
8. Position Manager tracks fills, exits, expiry, and P/L.
9. Journal writes all important state transitions to SQLite and JSONL.
10. Dashboard reads the state store and shows near-live status and metrics.

## Polymarket API Usage

The design uses the documented Polymarket APIs:

- Gamma API for market discovery.
- CLOB public endpoints and market WebSocket for orderbook and price data.
- CLOB authenticated endpoints for live orders, order queries, cancellations, and heartbeat.
- RTDS WebSocket for crypto price feeds.

Authenticated CLOB trading requires L1 private-key ownership for credential creation or derivation and L2 API credentials for trading endpoints. Even with L2 credentials, order payloads are signed locally.

## Error Handling

Errors are recorded as events and shown in the dashboard.

Important error classes:

- market not found
- market not accepting orders
- feed stale
- feed deviation too high
- orderbook stale
- risk gate blocked
- order rejected
- insufficient balance or allowance
- heartbeat failed
- WebSocket disconnected
- API rate limit or throttling
- execution mode misconfigured

The bot should fail closed: when required data is unavailable or inconsistent, it produces NO_TRADE and does not submit orders.

## MVP Scope

Included:

- Python project with CLI and local dashboard
- paper trading
- live trading layer through Polymarket SDK
- BTC 5-minute Up/Down market discovery
- multi-feed BTC aggregation
- CLOB orderbook and price reader
- Baseline Momentum Strategy
- Late-Window Strategy
- Fixed Stake, Fractional Kelly, and Confidence Tiering
- Hold-to-Resolution and Managed Exit
- SQLite state store and JSONL audit log
- dashboard for status, P/L, positions, orders, decisions, risk blocks, and feed health
- `.env.example` and setup commands

Excluded from MVP:

- cloud deployment
- multi-user support
- mobile app
- full historical backtesting suite
- builder-fee integration
- maker-rebate optimization
- automated strategy optimization
- support for many non-BTC market categories

## Acceptance Criteria

The MVP is acceptable when:

- the bot can discover the current BTC 5-minute Up/Down market
- paper mode can produce and record strategy decisions and simulated trades
- live mode can be configured and reaches authenticated readiness without source-controlled secrets
- the risk gate blocks invalid decisions and logs the reason
- both initial strategies can be selected from config or dashboard
- all staking modes can calculate a stake and respect caps
- both exit modes are selectable
- the dashboard displays bot status, active market, feed health, open positions, recent trades, and today's P/L
- all important bot decisions and execution events are persisted

