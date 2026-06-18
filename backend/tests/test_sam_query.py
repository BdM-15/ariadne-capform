import json

import pytest

from thread.intel.sam_query import (
    build_mcp_arguments,
    describe_sam_query,
    load_sam_queries,
    query_from_dict,
    resolve_active_sam_query,
)
from thread.config import Settings


def test_query_from_dict_requires_filter():
    assert query_from_dict({"id": "x", "name": "Empty"}) is None
    q = query_from_dict({"id": "sam1", "name": "Cyber O", "title": "cyber", "notice_type": "o"})
    assert q is not None
    assert q.title == "cyber"
    assert q.notice_type == "o"


def test_build_mcp_arguments_includes_posted_window():
    from datetime import date

    q = query_from_dict({"id": "a", "name": "Test", "title": "cloud", "days_back": 7})
    assert q is not None
    args = build_mcp_arguments(q, today=date(2026, 6, 17))
    assert args["posted_from"] == "06/10/2026"
    assert args["posted_to"] == "06/17/2026"
    assert args["title"] == "cloud"


def test_load_and_resolve_active_sam_query(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    state = tmp_path / ".thread"
    state.mkdir(parents=True)
    (state / "sam_queries.json").write_text(
        json.dumps(
            [
                {"id": "cyber-o", "name": "Cyber solicitations", "title": "cyber", "notice_type": "o"},
                {"id": "other", "name": "Other", "agency_keyword": "Army"},
            ]
        ),
        encoding="utf-8",
    )
    (state / "active_sam_query.json").write_text(json.dumps({"id": "cyber-o"}), encoding="utf-8")
    active = resolve_active_sam_query(settings)
    assert active is not None
    assert active.id == "cyber-o"
    assert "cyber" in describe_sam_query(active)