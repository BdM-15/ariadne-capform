"""Phase 16g/16h — task drawer HTTP smoke (single-request; full flow in verify script)."""

import uuid

from fastapi.testclient import TestClient

from thread.main import create_app
from thread.services.ingest_task_assistant import rules_polish_task


def test_task_drawer_partial_404():
    client = TestClient(create_app())
    res = client.get(f"/partials/tasks/{uuid.uuid4()}/drawer")
    assert res.status_code == 404


def test_meeting_rules_polish_includes_checklist():
    polished = rules_polish_task("schedule meeting with Molly for SECREP prep")
    assert polished.task_kind == "meeting"
    assert len(polished.checklist) >= 2


