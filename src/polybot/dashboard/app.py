from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from polybot.state_store import StateStore

STATIC_DIR = Path(__file__).with_name("static")


def create_dashboard_app(store: StateStore) -> FastAPI:
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
        data.setdefault("bot_status", "ready")
        data.setdefault("today_pnl", 0.0)
        return data

    return dashboard
