"""Phase 14j — connected fill routes for open packet fields."""

from __future__ import annotations

import uuid

import pytest

from thread.domain.schemas import OpportunityCreate
from thread.services import opportunities as opp_svc
from thread.services.packet_workflows import build_slide_fill_workflows, workflow_actions_for_field
from thread.services.packet_workspace import build_packet_workspace


@pytest.mark.asyncio
async def test_fill_workflows_include_open_fields_only(db_session):
    opp = await opp_svc.create_opportunity(db_session, OpportunityCreate(name=f"WF {uuid.uuid4().hex[:6]}"))
    view = await build_packet_workspace(db_session, opp.id, active_slide="slide_4_synopsis")
    assert view["fill_workflows"]
    assert all(not (w.get("label") == "") for w in view["fill_workflows"])
    for wf in view["fill_workflows"]:
        assert wf["actions"]
        assert any(a["id"] == "inspector" for a in wf["actions"])


def test_workflow_actions_map_intel_sources():
    actions = workflow_actions_for_field(
        {
            "field_key": "prime_name",
            "answer_sources": ["pg_intel", "clew_intel", "grok_synthesis"],
            "route_kind": "source_profile_lookup",
        },
        opp_id="abc",
    )
    labels = {a["label"] for a in actions}
    assert "USAspending intel" in labels
    assert "Clew trace" in labels
    assert "Grok synthesis" in labels


def test_build_slide_fill_workflows_skips_filled():
    workflows = build_slide_fill_workflows(
        [
            {"field_key": "a", "label": "A", "value": "done", "status": "answered", "answer_sources": []},
            {"field_key": "b", "label": "B", "value": "", "status": "unanswered", "answer_sources": ["human_input"]},
        ],
        opp_id="x",
    )
    assert len(workflows) == 1
    assert workflows[0]["field_key"] == "b"