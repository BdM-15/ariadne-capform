"""Phase 12a — command center nav and shell stubs."""

from fastapi.testclient import TestClient

from thread.main import create_app

NAV_ROUTES = (
    ("/", "pulse", "Portfolio Pulse"),
    ("/insights", "insights", "Data Insights"),
    ("/review", "review", "Review Queue"),
    ("/knowledge", "knowledge", "Knowledge"),
    ("/settings", "settings", "Settings"),
)


def test_shell_nav_routes_return_200():
    client = TestClient(create_app())
    for path, _nav, heading in NAV_ROUTES:
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
    """Stub route avoids PG; verifies sidebar + panel-canvas shell."""
    client = TestClient(create_app())
    res = client.get("/insights")
    assert res.status_code == 200
    assert "sidebar-vibrant" in res.text
    assert "nav-item-active" in res.text
    assert "panel-canvas" in res.text
    assert "glass-section-bar" in res.text
    assert 'href="/settings"' in res.text
    assert "Settings" in html
    assert "nav-group-cyan" in res.text
    assert "nav-group-magenta" in res.text