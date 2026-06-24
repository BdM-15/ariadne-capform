#!/usr/bin/env python
"""Phase 17e-e — MVP sign-off smoke against live Thread server + PG intel.

Path: Overview slice → Recompete → Watch → Pulse → Track → packet fill (pg_intel).

Usage:
  python app.py   # in another terminal
  python backend/scripts/smoke_insights_signoff.py
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from thread.config import get_settings
from thread.db.session import SessionLocal
from thread.domain.packet_answer_sources import PG_INTEL
from thread.services.insights_signoff import discover_expiring_award
from thread.services.watchlist import load_watchlist

BASE = "http://127.0.0.1:9622"
TIMEOUT = 180.0


def _capture_id(redirect: str) -> str:
    match = re.search(r"/capture/([0-9a-f-]{36})", redirect)
    if not match:
        raise ValueError(f"No capture id in redirect: {redirect!r}")
    return match.group(1)


async def _discover_seed() -> dict | None:
    async with SessionLocal() as session:
        return await discover_expiring_award(session)


def main() -> int:
    fails = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal fails
        status = "PASS" if ok else "FAIL"
        print(f"{status}: {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            fails += 1

    seed = asyncio.run(_discover_seed())
    if not seed:
        check("PG expiring seed", False, "no row in 18mo window — run intel migration")
        return 1

    naics = seed["naics_code"]
    award_key = seed["award_key"]
    check(
        "PG expiring seed",
        True,
        f"NAICS {naics} · {award_key[:20]}… · {seed.get('recipient', '')[:32]}",
    )

    client = httpx.Client(base_url=BASE, timeout=TIMEOUT, follow_redirects=False)

    try:
        health = client.get("/api/health")
        check("GET /api/health", health.status_code == 200)
    except httpx.HTTPError as exc:
        check("GET /api/health", False, str(exc))
        return 1

    try:
        r = client.get(
            "/partials/insights/slice",
            params={"run": 1, "lens": "overview", "naics_codes": naics},
        )
        ok = (
            r.status_code == 200
            and "insights-slice-panel" in r.text
            and (
                "insights-echarts-hero" in r.text
                or "insights-metric-cards" in r.text
                or "Capture intensity" in r.text
            )
        )
        check("Overview slice", ok)
    except httpx.HTTPError as exc:
        check("Overview slice", False, str(exc))

    try:
        r = client.get(
            "/partials/insights/slice",
            params={"run": 1, "lens": "recompete", "naics_codes": naics},
        )
        ok = r.status_code == 200 and (
            award_key in r.text or (seed.get("recipient") or "")[:12] in r.text
        )
        check("Recompete lens", ok, f"{len(r.text)} bytes")
    except httpx.HTTPError as exc:
        check("Recompete lens", False, str(exc))

    try:
        r = client.post(
            "/watchlist/add/recompete",
            data={
                "award_key": award_key,
                "title": seed.get("recipient") or "Signoff smoke",
                "agency": seed.get("agency") or "",
                "naics_code": naics,
                "end_date": seed.get("end_date") or "",
                "obligation": str(seed["obligation"]) if seed.get("obligation") is not None else "",
                "months_to_end": str(seed.get("months_to_end") or ""),
            },
            headers={"HX-Request": "true"},
        )
        settings = get_settings()
        items = load_watchlist(settings)
        ok = r.status_code == 200 and any(i.award_key == award_key for i in items)
        check("Watch → watchlist.json", ok)
    except httpx.HTTPError as exc:
        check("Watch → watchlist.json", False, str(exc))

    try:
        r = client.get("/pulse")
        ok = r.status_code == 200 and (
            award_key in r.text or (seed.get("recipient") or "")[:16] in r.text
        )
        check("Pulse watchlist", ok)
    except httpx.HTTPError as exc:
        check("Pulse watchlist", False, str(exc))

    opp_id = ""
    try:
        r = client.post(
            "/signals/track",
            data={
                "award_key": award_key,
                "title": seed.get("recipient") or "Signoff smoke",
                "agency": seed.get("agency") or "",
                "naics_code": naics,
            },
            headers={"HX-Request": "true"},
        )
        redirect = r.headers.get("HX-Redirect") or r.headers.get("Location") or ""
        ok = r.status_code == 200 and "/capture/" in redirect
        if ok:
            opp_id = _capture_id(redirect)
        check("Track → capture workspace", ok, redirect or "no redirect")
    except httpx.HTTPError as exc:
        check("Track → capture workspace", False, str(exc))

    if opp_id:
        try:
            r = client.post(
                f"/opportunities/{opp_id}/packet/prime_name/fill",
                data={"source": PG_INTEL},
                headers={"HX-Request": "true"},
            )
            ok = r.status_code == 200
            check("Packet fill prime_name (pg_intel)", ok)
        except httpx.HTTPError as exc:
            check("Packet fill prime_name (pg_intel)", False, str(exc))

        try:
            r = client.get(f"/api/opportunities/{opp_id}/packet")
            if r.status_code == 200:
                fields = r.json().get("fields") or []
                prime = next((f for f in fields if f.get("field_key") == "prime_name"), {})
                value = (prime.get("value") or "").strip()
                recip = (seed.get("recipient") or "")[:10].upper()
                ok = bool(value) and (not recip or recip in value.upper())
                check("Verify prime_name value", ok, value[:60] if value else "empty")
            else:
                check("Verify prime_name value", False, f"HTTP {r.status_code}")
        except httpx.HTTPError as exc:
            check("Verify prime_name value", False, str(exc))

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())