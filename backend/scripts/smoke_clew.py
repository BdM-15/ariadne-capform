#!/usr/bin/env python
"""Quick Clew smoke against live Thread server + PG intel."""

from __future__ import annotations

import sys

import httpx

BASE = "http://127.0.0.1:9622"
TIMEOUT = 120.0


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=TIMEOUT)
    fails = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal fails
        status = "PASS" if ok else "FAIL"
        print(f"{status}: {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            fails += 1

    try:
        r = client.get("/clew")
        check("GET /clew", r.status_code == 200 and "clew-body" in r.text)
    except httpx.HTTPError as exc:
        check("GET /clew", False, str(exc))
        return 1

    modes = [
        ("money_flow", {"recipient": "Lockheed", "mode": "money_flow", "run": 1}),
        ("spend_trend", {"recipient": "Boeing", "mode": "spend_trend", "run": 1}),
        ("recipient_landscape", {"naics_codes": "541512", "mode": "recipient_landscape", "run": 1}),
        ("teaming", {"recipient": "Lockheed", "mode": "teaming", "run": 1}),
    ]

    for label, params in modes:
        try:
            r = client.get("/partials/clew/results", params=params)
            html = r.text
            has_chart = "clew-echarts-host" in html
            has_warn = "insights-explore-msg-warn" in html or "error" in html.lower()
            if label == "teaming":
                ok = r.status_code == 200 and has_warn and "subaward" in html.lower()
                check(f"Clew {label}", ok, "expected subaward pending message")
            else:
                ok = r.status_code == 200 and has_chart and not (
                    "Prime awards table missing" in html
                )
                snippet = ""
                if "summary" in html:
                    i = html.find("summary")
                    snippet = html[i : i + 80].replace("\n", " ")
                check(f"Clew {label}", ok, snippet or ("chart" if has_chart else "no chart"))
        except httpx.HTTPError as exc:
            check(f"Clew {label}", False, str(exc))

    # POST analyze path (HTMX form)
    try:
        r = client.post(
            "/clew/analyze",
            data={
                "recipient": "Northrop",
                "mode": "money_flow",
            },
        )
        check(
            "POST /clew/analyze",
            r.status_code == 200 and "clew-echarts-host" in r.text,
        )
    except httpx.HTTPError as exc:
        check("POST /clew/analyze", False, str(exc))

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())