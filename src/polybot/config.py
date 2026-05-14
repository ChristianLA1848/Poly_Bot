from pathlib import Path
import tomllib
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POLYBOT_", env_file=".env", extra="ignore")

    config: str = "configs/bot.example.toml"
    db_path: str = "./data/polybot.sqlite3"
    audit_log_path: str = "./data/audit.jsonl"


class BotSection(BaseModel):
    mode: Literal["paper", "live"] = "paper"
    cycle_seconds: float = Field(default=1.0, gt=0.0)
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = Field(default=8787, ge=1, le=65535)


class RiskSection(BaseModel):
    max_stake: float = Field(gt=0.0)
    max_daily_loss: float = Field(gt=0.0)
    max_spread: float = Field(ge=0.0)
    min_liquidity: float = Field(gt=0.0)
    min_edge: float = Field(ge=0.0)
    max_feed_age_ms: int = Field(gt=0)
    max_feed_deviation_bps: int = Field(ge=0)
    max_open_positions: int = Field(default=1, ge=0)
    max_open_orders: int = Field(default=2, ge=0)
    max_trades_per_event: int = Field(default=1, ge=0)
    max_event_exposure: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def default_event_exposure(self) -> "RiskSection":
        if self.max_event_exposure is None:
            self.max_event_exposure = self.max_stake
        return self


class StrategySection(BaseModel):
    name: Literal[
        "baseline_momentum",
        "late_window",
        "late_window_5m",
        "trend_following",
    ] = "baseline_momentum"


class StakingSection(BaseModel):
    mode: Literal["fixed", "fractional_kelly", "confidence_tiering"] = "fixed"
    fixed_stake: float = Field(default=5.0, ge=0.0)
    kelly_fraction: float = Field(default=0.25, ge=0.0, le=1.0)
    low_confidence_stake: float = Field(default=2.0, ge=0.0)
    medium_confidence_stake: float = Field(default=5.0, ge=0.0)
    high_confidence_stake: float = Field(default=10.0, ge=0.0)


class ExitSection(BaseModel):
    mode: Literal["hold_to_resolution", "managed_exit"] = "hold_to_resolution"
    profit_target: float = Field(default=0.08, ge=0.0)
    stop_loss: float = Field(default=0.05, ge=0.0)


class LateWindowSection(BaseModel):
    min_seconds_remaining: int = Field(default=20, ge=0)
    max_seconds_remaining: int = Field(default=60, ge=0)
    min_delta_pct: float = Field(default=0.10, ge=0.0)
    min_expected_return: float = Field(default=0.01, ge=0.0)
    max_expected_return: float = Field(default=0.10, ge=0.0)
    min_confidence: float = Field(default=0.80, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_ranges(self) -> "LateWindowSection":
        if self.max_seconds_remaining < self.min_seconds_remaining:
            raise ValueError("max_seconds_remaining must be >= min_seconds_remaining")
        if self.max_expected_return < self.min_expected_return:
            raise ValueError("max_expected_return must be >= min_expected_return")
        return self


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
