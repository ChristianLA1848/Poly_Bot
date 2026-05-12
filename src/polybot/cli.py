from pathlib import Path
import tomllib

from pydantic import ValidationError
import typer

from polybot.config import BotConfig
from polybot.config import RuntimeSettings, load_bot_config

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
def run() -> None:
    typer.echo("Bot runner will be enabled after core tasks are implemented.")


@app.command()
def dashboard() -> None:
    typer.echo("Dashboard runner will be enabled after dashboard tasks are implemented.")
