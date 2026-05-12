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
