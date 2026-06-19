"""Phase 16a — FAB intent classify (knowledge vs admin_task)."""

import pytest

from thread.services.capture_intent import CaptureIntent, classify_capture_intent_deterministic


def test_meeting_dump_classifies_as_admin_task():
    dump = "schedule a meeting for LIS SECREP transition prep with Molly B and Teresa Deming"
    assert classify_capture_intent_deterministic(dump) == CaptureIntent.ADMIN_TASK


def test_capability_note_stays_ambiguous_for_rules():
    dump = "edge computing capability from Jason Gray — add to company knowledge"
    assert classify_capture_intent_deterministic(dump) is None


def test_remind_keyword_classifies_as_admin_task():
    assert classify_capture_intent_deterministic("remind me to call DISA PM next Tuesday") == CaptureIntent.ADMIN_TASK