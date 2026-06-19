"""Phase 12a — command center nav and shell stubs."""

import pytest
from fastapi.testclient import TestClient

from thread.main import create_app


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_ui_test():
    """Reset module-level asyncpg pool between UI tests (Windows TestClient loop clash)."""
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()

STUB_NAV_ROUTES = (
    ("/settings", "Settings"),
    ("/tools/mcp", "MCP Servers"),
    ("/tools/skills", "Agent Skills"),
)

DB_NAV_ROUTES = (
    ("/", "Command Center"),
    ("/capture", "Filament"),
    ("/review", "Review Queue"),
    ("/pulse", "Portfolio Pulse"),
)


def test_shell_stub_nav_routes_return_200():
    client = TestClient(create_app())
    for path, heading in STUB_NAV_ROUTES:
        res = client.get(path)
        assert res.status_code == 200, f"{path}: {res.text[:200]}"
        assert heading in res.text


@pytest.mark.parametrize("path,heading", DB_NAV_ROUTES)
def test_shell_db_nav_routes_return_200(path: str, heading: str):
    """One DB route per test invocation — avoids Windows asyncpg loop reuse."""
    client = TestClient(create_app())
    res = client.get(path)
    assert res.status_code == 200, f"{path}: {res.text[:200]}"
    assert heading in res.text


def test_insights_page_saved_lenses_not_stub():
    client = TestClient(create_app())
    res = client.get("/insights")
    assert res.status_code == 200
    assert "Data Insights" in res.text
    assert "Identify" in res.text
    assert "insights-frame" in res.text or "USAspending" in res.text
    assert "Shell stub" not in res.text

    res = client.get("/knowledge")
    assert "vault-browser-layout" in res.text
    assert "Shell stub" not in res.text


def test_theseus_sidebar_shell_not_topbar_app_nav():
    """Stub route avoids PG; verifies Theseus-style shell layout."""
    client = TestClient(create_app())
    res = client.get("/insights")
    html = res.text
    assert res.status_code == 200
    assert "topbar-vibrant" in html
    assert "sidebar-vibrant" in html
    assert "nav-item-active" in html
    assert "panel-canvas" in html
    assert "glass-section-bar" in html
    assert "h1-gradient" in html
    assert 'href="/settings"' in html
    assert "Settings" in html
    assert "nav-group-cyan" in html
    assert "nav-group-magenta" in html
    assert "System" in html
    assert "Command" in html
    assert "Tools" in html
    assert 'href="/tools/mcp"' in html
    assert 'href="/tools/skills"' in html
    assert 'href="/pulse"' in html
    assert 'href="/capture"' in html
    assert "data-lucide" in html
    assert 'data-lucide="layout-dashboard"' in html
    assert "Portfolio Pulse" in html
    # Global routes live in sidebar, not duplicated as topbar nav pills
    assert html.index("sidebar-vibrant") < html.index("glass-section-bar")
    assert 'href="/insights"' in html
    assert html.count('class="topbar-pill"') >= 1
    assert "page-content" in html


def test_settings_page_read_only_health():
    """Phase 12b — settings accordion wired to health context."""
    client = TestClient(create_app())
    res = client.get("/settings")
    html = res.text
    assert res.status_code == 200
    assert "Platform health" in html or "vault controls" in html
    assert 'class="acc ' in html
    assert "Intel migration" in html
    assert "Document parsing (MinerU)" in html
    assert "MinerU 3.3" in html
    assert "Operator workflow" in html
    assert "capture FAB" in html
    assert "404" in html
    assert "Research providers" in html
    assert "Grok" in html or "xAI" in html
    assert "default_naics" in html
    assert "Knowledge vault" in html
    assert "THREAD_VAULT_SANDBOX" in html
    assert "thread-restart-btn" in html


