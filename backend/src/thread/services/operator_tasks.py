"""Phase 16 — operator_tasks PG lane (EA / GTD execution truth)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from thread.config import Settings
from thread.db.models import OperatorTask, Opportunity
from thread.domain.enums import OperatorTaskSource, OperatorTaskStatus
from thread.services.capture_fab import CaptureContext, parse_opp_id
from thread.services.ingest_task_assistant import PolishedTaskDraft, polish_task_at_ingest


@dataclass(frozen=True)
class TaskListItem:
    id: uuid.UUID
    title: str
    description: str
    status: str
    priority: str
    task_kind: str
    due_at: datetime | None
    opportunity_id: uuid.UUID | None
    opportunity_name: str | None
    project_label: str | None
    is_overdue: bool
    attendees: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class TaskIngestResult:
    task_id: uuid.UUID
    title: str
    description: str
    polish_provider: str
    intent_provider: str


@dataclass(frozen=True)
class OpenTasksWidget:
    count: int
    preview: tuple[TaskListItem, ...]
    needs_attention: bool


def _utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    return start, end


def _task_to_item(row: OperatorTask) -> TaskListItem:
    now = datetime.now(timezone.utc)
    overdue = bool(
        row.due_at
        and row.due_at < now
        and row.status not in (OperatorTaskStatus.DONE.value, OperatorTaskStatus.CANCELLED.value)
    )
    opp_name = row.opportunity.name if row.opportunity else None
    attendees = tuple(row.attendees or ())
    return TaskListItem(
        id=row.id,
        title=row.title,
        description=row.description or "",
        status=row.status,
        priority=row.priority,
        task_kind=row.task_kind,
        due_at=row.due_at,
        opportunity_id=row.opportunity_id,
        opportunity_name=opp_name,
        project_label=row.project_label,
        is_overdue=overdue,
        attendees=attendees,
    )


async def ingest_fab_task(
    settings: Settings,
    session: AsyncSession,
    *,
    raw_dump: str,
    context: CaptureContext,
    intent_provider: str = "rules",
) -> TaskIngestResult:
    polished = await polish_task_at_ingest(
        settings,
        raw_dump,
        opportunity_name=context.opp_name,
    )
    task = await create_operator_task(
        session,
        raw_dump=raw_dump,
        polished=polished,
        opportunity_id=parse_opp_id(context.opp_id),
        provenance={
            "source": "fab",
            "context_label": context.context_label,
            "intent_provider": intent_provider,
        },
        llm_polish={"provider": polished.provider, "polished_at": datetime.now(timezone.utc).isoformat()},
    )
    await session.commit()
    return TaskIngestResult(
        task_id=task.id,
        title=task.title,
        description=task.description or "",
        polish_provider=polished.provider,
        intent_provider=intent_provider,
    )


async def create_operator_task(
    session: AsyncSession,
    *,
    raw_dump: str,
    polished: PolishedTaskDraft,
    opportunity_id: uuid.UUID | None = None,
    provenance: dict | None = None,
    llm_polish: dict | None = None,
    source: str = OperatorTaskSource.FAB.value,
) -> OperatorTask:
    now = datetime.now(timezone.utc)
    row = OperatorTask(
        title=polished.title,
        description=polished.description,
        raw_dump=raw_dump,
        task_kind=polished.task_kind,
        status=polished.status,
        priority=polished.priority,
        due_at=polished.due_at,
        start_at=polished.start_at,
        duration_minutes=polished.duration_minutes,
        opportunity_id=opportunity_id,
        project_label=polished.project_label,
        context_tags=list(polished.context_tags),
        attendees=list(polished.attendees),
        location=polished.location,
        waiting_on=polished.waiting_on,
        categories=list(polished.categories),
        checklist=list(polished.checklist),
        source=source,
        provenance=provenance,
        llm_polish=llm_polish,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    return row


_OPEN_STATUSES = (
    OperatorTaskStatus.INBOX.value,
    OperatorTaskStatus.NEXT.value,
    OperatorTaskStatus.WAITING.value,
    OperatorTaskStatus.SCHEDULED.value,
    OperatorTaskStatus.DEFERRED.value,
)


async def list_operator_tasks(
    session: AsyncSession,
    *,
    filter_key: str = "open",
    opportunity_id: uuid.UUID | None = None,
) -> list[TaskListItem]:
    stmt = select(OperatorTask).options(selectinload(OperatorTask.opportunity)).order_by(
        OperatorTask.due_at.asc().nulls_last(),
        OperatorTask.created_at.desc(),
    )
    today = date.today()
    day_start, day_end = _utc_day_bounds(today)
    now = datetime.now(timezone.utc)

    if filter_key == "today":
        stmt = stmt.where(
            OperatorTask.status.in_(_OPEN_STATUSES),
            or_(
                OperatorTask.due_at.between(day_start, day_end),
                OperatorTask.start_at.between(day_start, day_end),
            ),
        )
    elif filter_key == "overdue":
        stmt = stmt.where(
            OperatorTask.status.in_(_OPEN_STATUSES),
            OperatorTask.due_at.is_not(None),
            OperatorTask.due_at < now,
        )
    elif filter_key == "done":
        stmt = stmt.where(OperatorTask.status == OperatorTaskStatus.DONE.value)
    else:
        stmt = stmt.where(OperatorTask.status.in_(_OPEN_STATUSES))

    if opportunity_id is not None:
        stmt = stmt.where(OperatorTask.opportunity_id == opportunity_id)

    rows = (await session.execute(stmt)).scalars().all()
    return [_task_to_item(row) for row in rows]


async def count_open_tasks(session: AsyncSession) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(OperatorTask)
            .where(OperatorTask.status.in_(_OPEN_STATUSES))
        )
        or 0
    )


async def get_task_list_item(session: AsyncSession, task_id: uuid.UUID) -> TaskListItem | None:
    stmt = (
        select(OperatorTask)
        .options(selectinload(OperatorTask.opportunity))
        .where(OperatorTask.id == task_id)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    return _task_to_item(row) if row else None


_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    OperatorTaskStatus.INBOX.value: {
        OperatorTaskStatus.NEXT.value,
        OperatorTaskStatus.SCHEDULED.value,
        OperatorTaskStatus.WAITING.value,
        OperatorTaskStatus.DONE.value,
        OperatorTaskStatus.DEFERRED.value,
    },
    OperatorTaskStatus.NEXT.value: {
        OperatorTaskStatus.SCHEDULED.value,
        OperatorTaskStatus.WAITING.value,
        OperatorTaskStatus.DONE.value,
        OperatorTaskStatus.DEFERRED.value,
    },
    OperatorTaskStatus.SCHEDULED.value: {
        OperatorTaskStatus.NEXT.value,
        OperatorTaskStatus.DONE.value,
        OperatorTaskStatus.DEFERRED.value,
    },
    OperatorTaskStatus.WAITING.value: {
        OperatorTaskStatus.NEXT.value,
        OperatorTaskStatus.DONE.value,
    },
    OperatorTaskStatus.DEFERRED.value: {
        OperatorTaskStatus.NEXT.value,
        OperatorTaskStatus.INBOX.value,
    },
    OperatorTaskStatus.DONE.value: {OperatorTaskStatus.INBOX.value},
}


async def update_operator_task_status(
    session: AsyncSession,
    task_id: uuid.UUID,
    new_status: str,
) -> OperatorTask:
    clean = new_status.strip().lower()
    allowed = {s.value for s in OperatorTaskStatus}
    if clean not in allowed:
        raise ValueError(f"Invalid status: {new_status}")

    row = await session.get(OperatorTask, task_id)
    if row is None:
        raise ValueError("Task not found")

    transitions = _ALLOWED_TRANSITIONS.get(row.status, set())
    if clean != row.status and clean not in transitions:
        raise ValueError(f"Cannot move {row.status} → {clean}")

    now = datetime.now(timezone.utc)
    row.status = clean
    row.updated_at = now
    if clean == OperatorTaskStatus.DONE.value:
        row.completed_at = now
    elif row.completed_at is not None:
        row.completed_at = None
    await session.flush()
    return row


async def complete_operator_task(session: AsyncSession, task_id: uuid.UUID) -> OperatorTask:
    return await update_operator_task_status(session, task_id, OperatorTaskStatus.DONE.value)


async def build_open_tasks_widget(
    session: AsyncSession,
    *,
    preview_limit: int = 3,
) -> OpenTasksWidget:
    items = await list_operator_tasks(session, filter_key="open")
    count = len(items)
    return OpenTasksWidget(
        count=count,
        preview=tuple(items[:preview_limit]),
        needs_attention=count > 0,
    )