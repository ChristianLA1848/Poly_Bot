# Paper Trade Limits And Analytics Design

## Purpose

Add tighter event-level trading controls and make paper-mode behavior measurable. The bot should be able to limit how many trades it opens per event, store paper trades as first-class records, evaluate finished paper trades, and show a graph for trade performance.

## Scope

This package covers:

- Per-event trade limits.
- Paper trade persistence.
- Paper trade result evaluation.
- Dashboard analytics data.
- A basic trade performance graph.

This package does not implement full historical market replay from external data. It creates the journal and analytics foundation needed for real backtesting later.

## Event Trade Limits

The bot should prevent uncontrolled repeated entries in the same event.

Add risk settings:

```toml
[risk]
max_trades_per_event = 1
max_event_exposure = 10.0
```

Default behavior should be conservative:

- `max_trades_per_event = 1`
- `max_event_exposure` should default to the configured `max_stake` when not explicitly set, or use a small explicit default in the example config.

Before placing an order, the bot should check existing trades for the active event. If the limit is reached, it should not place another order and should record a risk block or no-trade event with reason code:

```text
event_trade_limit_reached
```

The limit should apply to paper trades immediately. The same data model should be compatible with future live-trade tracking.

## Paper Trade Journal

Paper-mode fills should be stored in a dedicated persistent table rather than only as decisions/events.

Each paper trade record should include:

- `id`
- `created_at`
- `event_slug`
- `market_id`
- `token_id`
- `action`
- `strategy`
- `reason_code`
- `stake`
- `price`
- `shares`
- `status`
- `estimated_probability`
- `market_probability`
- `edge`
- `target_price`
- `btc_price_at_entry`
- `event_end_time`

The journal should be append-only for executed paper trades. Decision records remain useful, but the paper trade journal becomes the source of truth for paper performance analytics.

## Paper Trade Evaluation

The first version should evaluate paper trades after the event end time.

Evaluation rule:

- `BUY_UP` wins if final BTC price is greater than or equal to the target price.
- `BUY_DOWN` wins if final BTC price is below the target price.
- Winning payout is `shares * 1.0`.
- Losing payout is `0.0`.
- `pnl = payout - stake`
- `pnl_pct = pnl / stake` when stake is positive.

The bot can use the latest available BTC feed after event end as the first pragmatic final-price source. Later, this can be replaced or reconciled with official Polymarket/Data API resolution data.

Each evaluated trade should store:

- `resolved_at`
- `final_btc_price`
- `outcome`
- `payout`
- `pnl`
- `pnl_pct`

Trades whose event has not ended should remain open.

## Analytics API

The dashboard snapshot or a dedicated endpoint should expose paper analytics.

Minimum analytics fields:

- total trades
- open trades
- resolved trades
- winning trades
- losing trades
- win rate
- total P/L
- average P/L
- average edge
- trades grouped by strategy
- equity curve points
- recent paper trades

Equity curve points should be ordered by resolution time and include cumulative P/L:

```json
{
  "resolved_at": "2026-05-13T20:25:00+00:00",
  "pnl": 1.25,
  "cumulative_pnl": 3.75
}
```

## Dashboard Analytics

Add an Analytics view or extend the existing dashboard with an analytics section.

The UI should show:

- total paper P/L
- win rate
- open/resolved trade counts
- average edge
- recent paper trades
- an equity curve graph

The first graph can be a lightweight SVG or Canvas implementation in `app.js`. No external charting library is required for the first version.

Graph requirements:

- Show cumulative paper P/L over time.
- Handle empty data with a clean empty state.
- Use green for positive territory and red for negative territory where practical.
- Avoid layout shifts and overflowing labels on mobile.

## Data Flow

One bot cycle should follow this paper-trade flow:

1. Discover active event.
2. Load feed, target price, and orderbooks.
3. Build strategy decision.
4. Apply risk gate.
5. Check per-event trade limits.
6. Calculate stake.
7. Execute paper order.
8. Persist paper trade record.
9. On later cycles, evaluate open paper trades whose event end time has passed.
10. Dashboard reads analytics from the persisted trade journal.

## Error Handling

Paper analytics should not break trading.

Expected handling:

- Missing final BTC price: leave trade open and record no warning unless it persists.
- Invalid trade record: exclude it from analytics and record a warning event.
- Trade limit reached: record a clear block reason and do not place an order.
- Empty analytics: dashboard displays zero values and an empty graph state.

## Testing

Tests should cover:

- Config accepts `max_trades_per_event` and `max_event_exposure`.
- State store creates and reads paper trade records.
- Paper execution records trade details after fills.
- Bot blocks a second trade in the same event when limit is one.
- Bot allows another trade in a different event.
- Paper trade evaluation calculates win/loss P/L correctly.
- Analytics summary aggregates trade counts, win rate, P/L, average edge, and equity curve.
- Dashboard snapshot or endpoint includes analytics.
- Dashboard HTML/JS includes and renders the graph empty state.

## Success Criteria

The package is complete when:

- The bot cannot open more than the configured number of trades per event.
- Paper fills are persisted in a dedicated journal.
- Paper trades can be evaluated after event end.
- Dashboard exposes paper P/L and trade analytics.
- Dashboard shows an equity curve graph.
- Full tests, lint, JS syntax check, and one paper bot cycle pass.
