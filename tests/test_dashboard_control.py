import asyncio
from datetime import UTC, datetime

import pytest

from polybot.config import (
    BotConfig,
    BotSection,
    ExitSection,
    LateWindowSection,
    RiskSection,
    StakingSection,
    StrategySection,
)
from polybot.dashboard.control import BotControlService
from polybot.models import FeedAggregate, FeedPrice
from polybot.state_store import StateStore


def config_for_control(cycle_seconds: float = 0.01) -> BotConfig:
    return BotConfig(
        bot=BotSection(mode="paper", cycle_seconds=cycle_seconds),
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


@pytest.mark.asyncio
async def test_control_service_start_and_stop_records_runtime_status(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    config = config_for_control()
    cycles = {"count": 0}
    cycle_started = asyncio.Event()

    async def fake_run_once(cfg, store_path, audit_log_path):
        assert cfg == config
        assert store_path == tmp_path / "bot.sqlite3"
        assert audit_log_path == tmp_path / "audit.jsonl"
        cycles["count"] += 1
        store.record_feed_status(
            FeedAggregate(
                101.0,
                [FeedPrice("test", "BTC-USD", 101.0, 1)],
                0,
                True,
                datetime(2026, 5, 13, tzinfo=UTC),
            ),
            target_price=100.0,
        )
        cycle_started.set()
        await asyncio.sleep(0)

    service = BotControlService(
        store=store,
        default_config=config,
        store_path=tmp_path / "bot.sqlite3",
        audit_log_path=tmp_path / "audit.jsonl",
        run_once=fake_run_once,
    )

    start_status = await service.start()
    await asyncio.wait_for(cycle_started.wait(), timeout=1)
    stop_status = await service.stop()

    assert start_status["state"] in {"starting", "running"}
    assert cycles["count"] >= 1
    assert stop_status["state"] == "stopped"
    assert store.dashboard_snapshot()["runtime_status"]["state"] == "stopped"


@pytest.mark.asyncio
async def test_control_service_start_is_idempotent_while_running(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    run_started = asyncio.Event()
    release_run = asyncio.Event()
    cycles = {"count": 0}

    async def fake_run_once(cfg, store_path, audit_log_path):
        cycles["count"] += 1
        run_started.set()
        await release_run.wait()

    service = BotControlService(
        store,
        config_for_control(),
        tmp_path / "bot.sqlite3",
        tmp_path / "audit.jsonl",
        fake_run_once,
    )

    first = await service.start()
    await asyncio.wait_for(run_started.wait(), timeout=1)
    second = await service.start()
    release_run.set()
    await service.stop()

    assert first["state"] in {"starting", "running"}
    assert second["state"] == "running"
    assert cycles["count"] == 1


@pytest.mark.asyncio
async def test_control_service_run_once_exception_records_error_and_stop_still_works(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    failed_once = asyncio.Event()
    cycles = {"count": 0}

    async def fake_run_once(cfg, store_path, audit_log_path):
        cycles["count"] += 1
        if cycles["count"] == 1:
            failed_once.set()
            raise RuntimeError("boom")
        await asyncio.sleep(0)

    service = BotControlService(
        store=store,
        default_config=config_for_control(),
        store_path=tmp_path / "bot.sqlite3",
        audit_log_path=tmp_path / "audit.jsonl",
        run_once=fake_run_once,
    )

    await service.start()
    await asyncio.wait_for(failed_once.wait(), timeout=1)
    error_status = store.dashboard_snapshot()["runtime_status"]
    stop_status = await service.stop()

    assert error_status["state"] == "error"
    assert error_status["last_error"] == "boom"
    assert stop_status["state"] == "stopped"
    assert cycles["count"] >= 1
