import builtins
import sys
import types
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from polybot import cli
from polybot.config import (
    BotConfig,
    BotSection,
    ExitSection,
    LateWindowSection,
    RiskSection,
    StakingSection,
    StrategySection,
)
from polybot.execution.live import LiveExecutionEngine
from polybot.execution.paper import PaperExecutionEngine
from polybot.models import FeedAggregate, FeedPrice

runner = CliRunner()


def _config(mode: str = "paper") -> BotConfig:
    return BotConfig(
        bot=BotSection(mode=mode, cycle_seconds=1),
        risk=RiskSection(
            max_stake=10,
            max_daily_loss=25,
            max_spread=0.04,
            min_liquidity=100,
            min_edge=0.03,
            max_feed_age_ms=2500,
            max_feed_deviation_bps=20,
        ),
        strategy=StrategySection(name="baseline_momentum"),
        staking=StakingSection(mode="fixed", fixed_stake=5),
        exit=ExitSection(mode="hold_to_resolution"),
        late_window=LateWindowSection(),
    )


def _feed() -> FeedAggregate:
    return FeedAggregate(
        reference_price=101.0,
        prices=[FeedPrice("coinbase", "BTC-USD", 101.0, 1_778_520_000_000)],
        max_deviation_bps=0.0,
        fresh=True,
        created_at=datetime(2026, 5, 12, 21, 0, tzinfo=UTC),
    )


def _write_config(path, mode: str) -> None:
    path.write_text(
        f"""
[bot]
mode = "{mode}"
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

[exit]
mode = "hold_to_resolution"
""",
        encoding="utf-8",
    )


def test_run_live_missing_env_exits_without_traceback(monkeypatch, tmp_path):
    cfg_path = tmp_path / "bot.toml"
    _write_config(cfg_path, "live")
    monkeypatch.chdir(tmp_path)
    for name in cli.LIVE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    result = runner.invoke(cli.app, ["run", "--config", str(cfg_path)])

    assert result.exit_code == 1
    assert "Missing live Polymarket environment variables" in result.output
    assert "Traceback" not in result.output


def test_build_execution_engine_returns_paper_engine_for_paper_mode():
    engine = cli.build_execution_engine(_config("paper"))

    assert isinstance(engine, PaperExecutionEngine)


def test_build_execution_engine_live_missing_env_fails_cleanly(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in cli.LIVE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(cli.CliConfigError, match="Missing live Polymarket environment variables"):
        cli.build_execution_engine(_config("live"))


def test_build_execution_engine_live_loads_polymarket_env_file(monkeypatch, tmp_path):
    created: dict[str, object] = {}

    class FakeApiCreds:
        def __init__(self, api_key: str, api_secret: str, api_passphrase: str) -> None:
            self.api_key = api_key
            self.api_secret = api_secret
            self.api_passphrase = api_passphrase

    class FakeClobClient:
        def __init__(self, **kwargs: object) -> None:
            created.update(kwargs)

    fake_module = types.ModuleType("py_clob_client_v2")
    fake_module.ClobClient = FakeClobClient
    fake_clob_types = types.ModuleType("py_clob_client_v2.clob_types")
    fake_clob_types.ApiCreds = FakeApiCreds
    monkeypatch.setitem(sys.modules, "py_clob_client_v2", fake_module)
    monkeypatch.setitem(sys.modules, "py_clob_client_v2.clob_types", fake_clob_types)
    monkeypatch.chdir(tmp_path)
    for name in cli.LIVE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(
            (
                "POLYMARKET_PRIVATE_KEY=private-key-from-env-file",
                "POLYMARKET_API_KEY=api-key-from-env-file",
                "POLYMARKET_API_SECRET=api-secret-from-env-file",
                "POLYMARKET_API_PASSPHRASE=api-passphrase-from-env-file",
                "POLYMARKET_FUNDER_ADDRESS=0xfunder-from-env-file",
            )
        ),
        encoding="utf-8",
    )

    engine = cli.build_execution_engine(_config("live"))

    assert isinstance(engine, LiveExecutionEngine)
    assert created["key"] == "private-key-from-env-file"
    assert created["funder"] == "0xfunder-from-env-file"
    assert created["creds"].api_key == "api-key-from-env-file"
    assert created["creds"].api_secret == "api-secret-from-env-file"
    assert created["creds"].api_passphrase == "api-passphrase-from-env-file"


