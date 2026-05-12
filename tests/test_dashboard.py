from fastapi.testclient import TestClient

from polybot.dashboard.app import create_dashboard_app
from polybot.state_store import StateStore


def test_dashboard_health_and_snapshot(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    app = create_dashboard_app(store)
    client = TestClient(app)

    health = client.get("/api/health")
    snapshot = client.get("/api/snapshot")

    assert health.json() == {"status": "ok"}
    assert snapshot.status_code == 200
    assert "recent_decisions" in snapshot.json()


def test_dashboard_root_serves_html(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    app = create_dashboard_app(store)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Polybot Dashboard" in response.text


def test_dashboard_snapshot_includes_defaults(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    app = create_dashboard_app(store)
    client = TestClient(app)

    response = client.get("/api/snapshot")

    assert response.status_code == 200
    assert response.json()["bot_status"] == "ready"
    assert response.json()["today_pnl"] == 0.0
