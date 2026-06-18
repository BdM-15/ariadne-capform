"""Phase 12l — Agent Skills run UX on /tools/skills."""

from fastapi.testclient import TestClient

from thread.main import create_app


def test_skills_page_has_run_panel_trigger():
    client = TestClient(create_app())
    res = client.get("/tools/skills")
    html = res.text
    assert res.status_code == 200
    assert "clew_intel" in html
    assert 'hx-get="/partials/tools/skills/clew_intel/panel"' in html
    assert "Phase 20" not in html
    assert "cursor-not-allowed" not in html or "wired" in html


def test_skills_run_panel_partial():
    client = TestClient(create_app())
    res = client.get("/partials/tools/skills/skill-creator/panel")
    assert res.status_code == 200
    assert 'hx-post="/tools/skills/skill-creator/run"' in res.text


def test_skills_run_skill_creator():
    client = TestClient(create_app())
    res = client.post("/tools/skills/skill-creator/run", data={})
    assert res.status_code == 200
    assert "existing_skills" in res.text or "skills_root" in res.text
    assert "Review queue" in res.text or "review" in res.text.lower()


def test_skills_run_unknown_skill():
    client = TestClient(create_app())
    res = client.post("/tools/skills/not_a_skill/run", data={})
    assert res.status_code == 404


def test_skills_run_mcp_invalid_json():
    client = TestClient(create_app())
    res = client.post(
        "/tools/skills/mcp_federal_tools/run",
        data={"server": "sam_gov", "tool": "search_opportunities", "arguments": "not-json"},
    )
    assert res.status_code == 200
    assert "Invalid arguments JSON" in res.text