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
    ("/insights", "Data Insights"),
    ("/knowledge", "Knowledge"),
    ("/settings", "Settings"),
    ("/tools/mcp", "MCP Servers"),
    ("/tools/skills", "Agent Skills"),
)

DB_NAV_ROUTES = (
    ("/", "Command Center"),
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


def test_shell_stub_pages_declare_product_lane():
    client = TestClient(create_app())
    res = client.get("/insights")
    assert res.status_code == 200
    assert "Identify" in res.text
    assert "Phase 17" in res.text

    res = client.get("/knowledge")
    assert "Capture" in res.text


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
    assert "Platform health" in html or "read-only" in html
    assert 'class="acc ' in html
    assert "Intel migration" in html
    assert "Research providers" in html
    assert "Grok" in html or "xAI" in html
    assert "default_naics" in html


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
    assert "datarepublican_intel" in html or "skill-creator" in html


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


def test_dashboard_hot_signals_widget():
    """Phase 12f — hot recompete widget on Command Center."""
    client = TestClient(create_app())
    res = client.get("/")
    html = res.text
    assert res.status_code == 200
    assert "cc-widget-hot-signals" in html
    assert "Hot recompete" in html
    assert "/pulse#recompete-radar" in html
    assert "cc-widget-grid-3" in html


def test_dashboard_quick_actions_strip():
    """Phase 12h — compact action chips, not full-width buttons."""
    client = TestClient(create_app())
    res = client.get("/")
    html = res.text
    assert res.status_code == 200
    assert "cc-quick-actions" in html
    assert "Track signal" in html
    assert "/pulse#recompete-radar" in html
    assert 'href="/insights"' in html
    assert 'href="/knowledge"' in html


def test_dashboard_compact_layout_and_phase_band_widget():
    """Phase 12d — widget grid + phase-band breakdown, not lazy full-width cards."""
    client = TestClient(create_app())
    res = client.get("/")
    html = res.text
    assert res.status_code == 200
    assert "cc-widget-grid" in html
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
    assert "cc-stat-tile" in html