from pathlib import Path

from polybot.config import BotConfig, load_bot_config


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
