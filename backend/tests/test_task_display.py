"""Phase 16f — GTD board display + status action UX."""

import uuid

import pytest

from thread.domain.enums import OperatorTaskStatus
from thread.services.ingest_task_assistant import rules_polish_task
from thread.services.operator_tasks import (
    create_operator_task,
    get_task_list_item,
    list_operator_tasks,
    update_operator_task_status,
)
from thread.services.task_display import build_tasks_page_context, task_actions_for


def test_task_actions_for_inbox_includes_complete():
    actions = task_actions_for(OperatorTaskStatus.INBOX.value)
    labels = {a.label for a in actions}
    statuses = {a.status for a in actions}
    assert "Mark complete" in labels
    assert "Move to Next" in labels
    assert OperatorTaskStatus.DONE.value in statuses
    assert OperatorTaskStatus.NEXT.value in statuses


def test_task_actions_for_done_includes_reopen():
    actions = task_actions_for(OperatorTaskStatus.DONE.value)
    assert len(actions) == 1
    assert actions[0].status == OperatorTaskStatus.INBOX.value
    assert actions[0].label == "Reopen"


def test_build_tasks_page_context_board_lanes():
    item_id = uuid.uuid4()
    from thread.services.operator_tasks import TaskListItem

    items = [
        TaskListItem(
            id=item_id,
            title="Prep call",
            description="",
            status=OperatorTaskStatus.INBOX.value,
            priority="normal",
            task_kind="call",
            due_at=None,
            opportunity_id=None,
            opportunity_name=None,
            project_label=None,
            is_overdue=False,
            attendees=(),
        ),
        TaskListItem(
            id=uuid.uuid4(),
            title="Email PM",
            description="",
            status=OperatorTaskStatus.NEXT.value,
            priority="normal",
            task_kind="email",
            due_at=None,
            opportunity_id=None,
            opportunity_name=None,
            project_label=None,
            is_overdue=False,
            attendees=(),
        ),
    ]
    page = build_tasks_page_context(items, filter_key="open", view_mode="board", open_count=2)
    assert page.view_mode == "board"
    assert page.inbox_count == 1
    assert page.next_count == 1
    lane_titles = [lane.title for lane in page.lanes]
    assert "Inbox" in lane_titles
    assert "Next" in lane_titles


@pytest.mark.asyncio
async def test_update_status_inbox_to_next(db_session):
    polished = rules_polish_task("schedule meeting with PM")
    task = await create_operator_task(db_session, raw_dump="schedule meeting", polished=polished)
    await update_operator_task_status(db_session, task.id, OperatorTaskStatus.NEXT.value)
    await db_session.commit()

    item = await get_task_list_item(db_session, task.id)
    assert item is not None
    assert item.status == OperatorTaskStatus.NEXT.value


@pytest.mark.asyncio
async def test_update_status_rejects_invalid_transition(db_session):
    polished = rules_polish_task("email DISA about timeline")
    task = await create_operator_task(db_session, raw_dump="email DISA", polished=polished)
    await update_operator_task_status(db_session, task.id, OperatorTaskStatus.DONE.value)
    with pytest.raises(ValueError, match="Cannot move"):
        await update_operator_task_status(db_session, task.id, OperatorTaskStatus.NEXT.value)


@pytest.mark.asyncio
async def test_done_filter_lists_completed_only(db_session):
    open_polish = rules_polish_task("call teresa")
    done_polish = rules_polish_task("email molly")
    open_task = await create_operator_task(db_session, raw_dump="call teresa", polished=open_polish)
    done_task = await create_operator_task(db_session, raw_dump="email molly", polished=done_polish)
    await update_operator_task_status(db_session, done_task.id, OperatorTaskStatus.DONE.value)
    await db_session.commit()

    done_items = await list_operator_tasks(db_session, filter_key="done")
    done_ids = {i.id for i in done_items}
    assert done_task.id in done_ids
    assert open_task.id not in done_ids