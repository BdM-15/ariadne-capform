"""Phase 12g — Intel inbox on Portfolio Pulse."""

import uuid

import pytest

from thread.services.intel_inbox import (
    INBOX_PREVIEW_LIMIT,
    _lane_from_mcp_server,
    _resolve_source_lane,
    _skill_id_from_item,
    build_intel_inbox_widget,
)
from thread.ui.review_display import ReviewQueueItem
from thread.services import opportunities as opp_svc
from thread.domain.schemas import OpportunityCreate


def test_lane_from_mcp_server():
    assert _lane_from_mcp_server("sam_gov") == "mcp_sam"
    assert _lane_from_mcp_server("usaspending") == "mcp_usaspending"
    assert _lane_from_mcp_server("ecfr") == "mcp"


def test_resolve_source_lane_packet():
    item = ReviewQueueItem(
        review_id=uuid.uuid4(),
        entity_type="packet_field_answer",
        title="Opportunity Name",
        subtitle="Packet field · opportunity_name",
        excerpt="Army Cloud",
    )
    lane, label, hint = _resolve_source_lane(item)
    assert lane == "packet"
    assert label == "Packet"
    assert hint is not None


def test_resolve_source_lane_insights_skill():
    item = ReviewQueueItem(
        review_id=uuid.uuid4(),
        entity_type="skill_run",
        title="Skill: datarepublican_intel",
        subtitle="Skill output",
        excerpt="3 contracts returned",
    )
    lane, label, hint = _resolve_source_lane(item, skill_id="datarepublican_intel")
    assert lane == "insights"
    assert "Insights" in label
    assert "Data Insights" in (hint or "")


def test_resolve_source_lane_mcp_skill():
    item = ReviewQueueItem(
        review_id=uuid.uuid4(),
        entity_type="skill_run",
        title="Skill: mcp_federal_tools",
        subtitle="Skill output",
        excerpt="ok",
    )
    lane, label, _ = _resolve_source_lane(item, skill_id="mcp_federal_tools", mcp_server="sam_gov")
    assert lane == "mcp_sam"
    assert label == "SAM.gov"


def test_skill_id_from_item():
    item = ReviewQueueItem(
        review_id=uuid.uuid4(),
        entity_type="skill_run",
        title="Skill: mcp_federal_tools",
        subtitle="x",
        excerpt="y",
    )
    assert _skill_id_from_item(item) == "mcp_federal_tools"


@pytest.mark.asyncio
async def test_build_intel_inbox_widget_from_packet_candidate(db_session, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Inbox {uuid.uuid4().hex[:6]}"),
    )
    await opp_svc.update_packet_field(
        db_session,
        opp.id,
        "opportunity_name",
        "Navy IT Recompete",
        as_candidate=True,
    )
    widget = await build_intel_inbox_widget(db_session, settings)
    assert widget.needs_attention is True
    assert widget.count >= 1
    assert len(widget.items) >= 1
    assert widget.items[0].source_lane == "packet"
    assert widget.items[0].opportunity_name == opp.name
    assert "Approve" in widget.items[0].suggested_action
    assert widget.lane_summary.startswith("Packet")


@pytest.mark.asyncio
async def test_inbox_preview_respects_limit(db_session, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    for i in range(INBOX_PREVIEW_LIMIT + 2):
        opp = await opp_svc.create_opportunity(
            db_session,
            OpportunityCreate(name=f"Bulk {i} {uuid.uuid4().hex[:4]}"),
        )
        await opp_svc.update_packet_field(
            db_session,
            opp.id,
            "opportunity_name",
            f"Candidate {i}",
            as_candidate=True,
        )
    widget = await build_intel_inbox_widget(db_session, settings)
    assert widget.count >= INBOX_PREVIEW_LIMIT + 2
    assert len(widget.items) == INBOX_PREVIEW_LIMIT