def test_shell_sidebar_fixed_viewport_layout():
    """App shell pins below topbar — sidebar scrolls independently of page canvas."""
    client = TestClient(create_app())
    res = client.get("/")
    html = res.text
    assert res.status_code == 200
    css = open("src/thread/ui/static/styles/thread.css", encoding="utf-8").read()
    assert "position: fixed" in css
    assert ".app-shell" in css
    assert "sidebar-edge-toggle" in css
    assert 'class="sidebar-edge-toggle"' in html
    assert "overscroll-contain" in html


def test_sidebar_restart_button():
    client = TestClient(create_app())
    res = client.get("/")
    html = res.text
    assert res.status_code == 200
    assert "thread-restart-btn" in html
    assert "Restart server" in html
    assert "thread_restart.js" in html
    assert "thread_sidebar.js" in html
    assert 'id="app-sidebar"' in html
    assert 'id="sidebar-collapse-toggle"' in html
    assert "thread-restart-overlay" in html


def test_system_restart_endpoint(monkeypatch):
    scheduled: list[float] = []
    monkeypatch.setattr(
        "thread.ui.routes.schedule_restart",
        lambda delay: scheduled.append(delay),
    )
    client = TestClient(create_app())
    res = client.post("/system/restart")
    assert res.status_code == 200
    assert res.json()["status"] == "restarting"
    assert scheduled == [0.75]


def test_settings_vault_sandbox_toggle(monkeypatch):
    saved: list[tuple[str, str]] = []

    def _fake_upsert(_path, key: str, value: str) -> None:
        saved.append((key, value))

    monkeypatch.setattr("thread.ui.routes.upsert_env_var", _fake_upsert)
    monkeypatch.setattr("thread.ui.routes.apply_env_to_process", lambda _k, _v: None)
    monkeypatch.setattr("thread.ui.routes.reload_settings", lambda: __import__("thread.config", fromlist=["get_settings"]).get_settings())

    client = TestClient(create_app())
    res = client.post("/settings/vault-sandbox", data={"enabled": "true"})
    assert res.status_code == 200
    assert ("THREAD_VAULT_SANDBOX", "true") in saved
    assert "settings-vault-panel" in res.text

    res = client.post("/settings/vault-sandbox", data={})
    assert res.status_code == 200
    assert ("THREAD_VAULT_SANDBOX", "false") in saved


def test_tools_mcp_page_has_guides():
    client = TestClient(create_app())
    res = client.get("/tools/mcp")
    html = res.text
    assert res.status_code == 200
    assert "guide-modal" in html
    assert "settings-tip-box" in html
    assert "usaspending" in html
    assert "openGuideDialog" in html
    assert "Got it" in html


def test_tools_skills_page_lists_skills():
    client = TestClient(create_app())
    res = client.get("/tools/skills")
    html = res.text
    assert res.status_code == 200
    assert "clew_intel" in html or "skill-creator" in html
    assert '/partials/tools/skills/' in html
    assert "Phase 20" not in html


def test_review_page_global_queue_not_stub():
    """Phase 12c — global review queue with human titles."""
    client = TestClient(create_app())
    res = client.get("/review")
    html = res.text
    assert res.status_code == 200
    assert "Review Queue" in html
    assert "global-review-queue" in html
    assert "Shell stub" not in html
    assert "Phase 12c" not in html
    assert "Review gate clear" in html or "pending" in html


def test_dashboard_pending_reviews_widget():
    """Phase 12c — GovDash gate-reviews attention widget on Command Center."""
    client = TestClient(create_app())
    res = client.get("/")
    html = res.text
    assert res.status_code == 200
    assert "cc-widget-pending-reviews" in html
    assert "Gate reviews need attention" in html or "Review gate clear" in html
    assert 'href="/review"' in html


def test_dashboard_platform_health_widget():
    """Phase 12e — blocking health strip, not award analytics."""
    client = TestClient(create_app())
    res = client.get("/")
    html = res.text
    assert res.status_code == 200
    assert "cc-widget-platform-health" in html
    assert "Platform health" in html
    assert 'href="/settings"' in html
    assert "cc-health-pill" in html
    assert "cc-stat-tile" not in html


