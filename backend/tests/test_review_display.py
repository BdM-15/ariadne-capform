import uuid

import pytest

from thread.ui.review_display import (
    _clip,
    _opportunity_id_from_run,
    _parse_research_entity,
    _provenance_excerpt,
    _run_for_opportunity,
    build_global_review_queue,
    build_review_queue,
)
from thread.services.review_gate import create_review_record
from thread.services import opportunities as opp_svc
from thread.domain.schemas import OpportunityCreate


def test_clip_truncates_long_text():
    assert _clip("a" * 400, 50).endswith("…")
    assert len(_clip("short")) == 5


def test_parse_research_entity():
    run_id = str(uuid.uuid4())
    assert _parse_research_entity(f"{run_id}:finding:2") == (run_id, "finding", 2)
    assert _parse_research_entity(f"{run_id}:interpretation") == (run_id, "interpretation", None)


def test_provenance_excerpt_prefers_url():
    ref, excerpt = _provenance_excerpt(
        [{"kind": "url", "ref": "https://example.com/doc", "excerpt": "Agency budget"}]
    )
    assert ref == "https://example.com/doc"
    assert "Agency" in (excerpt or "")


def test_run_for_opportunity_tagged():
    opp = uuid.uuid4()
    run = {"sources": [{"meta": "opportunity_id", "value": str(opp)}]}
    assert _opportunity_id_from_run(run) == opp
    assert _run_for_opportunity(run, opp) is True
    assert _run_for_opportunity(run, uuid.uuid4()) is False


@pytest.mark.asyncio
async def test_build_review_queue_shows_packet_field_label(db_session, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Review Display {uuid.uuid4().hex[:6]}"),
    )
    answer = await opp_svc.update_packet_field(
        db_session,
        opp.id,
        "opportunity_name",
        "DHS Enterprise Cyber Recompete",
        as_candidate=True,
    )
    pending = await build_review_queue(db_session, settings, opp.id)
    assert len(pending) >= 1
    packet_items = [i for i in pending if i.entity_type == "packet_field_answer"]
    assert packet_items
    assert packet_items[0].title == "Opportunity Name"
    assert "DHS Enterprise" in packet_items[0].excerpt
    assert packet_items[0].opportunity_id == opp.id
    assert packet_items[0].opportunity_name == opp.name


@pytest.mark.asyncio
async def test_build_global_review_queue_includes_opportunity_context(db_session, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Global Queue {uuid.uuid4().hex[:6]}"),
    )
    await opp_svc.update_packet_field(
        db_session,
        opp.id,
        "opportunity_name",
        "Army Cloud Recompete",
        as_candidate=True,
    )
    items = await build_global_review_queue(db_session, settings)
    packet_items = [i for i in items if i.entity_type == "packet_field_answer"]
    assert packet_items
    assert packet_items[0].opportunity_name == opp.name