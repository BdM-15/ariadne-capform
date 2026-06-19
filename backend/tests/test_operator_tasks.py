"""Phase 16 — operator_tasks service + FAB task lane."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from thread.domain.enums import OperatorTaskStatus
from thread.domain.schemas import OpportunityCreate
from thread.main import create_app
from thread.services import opportunities as opp_svc
from thread.services.capture_fab import build_capture_context
from thread.services.ingest_task_assistant import rules_polish_task
from thread.services.operator_tasks import (
    complete_operator_task,
    count_open_tasks,
    create_operator_task,
    ingest_fab_task,
    list_operator_tasks,
)


@pytest.mark.asyncio
async def test_create_task_stores_polished_title_not_raw(db_session):
    raw = "schedule meetign with bob for cyber thing"
    polished = rules_polish_task(raw)
    task = await create_operator_task(db_session, raw_dump=raw, polished=polished)
    await db_session.commit()

    assert task.title != raw
    assert task.raw_dump == raw
    assert task.status in (OperatorTaskStatus.INBOX.value, OperatorTaskStatus.SCHEDULED.value)


@pytest.mark.asyncio
async def test_complete_task_marks_done(db_session):
    polished = rules_polish_task("remind me to email PM")
    task = await create_operator_task(db_session, raw_dump="remind me to email PM", polished=polished)
    await db_session.flush()
    done = await complete_operator_task(db_session, task.id)
    await db_session.commit()
    assert done.status == OperatorTaskStatus.DONE.value
    assert done.completed_at is not None


@pytest.mark.asyncio
async def test_list_open_tasks_excludes_done(db_session):
    polished = rules_polish_task("call teresa")
    open_task = await create_operator_task(db_session, raw_dump="call teresa", polished=polished)
    done_polish = rules_polish_task("email molly")
    done_task = await create_operator_task(db_session, raw_dump="email molly", polished=done_polish)
    await complete_operator_task(db_session, done_task.id)
    await db_session.commit()

    open_items = await list_operator_tasks(db_session, filter_key="open")
    ids = {item.id for item in open_items}
    assert open_task.id in ids
    assert done_task.id not in ids


@pytest.mark.asyncio
async def test_fab_task_ingest_with_opportunity_link(db_session, settings, monkeypatch):
    monkeypatch.setattr(settings, "local_admin_model_enabled", False)
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name="LIS SECREP", lifecycle_state="pursuing"),
    )
    await db_session.flush()
    ctx = build_capture_context(opp_id=str(opp.id), opp_name=opp.name)
    result = await ingest_fab_task(
        settings,
        db_session,
        raw_dump="schedule meeting with Molly B for transition prep",
        context=ctx,
        intent_provider="rules",
    )
    assert result.title
    items = await list_operator_tasks(db_session, filter_key="open")
    match = next(i for i in items if i.id == result.task_id)
    assert match.opportunity_id == opp.id
    assert match.opportunity_name == "LIS SECREP"


@pytest.mark.asyncio
async def test_count_open_tasks(db_session):
    polished = rules_polish_task("todo buy stamps")
    await create_operator_task(db_session, raw_dump="todo buy stamps", polished=polished)
    await db_session.commit()
    n = await count_open_tasks(db_session)
    assert n >= 1


def test_fab_meeting_dump_routes_to_tasks_not_vault(settings, monkeypatch):
    """Integration — meeting FAB POST lands in Tasks success UI."""
    from thread.db.migrate import run_workflow_migrations

    run_workflow_migrations(settings)
    monkeypatch.setattr(settings, "local_admin_model_enabled", False)

    client = TestClient(create_app())
    dump = "schedule a meeting for LIS SECREP transition prep with Molly B"
    res = client.post("/partials/capture/quick", data={"dump": dump})
    assert res.status_code == 200, res.text[:500]
    assert "Added to Tasks" in res.text
    assert "Open in Vault Inbox" not in res.text
    assert "/tasks" in res.text