def test_sidebar_command_center_label_not_dashboard():
    client = TestClient(create_app())
    res = client.get("/")
    html = res.text
    assert res.status_code == 200
    assert "Command Center" in html
    assert ">Dashboard</span>" not in html


def test_dashboard_vault_stale_widget():
    """Phase 12m — stale vault ingest attention widget on Command Center."""
    client = TestClient(create_app())
    res = client.get("/")
    html = res.text
    assert res.status_code == 200
    assert "cc-widget-vault-stale" in html
    assert "/knowledge#knowledge-vault-inbox" in html or "Vault Inbox" in html
    assert "cc-widget-grid-4" in html


def test_dashboard_hot_signals_widget():
    """Phase 12f — hot recompete widget on Command Center."""
    client = TestClient(create_app())
    res = client.get("/")
    html = res.text
    assert res.status_code == 200
    assert "cc-widget-hot-signals" in html
    assert "Hot potential" in html
    assert "/pulse#potential-watchlist" in html
    assert "cc-widget-grid-4" in html


def test_dashboard_quick_actions_strip():
    """Phase 12h — compact action chips, not full-width buttons."""
    client = TestClient(create_app())
    res = client.get("/")
    html = res.text
    assert res.status_code == 200
    assert "cc-quick-actions" in html
    assert "Watchlist" in html
    assert "/pulse#potential-watchlist" in html
    assert 'href="/insights"' in html
    assert 'href="/knowledge"' in html


def test_dashboard_compact_layout_and_phase_band_widget():
    """Phase 12d — widget grid + phase-band breakdown, not lazy full-width cards."""
    client = TestClient(create_app())
    res = client.get("/")
    html = res.text
    assert res.status_code == 200
    assert "cc-widget-grid" in html
    assert "cc-widget-grid-4" in html
    assert "cc-widget-phase-band" in html
    assert "cc-widget-platform-health" in html
    assert "cc-lane-grid" in html
    assert "lane-tile" in html
    assert "pursuit-card" in html or "No active pursuits" in html.lower() or "track a signal" in html


def test_pulse_compact_split_layout():
    client = TestClient(create_app())
    res = client.get("/pulse")
    html = res.text
    assert res.status_code == 200
    assert "pulse-split" in html
    assert "pulse-rail" in html
    assert "pursuit-grid" in html or "pursuit-card" in html
    assert "cc-stat-tile" not in html


def test_pulse_intel_inbox_region():
    """Phase 12g — morning briefing inbox between radar and pursuits."""
    client = TestClient(create_app())
    res = client.get("/pulse")
    html = res.text
    assert res.status_code == 200
    assert "pulse-doctrine" in html
    assert "Filament" in html
    assert "Potential" in html
    assert "Tracked" in html
    assert 'id="intel-inbox"' in html
    assert "Intel inbox" in html
    assert "pulse-inbox-card" in html or "No candidates waiting" in html
    assert "pulse-collapse" in html
    assert "data-pulse-collapse" in html
    assert 'id="potential-watchlist"' in html
    assert 'href="/review"' in html
    assert "Data Insights" in html
    assert "Identify funnel" in html
    assert 'href="/capture"' in html
    watch_idx = html.index("potential-watchlist")
    inbox_idx = html.index("intel-inbox")
    digest_idx = html.index("knowledge-digest")
    pursuits_idx = html.index("tracked-pursuits")
    assert watch_idx < inbox_idx < digest_idx < pursuits_idx
    assert "Watchlist" in html
    assert "recompete-radar" not in html
    assert "sam-monitor" not in html
    assert "Knowledge digest" in html
    assert "domain_intel" in html or "bid-fit" in html.lower()


def test_pulse_not_pipeline_crm_copy():
    """Pulse doctrine — not full pipeline CRM; analytics on Insights."""
    client = TestClient(create_app())
    res = client.get("/pulse")
    html = res.text
    assert res.status_code == 200
    assert "not full pipeline" in html.lower()
    assert "Award totals live on" in html or "Insights" in html
    assert "cc-stat-tile" not in html