def test_build_execution_engine_live_missing_optional_dependency_fails_cleanly(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("py_clob_client_v2"):
            raise ImportError("missing py-clob-client-v2")
        return real_import(name, *args, **kwargs)

    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "private-key")
    monkeypatch.setenv("POLYMARKET_API_KEY", "api-key")
    monkeypatch.setenv("POLYMARKET_API_SECRET", "api-secret")
    monkeypatch.setenv("POLYMARKET_API_PASSPHRASE", "api-passphrase")
    monkeypatch.setenv("POLYMARKET_FUNDER_ADDRESS", "0xfunder")
    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(cli.CliConfigError, match="optional dependency py-clob-client-v2"):
        cli.build_execution_engine(_config("live"))


def test_build_execution_engine_live_builds_clob_client_from_env(monkeypatch):
    created: dict[str, object] = {}

    class FakeApiCreds:
        def __init__(self, api_key: str, api_secret: str, api_passphrase: str) -> None:
            self.api_key = api_key
            self.api_secret = api_secret
            self.api_passphrase = api_passphrase

    class FakeClobClient:
        def __init__(self, **kwargs: object) -> None:
            created.update(kwargs)

    fake_module = types.ModuleType("py_clob_client_v2")
    fake_module.ClobClient = FakeClobClient
    fake_clob_types = types.ModuleType("py_clob_client_v2.clob_types")
    fake_clob_types.ApiCreds = FakeApiCreds
    monkeypatch.setitem(sys.modules, "py_clob_client_v2", fake_module)
    monkeypatch.setitem(sys.modules, "py_clob_client_v2.clob_types", fake_clob_types)
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "private-key")
    monkeypatch.setenv("POLYMARKET_API_KEY", "api-key")
    monkeypatch.setenv("POLYMARKET_API_SECRET", "api-secret")
    monkeypatch.setenv("POLYMARKET_API_PASSPHRASE", "api-passphrase")
    monkeypatch.setenv("POLYMARKET_FUNDER_ADDRESS", "0xfunder")

    engine = cli.build_execution_engine(_config("live"))

    assert isinstance(engine, LiveExecutionEngine)
    assert created["host"] == "https://clob.polymarket.com"
    assert created["key"] == "private-key"
    assert created["chain_id"] == 137
    assert created["signature_type"] == 3
    assert created["funder"] == "0xfunder"
    assert created["creds"].api_key == "api-key"
    assert created["creds"].api_secret == "api-secret"
    assert created["creds"].api_passphrase == "api-passphrase"


@pytest.mark.asyncio
async def test_run_one_cycle_fetches_latest_feed_and_passes_audit_log_path(monkeypatch, tmp_path):
    seen: dict[str, object] = {}
    feed = _feed()

    async def fake_fetch(max_age_ms: int) -> FeedAggregate:
        seen["max_age_ms"] = max_age_ms
        return feed

    class FakeRunner:
        def __init__(self, config, **kwargs):
            seen["config"] = config
            seen.update(kwargs)

        async def run_once(self):
            seen["ran"] = True

        async def aclose(self):
            seen["closed"] = True

    monkeypatch.setattr(cli, "fetch_btc_feed_aggregate", fake_fetch)
    monkeypatch.setattr(cli, "build_execution_engine", lambda cfg: "paper-engine")
    monkeypatch.setattr(cli, "BotRunner", FakeRunner)

    await cli._run_one_cycle(_config("paper"), tmp_path / "bot.sqlite3", tmp_path / "audit.jsonl")

    assert seen["max_age_ms"] == 2500
    assert seen["execution"] == "paper-engine"
    assert seen["latest_feed"] is feed
    assert seen["store_path"] == tmp_path / "bot.sqlite3"
    assert seen["audit_log_path"] == tmp_path / "audit.jsonl"
    assert seen["ran"] is True
    assert seen["closed"] is True
