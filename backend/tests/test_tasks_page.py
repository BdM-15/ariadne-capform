"""Phase 16b–16d — /tasks page, C&C widget, opp chip."""

import uuid

import pytest
from fastapi.testclient import TestClient

from thread.domain.schemas import OpportunityCreate
from thread.main import create_app
from thread.services import opportunities as opp_svc
from thread.services.ingest_task_assistant import rules_polish_task
from thread.services.operator_tasks import (
    complete_operator_task,
    create_operator_task,
    get_task_list_item,
    list_operator_tasks,
)


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_tasks_test():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


def test_tasks_page_shell():
    client = TestClient(create_app())
    res = client.get("/tasks")
    assert res.status_code == 200
    assert "Tasks" in res.text
    assert "tasks-body" in res.text
    assert "tasks-checkoff" in res.text or "No tasks" in res.text


def test_command_center_shows_open_tasks_widget():
    client = TestClient(create_app())
    res = client.get("/")
    assert res.status_code == 200
    assert "cc-widget-open-tasks" in res.text
    assert "/tasks#today" in res.text


@pytest.mark.asyncio
async def test_list_open_tasks_after_create(db_session):
    polished = rules_polish_task("schedule meeting with PM about cyber")
    await create_operator_task(db_session, raw_dump="schedule meeting with PM", polished=polished)
    await db_session.commit()

    items = await list_operator_tasks(db_session, filter_key="open")
    assert any("Meeting" in i.title or "Schedule" in i.title for i in items)


@pytest.mark.asyncio
async def test_complete_task_marks_done(db_session):
    polished = rules_polish_task("email DISA about timeline")
    task = await create_operator_task(db_session, raw_dump="email DISA", polished=polished)
    await complete_operator_task(db_session, task.id)
    await db_session.commit()

    item = await get_task_list_item(db_session, task.id)
    assert item is not None
    assert item.status == "done"


@pytest.mark.asyncio
async def test_task_item_includes_opportunity_link(db_session):
    tag = uuid.uuid4().hex[:8]
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Army Cyber {tag}", lifecycle_state="pursuing"),
    )
    polished = rules_polish_task("schedule prep call")
    await create_operator_task(
        db_session,
        raw_dump="schedule prep call",
        polished=polished,
        opportunity_id=opp.id,
    )
    await db_session.commit()

    items = await list_operator_tasks(db_session, filter_key="open")
    match = next(i for i in items if i.opportunity_id == opp.id)
    assert match.opportunity_name == f"Army Cyber {tag}"