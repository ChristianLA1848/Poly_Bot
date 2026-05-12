from pathlib import Path
import tomllib

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POLYBOT_", env_file=".env", extra="ignore")

    config: str = "configs/bot.example.toml"
    db_path: str = "./data/polybot.sqlite3"
    audit_log_path: str = "./data/audit.jsonl"


class BotSection(BaseModel):
    mode: str = "paper"
    cycle_seconds: float = 1.0
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8787


class RiskSection(BaseModel):
    max_stake: float
    max_daily_loss: float
    max_spread: float
    min_liquidity: float
    min_edge: float
    max_feed_age_ms: int
    max_feed_deviation_bps: int
    max_open_positions: int = 1
    max_open_orders: int = 2


class StrategySection(BaseModel):
    name: str = "baseline_momentum"


class StakingSection(BaseModel):
    mode: str = "fixed"
    fixed_stake: float = 5.0
    kelly_fraction: float = Field(default=0.25, ge=0.0, le=1.0)
    low_confidence_stake: float = 2.0
    medium_confidence_stake: float = 5.0
    high_confidence_stake: float = 10.0


class ExitSection(BaseModel):
    mode: str = "hold_to_resolution"
    profit_target: float = 0.08
    stop_loss: float = 0.05


class LateWindowSection(BaseModel):
    min_seconds_remaining: int = 20
    max_seconds_remaining: int = 60
    min_expected_return: float = 0.01
    max_expected_return: float = 0.10
    min_confidence: float = 0.80


class BotConfig(BaseModel):
    bot: BotSection
    risk: RiskSection
    strategy: StrategySection
    staking: StakingSection
    exit: ExitSection
    late_window: LateWindowSection = Field(default_factory=LateWindowSection)


def load_bot_config(path: str | Path) -> BotConfig:
    config_path = Path(path)
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return BotConfig.model_validate(data)
