"""Foundation E2E smoke — intel signal → packet edit → review approve.

Requires local Postgres (docker on :55432). Skips if unreachable.
"""

from __future__ import annotations

import os
import socket
import uuid
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from thread.config import Settings
from thread.domain.enums import ReviewState, TrustLevel
from thread.domain.schemas import OpportunityCreate
from thread.main import create_app
from thread.services import opportunities as opp_svc
from thread.services.review_gate import approve_review, list_pending_reviews

pytestmark = pytest.mark.skipif(
    os.environ.get("THREAD_SKIP_PG_TESTS", "").lower() in ("1", "true", "yes"),
    reason="THREAD_SKIP_PG_TESTS set",
)


def _postgres_reachable() -> bool:
    """Socket probe only — avoid warming the app engine at import time."""
    try:
        url = Settings().database_url
        host = urlparse(url.replace("+asyncpg", "")).hostname or "127.0.0.1"
        port = urlparse(url.replace("+asyncpg", "")).port or 5432
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


if not _postgres_reachable():
    pytestmark = pytest.mark.skip(reason="Postgres not ready — start docker postgres")


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_smoke():
    """Reset module-level asyncpg pool between smokes (Windows TestClient loop clash)."""
    yield
    from thread.db import session as db_session_module

    await db_session_module.engine.dispose()


@pytest.mark.asyncio
async def test_z_smoke_service_path(db_session):
    """Core foundation path via services (runs last — avoids asyncpg loop clash with TestClient)."""
    tag = uuid.uuid4().hex[:8]
    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(
            name=f"Smoke Signal {tag}",
            award_key=f"SMOKE-{tag}",
            naics_code="561210",
            entry_reason="intel_signal",
        ),
    )
    assert opp.intel_provenance is not None
    assert opp.intel_provenance.get("award_key") == f"SMOKE-{tag}"

    answer = await opp_svc.update_packet_field(
        db_session,
        opp.id,
        "opportunity_name",
        f"DHS Cyber Recompete {tag}",
        as_candidate=True,
    )
    assert answer.trust_level == TrustLevel.CANDIDATE.value
    assert answer.review_state == ReviewState.PENDING_REVIEW.value

    pending = await list_pending_reviews(db_session)
    match = [
        r
        for r in pending
        if r.entity_type == "packet_field_answer" and r.entity_id == str(answer.id)
    ]
    assert len(match) == 1

    await approve_review(db_session, match[0].id)
    await db_session.refresh(answer)
    assert answer.trust_level == TrustLevel.TRUSTED.value
    assert answer.review_state == ReviewState.ACCEPTED.value
    assert answer.value == f"DHS Cyber Recompete {tag}"


@pytest.mark.asyncio
async def test_a_smoke_api_http_path():
    """Same path through /api/* (HTTP contract smoke)."""
    app = create_app()
    tag = uuid.uuid4().hex[:8]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/opportunities",
            json={
                "name": f"HTTP Smoke {tag}",
                "award_key": f"HTTP-{tag}",
                "naics_code": "561210",
                "entry_reason": "intel_signal",
            },
        )
        assert created.status_code == 200, created.text
        opp_id = created.json()["id"]
        assert created.json().get("intel_provenance")

        patched = await client.patch(
            f"/api/opportunities/{opp_id}/packet/opportunity_name",
            json={"value": f"Trusted via smoke {tag}"},
        )
        assert patched.status_code == 200
        assert patched.json()["trust_level"] == TrustLevel.CANDIDATE.value

        answer_id = patched.json()["id"]
        assert answer_id

        pending = await client.get("/api/review/pending")
        assert pending.status_code == 200
        match = [
            r
            for r in pending.json()
            if r["entity_type"] == "packet_field_answer" and r["entity_id"] == answer_id
        ]
        assert len(match) == 1, "expected one pending review for patched answer"
        review_id = match[0]["id"]

        approved = await client.post(f"/api/review/{review_id}/approve", json={})
        assert approved.status_code == 200
        assert approved.json()["review_state"] == ReviewState.ACCEPTED.value

        packet = await client.get(f"/api/opportunities/{opp_id}/packet")
        assert packet.status_code == 200
        field = next(f for f in packet.json()["fields"] if f["field_key"] == "opportunity_name")
        assert field["trust_level"] == TrustLevel.TRUSTED.value
        assert field["value"] == f"Trusted via smoke {tag}"


def test_b_smoke_htmx_track_signal_redirect():
    """HTMX track form returns redirect to opportunity workspace."""
    client = TestClient(create_app())
    tag = uuid.uuid4().hex[:8]
    res = client.post(
        "/signals/track",
        data={
            "award_key": f"HTMX-{tag}",
            "title": f"HTMX Smoke {tag}",
            "agency": "DHS",
            "naics_code": "561210",
        },
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    assert "HX-Redirect" in res.headers
    assert "/opportunities/" in res.headers["HX-Redirect"]