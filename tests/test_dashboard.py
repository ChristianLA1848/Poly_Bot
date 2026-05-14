from fastapi.testclient import TestClient

from polybot.config import (
    BotConfig,
    BotSection,
    ExitSection,
    LateWindowSection,
    RiskSection,
    StakingSection,
    StrategySection,
)
from polybot.dashboard.app import create_dashboard_app
from polybot.state_store import StateStore


def dashboard_config_for_test() -> BotConfig:
    return BotConfig(
        bot=BotSection(),
        risk=RiskSection(
            max_stake=10.0,
            max_daily_loss=25.0,
            max_spread=0.05,
            min_liquidity=100.0,
            min_edge=0.01,
            max_feed_age_ms=5000,
            max_feed_deviation_bps=50,
        ),
        strategy=StrategySection(),
        staking=StakingSection(),
        exit=ExitSection(),
        late_window=LateWindowSection(),
    )


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
    assert "Market Status" in response.text


def test_dashboard_snapshot_includes_defaults(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    app = create_dashboard_app(store)
    client = TestClient(app)

    response = client.get("/api/snapshot")

    assert response.status_code == 200
    assert response.json()["bot_status"] == "ready"
    assert response.json()["today_pnl"] == 0.0
    assert response.json()["market_status"]["state"] == "unknown"


def test_dashboard_settings_get_and_put(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    cfg = dashboard_config_for_test()
    app = create_dashboard_app(store, default_config=cfg, control_service=None)
    client = TestClient(app)

    settings = client.get("/api/settings").json()
    settings["bot"]["mode"] = "live"
    response = client.put("/api/settings", json=settings)

    assert response.status_code == 200
    assert response.json()["bot"]["mode"] == "live"


def test_dashboard_settings_reject_invalid_payload(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    cfg = dashboard_config_for_test()
    app = create_dashboard_app(store, default_config=cfg, control_service=None)
    client = TestClient(app)

    response = client.put("/api/settings", json={"bot": {"mode": "invalid"}})

    assert response.status_code == 422


def test_dashboard_settings_reject_invalid_late_window_with_json_response(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    cfg = dashboard_config_for_test()
    app = create_dashboard_app(store, default_config=cfg, control_service=None)
    client = TestClient(app)
    settings = cfg.model_dump(mode="json")
    settings["late_window"]["min_seconds_remaining"] = 60
    settings["late_window"]["max_seconds_remaining"] = 20

    response = client.put("/api/settings", json=settings)

    assert response.status_code == 422
    assert response.json()["detail"]


def test_dashboard_start_stop_routes_call_control_service(tmp_path):
    class FakeControl:
        async def start(self):
            return {"state": "running", "message": "Bot loop running."}

        async def stop(self):
            return {"state": "stopped", "message": "Bot is stopped."}

    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    app = create_dashboard_app(store, dashboard_config_for_test(), FakeControl())
    client = TestClient(app)

    assert client.post("/api/bot/start").json()["state"] == "running"
    assert client.post("/api/bot/stop").json()["state"] == "stopped"


def test_dashboard_snapshot_includes_settings_when_default_config_supplied(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    cfg = dashboard_config_for_test()
    app = create_dashboard_app(store, default_config=cfg)
    client = TestClient(app)

    response = client.get("/api/snapshot")

    assert response.status_code == 200
    assert response.json()["settings"] == cfg.model_dump(mode="json")


def test_dashboard_snapshot_includes_strategy_metadata(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    app = create_dashboard_app(store, dashboard_config_for_test(), control_service=None)
    client = TestClient(app)

    response = client.get("/api/snapshot")

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["strategy_metadata"]]
    assert names == ["baseline_momentum", "late_window_5m", "trend_following"]


def test_dashboard_snapshot_includes_paper_analytics(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    app = create_dashboard_app(store, dashboard_config_for_test(), control_service=None)
    client = TestClient(app)

    response = client.get("/api/snapshot")

    assert response.status_code == 200
    assert response.json()["paper_analytics"]["total_trades"] == 0
    assert response.json()["paper_analytics"]["equity_curve"] == []


def test_dashboard_root_contains_tabs_controls_and_settings(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    app = create_dashboard_app(store, dashboard_config_for_test(), control_service=None)
    client = TestClient(app)

    html = client.get("/").text

    assert 'data-tab-target="monitor"' in html
    assert 'data-tab-target="settings"' in html
    assert 'data-tab-target="analytics"' in html
    assert 'data-tab-target="logs"' in html
    assert 'role="tablist"' in html
    assert 'role="tab"' in html
    assert 'role="tabpanel"' in html
    assert 'aria-selected="true"' in html
    assert 'aria-controls="monitor-panel"' in html
    assert 'id="start-bot"' in html
    assert 'id="stop-bot"' in html
    assert 'id="btc-price"' in html
    assert 'id="target-price"' in html
    assert 'id="strategy-reason-code"' in html
    assert 'id="strategy-edge"' in html
    assert 'id="strategy-confidence"' in html
    assert 'id="strategy-estimated-probability"' in html
    assert 'id="strategy-market-probability"' in html
    assert 'id="strategy-compatibility"' in html
    assert 'id="paper-total-pnl"' in html
    assert 'id="paper-win-rate"' in html
    assert 'id="paper-trade-counts"' in html
    assert 'id="paper-average-edge"' in html
    assert 'id="equity-curve"' in html
    assert 'id="paper-trades"' in html
    assert 'name="bot.mode"' in html
    assert 'name="bot.cycle_seconds" min="0.01"' in html
    assert 'name="strategy.name"' in html
    assert 'value="late_window_5m"' in html
    assert 'value="trend_following"' in html
    assert 'name="staking.mode"' in html
    assert 'name="risk.max_stake" min="0.01"' in html
    assert 'name="risk.max_feed_age_ms" min="1"' in html


def test_dashboard_root_contains_german_label_translations(tmp_path):
    store = StateStore(tmp_path / "bot.sqlite3")
    store.initialize()
    app = create_dashboard_app(store, dashboard_config_for_test(), control_service=None)
    client = TestClient(app)

    html = client.get("/").text

    assert 'class="label-translation">Überwachung</span>' in html
    assert 'class="label-translation">Heutiger Gewinn/Verlust</span>' in html
    assert 'class="label-translation">Zielkurs</span>' in html
    assert 'class="label-translation">Geschätzte Wahrscheinlichkeit</span>' in html
    assert 'class="label-translation">Bot-Steuerung</span>' in html
    assert 'class="label-translation">Marktstatus</span>' in html
    assert 'class="label-translation">Einstellungen speichern</span>' in html
    assert 'class="label-translation">Aktuelle Entscheidungen</span>' in html
    assert 'class="label-translation">Aktuelle Ereignisse</span>' in html
