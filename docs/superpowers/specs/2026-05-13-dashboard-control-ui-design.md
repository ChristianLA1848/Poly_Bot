# Dashboard Control UI Design

## Goal

Extend the local Polybot dashboard from a passive status view into a tabbed control surface. The dashboard must show the live BTC price, the current event target value, and enough market context to understand why the bot is or is not trading. It must also allow the user to configure, start, stop, and monitor the bot in both paper and live modes.

## Confirmed Layout

Use a tabbed dashboard with three sections:

1. **Monitor**
   - BTC reference price from the latest feed aggregate.
   - Current event target value, defined as the bot's `reference_start_price` for the active 5-minute event.
   - Delta between BTC price and target value.
   - Bot runtime state: stopped, starting, running, stopping, or error.
   - Current market status, today's P/L, recent decisions, and high-signal recent events.

2. **Settings**
   - Editable settings for:
     - bot mode: `paper` or `live`
     - cycle seconds
     - strategy: `baseline_momentum` or `late_window`
     - staking mode: `fixed`, `fractional_kelly`, or `confidence_tiering`
     - fixed stake and Kelly fraction
     - core risk limits
     - late-window parameters
   - Server-side validation must use the existing `BotConfig` model.
   - Settings changes apply to the next bot start. Running bots are not hot-reconfigured.

3. **Logs**
   - Recent events.
   - Recent decisions.
   - Later expansion point for audit/order-result rows.

## Runtime Control

Add a dashboard-side bot control service. The service owns a single background task:

- `Start` validates the current config, builds the configured execution engine, and starts a loop.
- Each loop iteration fetches the BTC feed aggregate, creates or reuses the bot runner, runs one bot cycle, records state, sleeps for `cycle_seconds`, and repeats.
- `Stop` requests a graceful shutdown after the current cycle.
- If live mode is selected, missing Polymarket environment variables are surfaced as a dashboard error instead of a traceback.
- Only one bot loop may run at a time.

## Data Model

Persist enough runtime state for the dashboard snapshot:

- latest BTC price
- latest feed freshness and max deviation
- active event target value
- delta to target in absolute and percent terms
- bot runtime state and last runtime error

The existing market status table remains the source for market slug, question, end time, orderability, tick size, and minimum order size.

## API Design

Extend the dashboard API with:

- `GET /api/snapshot`
  - Existing snapshot fields plus runtime state, feed/target fields, and current settings.
- `POST /api/bot/start`
  - Starts the background loop if stopped.
- `POST /api/bot/stop`
  - Requests graceful stop.
- `GET /api/settings`
  - Returns editable settings.
- `PUT /api/settings`
  - Validates and stores editable settings for the next start.

## Error Handling

- Invalid settings return a structured validation response.
- Starting while already running returns the current runtime state.
- Stopping while already stopped is harmless.
- Feed/API errors are recorded in runtime state and as bot events; the loop continues unless start-up configuration is invalid.
- Live-mode credential errors prevent start and show a clear dashboard message.

## Testing

Use test-first implementation for:

- state store persistence for runtime/feed/target status
- control service start/stop behavior
- settings validation and persistence
- API routes for start, stop, settings, and snapshot
- dashboard HTML contains tab structure and controls
- bot loop records BTC price, target value, and delta for the snapshot

Full verification before completion:

- `uv run pytest -v`
- `uv run ruff check .`
- browser check of the dashboard tabs and visible runtime fields
