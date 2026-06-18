import json

import pytest

from thread.intel.sam_query import query_from_dict
from thread.services.sam_monitor import (
    SamNoticeLead,
    _read_cache,
    _write_cache,
    build_sam_monitor_widget,
    parse_notices_from_mcp_output,
)


SAMPLE_SAM_JSON = json.dumps(
    {
        "totalRecords": 1,
        "opportunitiesData": [
            {
                "noticeId": "abc123def456",
                "title": "Enterprise IT Support Services",
                "solicitationNumber": "W912HQ-26-R-0001",
                "department": "DEPT OF DEFENSE",
                "subtier": "DEPT OF THE ARMY",
                "postedDate": "06/15/2026",
                "responseDeadLine": "07/01/2026",
                "naicsCode": "541512",
                "baseType": "o",
                "typeOfSetAside": "SBA",
            }
        ],
    }
)


def test_parse_notices_from_mcp_output():
    leads = parse_notices_from_mcp_output(SAMPLE_SAM_JSON)
    assert len(leads) == 1
    assert leads[0].notice_id == "abc123def456"
    assert "IT Support" in leads[0].title
    assert "DEFENSE" in leads[0].agency
    assert leads[0].solicitation_number == "W912HQ-26-R-0001"


def test_sam_cache_roundtrip(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    notice = SamNoticeLead(
        notice_id="n1",
        title="Test Notice",
        agency="GSA",
        solicitation_number=None,
        response_deadline=None,
        posted_date=None,
        notice_type="o",
        set_aside=None,
        naics_code=None,
    )
    _write_cache(settings, "q1", [notice])
    cached = _read_cache(settings, "q1")
    assert cached is not None
    notices, fetched_at = cached
    assert len(notices) == 1
    assert notices[0].notice_id == "n1"


@pytest.mark.asyncio
async def test_build_sam_monitor_no_query(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    widget = await build_sam_monitor_widget(settings)
    assert widget.status in ("not_configured", "no_query")


@pytest.mark.asyncio
async def test_build_sam_monitor_uses_cache(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    state = tmp_path / ".thread"
    state.mkdir(parents=True)
    (state / "sam_queries.json").write_text(
        json.dumps([{"id": "q1", "name": "Test", "title": "cloud"}]),
        encoding="utf-8",
    )
    (state / "active_sam_query.json").write_text(json.dumps({"id": "q1"}), encoding="utf-8")
    _write_cache(
        settings,
        "q1",
        [
            SamNoticeLead(
                notice_id="cached-1",
                title="Cached Cloud Services",
                agency="NASA",
                solicitation_number="NNG26",
                response_deadline="08/01/2026",
                posted_date="06/01/2026",
                notice_type="o",
                set_aside=None,
                naics_code="541512",
            )
        ],
    )

    async def fail_invoke(*_args, **_kwargs):
        raise AssertionError("MCP should not be called when cache is fresh")

    monkeypatch.setattr("thread.services.sam_monitor.MCPService.invoke", fail_invoke)
    monkeypatch.setattr(
        "thread.services.sam_monitor._sam_configured",
        lambda _settings: True,
    )

    widget = await build_sam_monitor_widget(settings)
    assert widget.status == "ready"
    assert widget.cache_hit is True
    assert widget.notices[0].notice_id == "cached-1"


@pytest.mark.asyncio
async def test_track_sam_notice_creates_opp(db_session, settings, tmp_path, monkeypatch):
    from thread.domain.schemas import OpportunityCreate
    from thread.services import opportunities as opp_svc
    from thread.ui.routes import track_sam_notice_form
    from unittest.mock import MagicMock

    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    request = MagicMock()
    request.headers.get.return_value = None

    await track_sam_notice_form(
        request=request,
        notice_id="sam-notice-xyz",
        title="Cloud Migration",
        agency="Department of Veterans Affairs",
        solicitation_number="36C10B-26-R-0002",
        notice_type="o",
        naics_code="541512",
        db=db_session,
    )
    await db_session.commit()
    opps = await opp_svc.list_opportunities(db_session)
    tracked = [o for o in opps if o.intel_provenance and o.intel_provenance.get("notice_id") == "sam-notice-xyz"]
    assert tracked
    assert tracked[0].entry_reason == "sam_notice"