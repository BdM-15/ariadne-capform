"""Tasks page — GTD lanes + operator accomplish UX."""

from __future__ import annotations

from dataclasses import dataclass

from thread.domain.enums import OperatorTaskStatus
from thread.services.operator_tasks import TaskListItem
from thread.ui.tasks_guides import action_hint

_LANE_ORDER: tuple[tuple[str, str, str], ...] = (
    (OperatorTaskStatus.INBOX.value, "Inbox", "New from FAB — clarify before doing"),
    (OperatorTaskStatus.NEXT.value, "Next", "Do now — your highest-leverage queue"),
    (OperatorTaskStatus.SCHEDULED.value, "Scheduled", "Time-bound — calendar / due date"),
    (OperatorTaskStatus.WAITING.value, "Waiting", "Blocked — waiting on someone else"),
    (OperatorTaskStatus.DEFERRED.value, "Deferred", "Someday — low urgency backlog"),
)

_STATUS_ACTIONS: dict[str, tuple[tuple[str, str, str], ...]] = {
    OperatorTaskStatus.INBOX.value: (
        ("next", "Move to Next", "arrow-right-circle"),
        ("scheduled", "Move to Scheduled", "calendar"),
        ("waiting", "Move to Waiting", "hourglass"),
        ("done", "Mark complete", "circle-check"),
    ),
    OperatorTaskStatus.NEXT.value: (
        ("scheduled", "Move to Scheduled", "calendar"),
        ("waiting", "Move to Waiting", "hourglass"),
        ("done", "Mark complete", "circle-check"),
        ("deferred", "Defer", "archive"),
    ),
    OperatorTaskStatus.SCHEDULED.value: (
        ("next", "Move to Next", "arrow-right-circle"),
        ("done", "Mark complete", "circle-check"),
        ("deferred", "Defer", "archive"),
    ),
    OperatorTaskStatus.WAITING.value: (
        ("next", "Move to Next", "arrow-right-circle"),
        ("done", "Mark complete", "circle-check"),
    ),
    OperatorTaskStatus.DEFERRED.value: (
        ("next", "Move to Next", "arrow-right-circle"),
        ("inbox", "Back to Inbox", "inbox"),
    ),
    OperatorTaskStatus.DONE.value: (
        ("inbox", "Reopen", "rotate-ccw"),
    ),
}


@dataclass(frozen=True)
class TaskLane:
    status: str
    title: str
    hint: str
    items: tuple[TaskListItem, ...]


@dataclass(frozen=True)
class TaskAction:
    status: str
    label: str
    icon: str
    hint: str


@dataclass(frozen=True)
class TasksPageContext:
    items: tuple[TaskListItem, ...]
    lanes: tuple[TaskLane, ...]
    filter_key: str
    view_mode: str
    open_count: int
    inbox_count: int
    next_count: int
    scheduled_count: int
    overdue_count: int


def task_actions_for(status: str) -> tuple[TaskAction, ...]:
    return tuple(
        TaskAction(status=key, label=label, icon=icon, hint=action_hint(key))
        for key, label, icon in _STATUS_ACTIONS.get(status, ())
    )


def build_tasks_page_context(
    items: list[TaskListItem],
    *,
    filter_key: str,
    view_mode: str,
    open_count: int,
) -> TasksPageContext:
    by_status: dict[str, list[TaskListItem]] = {key: [] for key, _, _ in _LANE_ORDER}
    for item in items:
        if item.status in by_status:
            by_status[item.status].append(item)
        elif item.status == OperatorTaskStatus.DONE.value and filter_key == "done":
            by_status.setdefault("_done", []).append(item)

    lanes: list[TaskLane] = []
    if filter_key == "done":
        done_items = [i for i in items if i.status == OperatorTaskStatus.DONE.value]
        lanes.append(TaskLane("done", "Done", "Completed — reopen or archive", tuple(done_items)))
    else:
        for status, title, hint in _LANE_ORDER:
            lanes.append(TaskLane(status, title, hint, tuple(by_status.get(status, []))))

    inbox_count = len(by_status.get(OperatorTaskStatus.INBOX.value, []))
    next_count = len(by_status.get(OperatorTaskStatus.NEXT.value, []))
    scheduled_count = len(by_status.get(OperatorTaskStatus.SCHEDULED.value, []))
    overdue_count = sum(1 for i in items if i.is_overdue)

    return TasksPageContext(
        items=tuple(items),
        lanes=tuple(lanes),
        filter_key=filter_key,
        view_mode=view_mode if view_mode in ("board", "list") else "board",
        open_count=open_count,
        inbox_count=inbox_count,
        next_count=next_count,
        scheduled_count=scheduled_count,
        overdue_count=overdue_count,
    )