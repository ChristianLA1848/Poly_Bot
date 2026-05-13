import asyncio
import os
from pathlib import Path
import tomllib

from pydantic import ValidationError
from dotenv import load_dotenv
import typer
import uvicorn

from polybot.bot import BotRunner
from polybot.config import BotConfig
from polybot.config import RuntimeSettings, load_bot_config
from polybot.dashboard import create_dashboard_app
from polybot.dashboard.control import BotControlService
from polybot.execution.live import LiveExecutionEngine
from polybot.execution.paper import PaperExecutionEngine
from polybot.price_feeds import fetch_btc_feed_aggregate
from polybot.state_store import StateStore

app = typer.Typer(help="Polymarket BTC event trading bot")

LIVE_ENV_VARS = (
    "POLYMARKET_PRIVATE_KEY",
    "POLYMARKET_API_KEY",
    "POLYMARKET_API_SECRET",
    "POLYMARKET_API_PASSPHRASE",
    "POLYMARKET_FUNDER_ADDRESS",
)


class CliConfigError(RuntimeError):
    pass


def _load_config_or_exit(config: Path | str) -> BotConfig:
    try:
        return load_bot_config(config)
    except FileNotFoundError:
        typer.secho(f"Config file not found: {config}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from None
    except OSError as exc:
        typer.secho(f"Could not read config file: {config} ({exc})", err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from None
    except tomllib.TOMLDecodeError as exc:
        typer.secho(f"Invalid TOML config: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from None
    except ValidationError as exc:
        typer.secho(f"Invalid bot config:\n{exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from None


@app.command()
def check_config(config: Path | None = None) -> None:
    settings = RuntimeSettings()
    cfg = _load_config_or_exit(config or settings.config)
    typer.echo(cfg.model_dump_json(indent=2))


@app.command()
def run(config: Path | None = None) -> None:
    settings = RuntimeSettings()
    cfg = _load_config_or_exit(config or settings.config)
    try:
        asyncio.run(_run_one_cycle(cfg, settings.db_path, settings.audit_log_path))
    except CliConfigError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from None
    typer.echo("Completed one bot cycle.")


async def _run_one_cycle(
    cfg: BotConfig,
    store_path: str | Path,
    audit_log_path: str | Path | None = None,
) -> None:
    execution = build_execution_engine(cfg)
    try:
        latest_feed = await fetch_btc_feed_aggregate(cfg.risk.max_feed_age_ms)
    except Exception as exc:
        raise CliConfigError(f"Could not fetch BTC feed aggregate: {exc}") from None

    runner = BotRunner(
        cfg,
        execution=execution,
        store_path=store_path,
        latest_feed=latest_feed,
        audit_log_path=audit_log_path,
    )
    try:
        await runner.run_once()
    finally:
        await runner.aclose()


def build_execution_engine(cfg: BotConfig) -> PaperExecutionEngine | LiveExecutionEngine:
    if cfg.bot.mode == "paper":
        return PaperExecutionEngine()

    load_dotenv(Path.cwd() / ".env")
    missing = [name for name in LIVE_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise CliConfigError(
            "Missing live Polymarket environment variables: " + ", ".join(missing)
        )

    try:
        from py_clob_client_v2 import ClobClient
        from py_clob_client_v2.clob_types import ApiCreds
    except ImportError:
        raise CliConfigError(
            "Live mode requires optional dependency py-clob-client-v2. "
            "Install the trading extra before running live mode."
        ) from None

    creds = ApiCreds(
        api_key=os.environ["POLYMARKET_API_KEY"],
        api_secret=os.environ["POLYMARKET_API_SECRET"],
        api_passphrase=os.environ["POLYMARKET_API_PASSPHRASE"],
    )
    clob_client = ClobClient(
        host="https://clob.polymarket.com",
        key=os.environ["POLYMARKET_PRIVATE_KEY"],
        chain_id=137,
        creds=creds,
        signature_type=3,
        funder=os.environ["POLYMARKET_FUNDER_ADDRESS"],
    )
    return LiveExecutionEngine(clob_client)


@app.command()
def dashboard(config: Path | None = None) -> None:
    settings = RuntimeSettings()
    cfg = _load_config_or_exit(config or settings.config)
    store = StateStore(settings.db_path)
    store.initialize()
    control = BotControlService(store, cfg, settings.db_path, settings.audit_log_path, _run_one_cycle)
    uvicorn.run(
        create_dashboard_app(store, cfg, control),
        host=cfg.bot.dashboard_host,
        port=cfg.bot.dashboard_port,
    )
