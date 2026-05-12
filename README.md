# Polymarket BTC Bot

A private Polymarket BTC 5-minute event trading bot with paper execution, configuration checks, and a local dashboard.

## Setup

Install the project with development dependencies:

```sh
uv sync --extra dev
```

Create local environment and bot configuration files:

```sh
cp .env.example .env
cp configs/bot.example.toml configs/bot.local.toml
```

The default bot mode is `paper`. Keep secrets in `.env`; do not commit real credentials or private keys.

## Check Configuration

Validate the local configuration before running the bot:

```sh
uv run polybot check-config --config configs/bot.local.toml
```

## Run One Paper Cycle

Run one bot cycle with paper execution:

```sh
uv run polybot run --config configs/bot.local.toml
```

## Dashboard

Start the local dashboard:

```sh
uv run polybot dashboard --config configs/bot.local.toml
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787).

Stop the dashboard process when finished.

## Live Trading Variables

Live trading requires credentials in `.env`:

```sh
POLYMARKET_PRIVATE_KEY=
POLYMARKET_API_KEY=
POLYMARKET_API_SECRET=
POLYMARKET_API_PASSPHRASE=
POLYMARKET_FUNDER_ADDRESS=
```
