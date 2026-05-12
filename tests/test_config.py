from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from polybot.cli import app
from polybot.config import BotConfig, load_bot_config


runner = CliRunner()


def test_load_bot_config_from_toml(tmp_path: Path):
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(
        """
[bot]
mode = "paper"
cycle_seconds = 1.0

[risk]
max_stake = 10.0
max_daily_loss = 25.0
max_spread = 0.04
min_liquidity = 100.0
min_edge = 0.03
max_feed_age_ms = 2500
max_feed_deviation_bps = 20

[strategy]
name = "baseline_momentum"

[staking]
mode = "fixed"
fixed_stake = 5.0
kelly_fraction = 0.25

[exit]
mode = "hold_to_resolution"
""",
        encoding="utf-8",
    )

    cfg = load_bot_config(cfg_path)

    assert isinstance(cfg, BotConfig)
    assert cfg.bot.mode == "paper"
    assert cfg.risk.max_stake == 10.0
    assert cfg.strategy.name == "baseline_momentum"
    assert cfg.staking.fixed_stake == 5.0


def test_load_bot_config_rejects_invalid_risk_values(tmp_path: Path):
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(
        """
[bot]
mode = "paper"
cycle_seconds = 1.0

[risk]
max_stake = 0.0
max_daily_loss = 25.0
max_spread = -0.01
min_liquidity = 100.0
min_edge = 0.03
max_feed_age_ms = 2500
max_feed_deviation_bps = 20

[strategy]
name = "baseline_momentum"

[staking]
mode = "fixed"
fixed_stake = 5.0
kelly_fraction = 0.25

[exit]
mode = "hold_to_resolution"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        load_bot_config(cfg_path)

    errors = exc_info.value.errors()
    assert any(error["loc"] == ("risk", "max_stake") for error in errors)
    assert any(error["loc"] == ("risk", "max_spread") for error in errors)


def test_check_config_missing_file_exits_cleanly():
    result = runner.invoke(app, ["check-config", "--config", "/tmp/does-not-exist.toml"])

    assert result.exit_code == 1
    assert "Config file not found" in result.output
    assert "Traceback" not in result.output


def test_check_config_directory_path_exits_cleanly(tmp_path: Path):
    result = runner.invoke(app, ["check-config", "--config", str(tmp_path)])

    assert result.exit_code == 1
    assert "Could not read config file" in result.output
    assert "Traceback" not in result.output
