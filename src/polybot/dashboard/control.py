import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from polybot.config import BotConfig
from polybot.state_store import StateStore

RunOnce = Callable[[BotConfig, str | Path, str | Path | None], Awaitable[None]]


class BotControlService:
    def __init__(
        self,
        store: StateStore,
        default_config: BotConfig,
        store_path: str | Path,
        audit_log_path: str | Path | None,
        run_once: RunOnce,
    ) -> None:
        self.store = store
        self.default_config = default_config
        self.store_path = store_path
        self.audit_log_path = audit_log_path
        self.run_once = run_once
        self._task: asyncio.Task[None] | None = None
        self._stop_requested = asyncio.Event()

    def status(self) -> dict[str, Any]:
        return self.store.dashboard_snapshot()["runtime_status"]

    async def start(self) -> dict[str, Any]:
        if self._task is not None and not self._task.done():
            return self.status()

        self._stop_requested.clear()
        self.store.record_runtime_status("starting", "Bot loop starting.", datetime.now(tz=UTC))
        self._task = asyncio.create_task(self._run_loop())
        await asyncio.sleep(0)
        return self.status()

    async def stop(self) -> dict[str, Any]:
        if self._task is None or self._task.done():
            self.store.record_runtime_status("stopped", "Bot is stopped.", datetime.now(tz=UTC))
            return self.status()

        self.store.record_runtime_status(
            "stopping",
            "Stopping after current cycle.",
            datetime.now(tz=UTC),
        )
        self._stop_requested.set()
        await self._task
        return self.status()

    async def _run_loop(self) -> None:
        self.store.record_runtime_status("running", "Bot loop running.", datetime.now(tz=UTC))
        while not self._stop_requested.is_set():
            config = self.default_config
            try:
                config = BotConfig.model_validate(self.store.get_settings(self.default_config))
                await self.run_once(config, self.store_path, self.audit_log_path)
                self.store.record_runtime_status(
                    "running",
                    "Bot loop running.",
                    datetime.now(tz=UTC),
                )
            except Exception as exc:
                self.store.record_runtime_status(
                    "error",
                    "Bot loop error.",
                    datetime.now(tz=UTC),
                    str(exc),
                )

            if not self._stop_requested.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_requested.wait(),
                        timeout=config.bot.cycle_seconds,
                    )
                except TimeoutError:
                    pass

        self.store.record_runtime_status("stopped", "Bot is stopped.", datetime.now(tz=UTC))
