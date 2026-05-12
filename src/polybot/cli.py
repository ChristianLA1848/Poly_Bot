import asyncio
from pathlib import Path
import tomllib

from pydantic import ValidationError
import typer

from polybot.bot import BotRunner
from polybot.config import BotConfig
from polybot.config import RuntimeSettings, load_bot_config
from polybot.execution.paper import PaperExecutionEngine

app = typer.Typer(help="Polymarket BTC event trading bot")


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
    asyncio.run(_run_one_cycle(cfg, settings.db_path))
    typer.echo("Completed one bot cycle.")


async def _run_one_cycle(cfg: BotConfig, store_path: str) -> None:
    runner = BotRunner(cfg, execution=PaperExecutionEngine(), store_path=store_path)
    try:
        await runner.run_once()
    finally:
        await runner.aclose()


@app.command()
def dashboard() -> None:
    typer.echo("Dashboard runner will be enabled after dashboard tasks are implemented.")
