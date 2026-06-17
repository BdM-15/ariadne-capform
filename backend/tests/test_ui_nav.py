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
    ("/review", "Review Queue"),
    ("/knowledge", "Knowledge"),
    ("/settings", "Settings"),
)

DB_NAV_ROUTES = (("/", "Command Center"),)


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
    assert 'href="/pulse"' in html
    assert "data-lucide" in html
    assert 'data-lucide="layout-dashboard"' in html
    assert "Portfolio Pulse" in html
    # Global routes live in sidebar, not duplicated as topbar nav pills
    assert html.index("sidebar-vibrant") < html.index("glass-section-bar")
    assert 'href="/insights"' in html
    assert html.count('class="topbar-pill"') >= 1


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