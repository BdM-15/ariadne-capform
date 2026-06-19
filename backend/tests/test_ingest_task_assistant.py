"""Phase 16a — EA task polish at ingest."""

from thread.domain.enums import OperatorTaskKind, OperatorTaskStatus
from thread.services.ingest_task_assistant import rules_polish_task


def test_rules_polish_meeting_extracts_title_and_attendees():
    dump = "schedule a meeting for LIS SECREP transition prep with Molly B and Teresa Deming"
    polished = rules_polish_task(dump)
    assert polished.provider == "rules"
    assert "Meeting" in polished.title or "Schedule" in polished.title
    assert polished.task_kind == OperatorTaskKind.MEETING.value
    assert polished.status == OperatorTaskStatus.SCHEDULED.value
    names = {a["name"] for a in polished.attendees}
    assert "Molly B" in names
    assert polished.project_label is not None