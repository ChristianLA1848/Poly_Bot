from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from polybot.config import BotConfig
from polybot.state_store import StateStore
from polybot.strategies.base import list_strategy_metadata

STATIC_DIR = Path(__file__).with_name("static")


def create_dashboard_app(
    store: StateStore,
    default_config: BotConfig | None = None,
    control_service: Any | None = None,
) -> FastAPI:
    dashboard = FastAPI(title="Polybot Dashboard")
    dashboard.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @dashboard.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @dashboard.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @dashboard.get("/api/snapshot")
    def snapshot() -> dict[str, Any]:
        data = store.dashboard_snapshot()
        data["snapshot_time"] = datetime.now(tz=UTC).isoformat()
        data.setdefault("bot_status", "ready")
        data.setdefault("today_pnl", 0.0)
        data["strategy_metadata"] = [
            {
                "name": item.name,
                "label": item.label,
                "market_profiles": list(item.market_profiles),
                "description": item.description,
            }
            for item in list_strategy_metadata()
        ]
        data["paper_analytics"] = store.paper_analytics()
        if default_config is not None:
            data.setdefault("settings", store.get_settings(default_config))
        return data

    @dashboard.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        if default_config is None:
            return {}
        return store.get_settings(default_config)

    @dashboard.put("/api/settings")
    def put_settings(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            config = BotConfig.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=json.loads(exc.json())) from exc
        store.record_settings(config)
        return config.model_dump(mode="json")

    @dashboard.post("/api/bot/start")
    async def start_bot() -> dict[str, Any]:
        if control_service is None:
            raise HTTPException(status_code=503, detail="Bot control is unavailable.")
        return await control_service.start()

    @dashboard.post("/api/bot/stop")
    async def stop_bot() -> dict[str, Any]:
        if control_service is None:
            raise HTTPException(status_code=503, detail="Bot control is unavailable.")
        return await control_service.stop()

    return dashboard
