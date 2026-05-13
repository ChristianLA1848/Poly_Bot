# Trading Quality Strategies Design

## Purpose

Improve the bot's trading quality before adding more usability features. The next development package should make strategy decisions more explainable, add strategy-specific market compatibility, and support multiple selectable approaches instead of forcing all trading behavior through one BTC 5-minute tactic.

## Scope

This design covers the trading-quality layer only:

- A shared market snapshot used by all strategies.
- A strategy registry with selectable strategies.
- A refined BTC 5-minute late-window strategy.
- A trend-following strategy prepared for longer windows.
- Structured decision reasons for dashboard/debugging.

This design does not cover broader dashboard simplification, onboarding, or live-wallet reconciliation. Those belong to the next usability/safety package.

## Strategy Profiles

### Late Window 5m

This strategy is specialized for BTC 5-minute Up/Down events.

It should avoid early entries and only evaluate trades near the end of the window, for example in the final 60-120 seconds. It should compare the fixed event target price with the current BTC price, estimate whether BTC is likely to cross back over the target before expiry, and only trade when the expected return is still attractive.

Typical requirements:

- Event is the current BTC 5-minute window.
- Target price is fixed from the event open price or `priceToBeat`.
- Feed is fresh and internally consistent.
- Spread and liquidity pass risk filters.
- Remaining return is within configured bounds, such as 1-10%.
- No existing open position blocks the trade.

### Trend Following

This strategy is intended for longer windows and should not be the primary tactic for BTC 5-minute markets.

It should evaluate broader trend behavior before entering earlier in the event. Inputs should include recent price momentum, volatility, moving averages, remaining time, market price, spread, and liquidity. The first version can be conservative and focus on generating explainable decisions rather than high trade frequency.

Typical requirements:

- Market window is long enough for trend analysis.
- Price history has enough samples.
- Estimated probability exceeds market-implied probability by a configured edge.
- Volatility is not too chaotic for the configured risk profile.

## Shared Market Snapshot

Strategies should receive a normalized snapshot instead of pulling scattered fields from the bot runner.

The snapshot should include:

- Market identity: slug, question, token IDs, start/end times, accepting order status.
- Event timing: seconds elapsed, seconds remaining, window duration.
- Target/reference: fixed target price, current BTC price, absolute and percentage delta.
- Orderbook: best bid/ask for Up and Down, spread, available sizes.
- Feed quality: freshness, max deviation, source count.
- Position context: open position count, current event exposure, today P/L if available.

The snapshot should be serializable so it can later support replay/backtesting.

## Strategy Interface

Each strategy should expose:

- A stable name used in config and dashboard.
- A display label.
- Supported market profile, such as `btc_5m`, `longer_crypto`, or `all_crypto`.
- A parameter schema for dashboard editing.
- A `decide(snapshot)` function returning a structured decision.

Decisions should include:

- Action: buy up, buy down, sell, or no trade.
- Token ID and target price when relevant.
- Estimated probability.
- Market-implied probability.
- Edge.
- Confidence.
- Expected return.
- Reason code.
- Human-readable reason.

Examples of reason codes:

- `too_early`
- `target_missing`
- `feed_stale`
- `spread_too_high`
- `edge_too_low`
- `return_out_of_range`
- `late_window_high_confidence`
- `trend_confirmed`
- `trend_not_supported_for_market`

## Strategy Registry

The bot should load strategies through a registry instead of direct module-specific assumptions.

The registry should allow:

- Listing all available strategies.
- Selecting one strategy by config/dashboard.
- Checking whether the selected strategy supports the active market.
- Returning a clear no-trade decision when the strategy is incompatible with the active market.

Initial registry entries:

- `baseline_momentum`
- `late_window_5m`
- `trend_following`

The existing `late_window` strategy can either be migrated into `late_window_5m` or kept as a compatibility alias.

## Dashboard Impact

The dashboard should eventually expose the new strategy layer, but the first implementation should keep UI changes focused.

Minimum dashboard additions:

- Strategy dropdown uses registry metadata.
- Active strategy compatibility status.
- Last decision reason code.
- Last estimated probability, market probability, edge, and confidence.

Parameter editing can remain simple at first and continue using the existing settings tab. A richer per-strategy editor can be part of the later usability/safety phase.

## Data Flow

One bot cycle should follow this flow:

1. Discover current market.
2. Load fixed target price.
3. Load price feed.
4. Load orderbooks.
5. Build market snapshot.
6. Load selected strategy from registry.
7. Ask strategy for a structured decision.
8. Store decision details and reason codes.
9. Apply risk gate.
10. Calculate stake.
11. Execute paper/live order when allowed.

## Error Handling

Missing or unreliable inputs should produce no-trade decisions rather than exceptions where possible.

Examples:

- Missing target price: `NO_TRADE / target_missing`
- Incompatible strategy and market: `NO_TRADE / strategy_not_supported`
- Stale feed: `NO_TRADE / feed_stale`
- Missing orderbook: record warning and skip execution

Unexpected implementation errors should still be recorded as bot events and should not silently disappear.

## Testing

Tests should cover:

- Snapshot construction from market, feed, orderbook, and timing inputs.
- Strategy registry listing and loading.
- Strategy compatibility checks.
- Late-window strategy no-trade paths: too early, missing target, low edge, bad spread, return outside range.
- Late-window strategy buy paths for Up and Down.
- Trend-following strategy rejects unsupported 5-minute markets.
- Dashboard snapshot includes decision reason and edge fields.

## Implementation Order

1. Add market snapshot model and tests.
2. Add structured decision fields and reason codes.
3. Add strategy registry metadata and compatibility checks.
4. Implement `late_window_5m` using the snapshot.
5. Add a conservative `trend_following` skeleton for longer windows.
6. Surface decision reasons and compatibility in the dashboard.

## Success Criteria

The package is complete when:

- The bot can select between at least `baseline_momentum`, `late_window_5m`, and `trend_following`.
- BTC 5-minute late-window trading uses target price, remaining time, orderbook price, spread, and expected return.
- Trend-following refuses BTC 5-minute markets unless explicitly configured otherwise.
- Every no-trade path records a clear reason code.
- Tests pass and the dashboard exposes the last strategy reason.
