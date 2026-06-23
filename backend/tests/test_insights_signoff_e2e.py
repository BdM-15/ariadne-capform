"""Phase 17e-e — MVP sign-off funnel: find → watch → track → packet fill from intel.

Requires local Postgres with intel prime awards loaded. Skips if unreachable or no expiring rows.
Uses httpx AsyncClient (not TestClient) to avoid Windows asyncpg loop clashes.
"""

from __future__ import annotations

import os
import re
import socket
import uuid
from urllib.parse import urlparse

import pytest
from httpx import ASGITransport, AsyncClient

from thread.config import Settings, get_settings, reload_settings
from thread.domain.packet_answer_sources import PG_INTEL
from thread.main import create_app
from thread.services.insights_signoff import discover_expiring_award
from thread.services.watchlist import load_watchlist

pytestmark = pytest.mark.skipif(
    os.environ.get("THREAD_SKIP_PG_TESTS", "").lower() in ("1", "true", "yes"),
    reason="THREAD_SKIP_PG_TESTS set",
)


def _postgres_reachable() -> bool:
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
async def _dispose_app_engine_after_signoff_smoke():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


def _capture_id_from_redirect(header: str) -> str:
    match = re.search(r"/capture/([0-9a-f-]{36})", header)
    assert match, f"Expected /capture/{{id}} in redirect, got {header!r}"
    return match.group(1)


@pytest.mark.asyncio
async def test_insights_mvp_signoff_funnel(db_session, tmp_path, monkeypatch):
    """Facet slice → Overview → Watch → Pulse → Track → PG intel packet fill."""
    state = tmp_path / ".thread"
    state.mkdir(parents=True)
    reload_settings()
    settings = get_settings().model_copy(update={"thread_state_dir": state.resolve()})

    seed = await discover_expiring_award(db_session)
    if seed is None:
        pytest.skip("No expiring prime awards in PG — intel migration or date window empty")

    naics = seed["naics_code"]
    award_key = seed["award_key"]
    tag = uuid.uuid4().hex[:8]
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=180.0) as client:
        overview = await client.get(
            "/partials/insights/slice",
            params={"run": 1, "lens": "overview", "naics_codes": naics},
        )
        assert overview.status_code == 200, overview.text[:500]
        html = overview.text
        assert "insights-slice-panel" in html
        assert (
            "insights-echarts-hero" in html
            or "insights-kpi-strip" in html
            or "Capture intensity" in html
            or "obligated" in html.lower()
        ), "Overview lens should show market picture"

        recompete = await client.get(
            "/partials/insights/slice",
            params={"run": 1, "lens": "recompete", "naics_codes": naics},
        )
        assert recompete.status_code == 200
        assert award_key in recompete.text or seed["recipient"][:12] in recompete.text

        watch = await client.post(
            "/watchlist/add/recompete",
            data={
                "award_key": award_key,
                "title": seed["recipient"] or f"Signoff {tag}",
                "agency": seed.get("agency") or "",
                "naics_code": naics,
                "end_date": seed.get("end_date") or "",
                "obligation": str(seed["obligation"]) if seed.get("obligation") is not None else "",
                "months_to_end": str(seed.get("months_to_end") or ""),
            },
            headers={"HX-Request": "true"},
        )
        assert watch.status_code == 200
        assert "Watching" in watch.text or award_key in watch.text
        items = load_watchlist(settings)
        assert any(i.award_key == award_key for i in items), (
            f"watchlist.json missing {award_key!r} — items={[i.award_key for i in items]}"
        )

        pulse = await client.get("/pulse")
        assert pulse.status_code == 200
        assert award_key in pulse.text or (seed["recipient"] or "")[:20] in pulse.text

        track = await client.post(
            "/signals/track",
            data={
                "award_key": award_key,
                "title": seed["recipient"] or f"Signoff {tag}",
                "agency": seed.get("agency") or "",
                "naics_code": naics,
            },
            headers={"HX-Request": "true"},
        )
        assert track.status_code == 200
        redirect = track.headers.get("HX-Redirect") or track.headers.get("location") or ""
        assert "/capture/" in redirect
        opp_id = _capture_id_from_redirect(redirect)

        track_again = await client.post(
            "/signals/track",
            data={
                "award_key": award_key,
                "title": seed["recipient"] or f"Signoff {tag}",
                "agency": seed.get("agency") or "",
                "naics_code": naics,
            },
            headers={"HX-Request": "true"},
        )
        assert track_again.status_code == 200
        assert (track_again.headers.get("HX-Redirect") or "") == redirect

        fill = await client.post(
            f"/opportunities/{opp_id}/packet/prime_name/fill",
            data={"source": PG_INTEL},
            headers={"HX-Request": "true"},
        )
        assert fill.status_code == 200, fill.text[:800]

        packet = await client.get(f"/api/opportunities/{opp_id}/packet")
        assert packet.status_code == 200
        fields = packet.json().get("fields") or []
        prime = next((f for f in fields if f.get("field_key") == "prime_name"), None)
        assert prime is not None
        value = (prime.get("value") or "").strip()
        assert value, "prime_name should be filled from PG intel"
        if seed.get("recipient"):
            assert seed["recipient"][:10].upper() in value.upper()

    reload_settings()