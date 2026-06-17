from fastapi.testclient import TestClient

from thread.main import create_app


def test_list_skills_endpoint():
    client = TestClient(create_app())
    res = client.get("/api/skills")
    assert res.status_code == 200
    ids = {row["id"] for row in res.json()}
    assert "skill-creator" in ids


def test_mcp_catalog_endpoint():
    client = TestClient(create_app())
    res = client.get("/api/intel/mcp")
    assert res.status_code == 200
    assert len(res.json()) >= 8