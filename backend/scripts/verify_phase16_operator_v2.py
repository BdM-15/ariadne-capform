#!/usr/bin/env python3
"""Operator experience proof — Phase 16 against live :9622."""

from __future__ import annotations

import re
import sys
import uuid

import httpx

BASE = "http://127.0.0.1:9622"


def main() -> int:
    tag = uuid.uuid4().hex[:8]
    results: list[tuple[str, bool, str]] = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        results.append((name, cond, detail))
        print(f"{'PASS' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))

    with httpx.Client(base_url=BASE, timeout=120.0) as client:
        # A — knowledge stays off Tasks lane
        k = client.post(
            "/partials/capture/quick",
            data={"dump": f"edge computing sensor stack {tag} — add to company capability knowledge"},
        )
        kicker = "Added to Tasks" not in k.text
        ok("A1 knowledge not Tasks", kicker, k.text[k.text.find("Added to") : k.text.find("Added to") + 48] if "Added to" in k.text else "no success")
        ok("A2 knowledge inbox branch", "Inbox" in k.text)
        ok("A3 knowledge inbox CTA", "Vault Inbox" in k.text or "knowledge-vault-inbox" in k.text)

        # B — meeting → Tasks
        m = client.post(
            "/partials/capture/quick",
            data={"dump": "schedule meeting LIS SECREP prep with Molly B and Teresa Deming"},
        )
        ok("B1 meeting Tasks branch", "Added to Tasks" in m.text)
        ok("B2 meeting not vault inbox", "Added to Vault Inbox" not in m.text and "Added to Test Inbox" not in m.text)
        ok("B3 Open Tasks CTA", "Open Tasks" in m.text and "/tasks" in m.text)
        title_m = re.search(r'capture-fab-flash-title">([^<]+)', m.text)
        ok("B4 polished title", bool(title_m and len(title_m.group(1)) > 10), title_m.group(1) if title_m else "")

        # C — /tasks GTD board surface
        t = client.get("/tasks")
        ok("C1 tasks page 200", t.status_code == 200)
        ok("C2 GTD board", "tasks-board-scroll" in t.text or "tasks-lane" in t.text)
        ok("C3 accomplish actions", "task-card-actions" in t.text)
        ok("C4 filter tabs", all(x in t.text for x in ("Open", "Today", "Overdue", "Done")))
        ok("C5 view toggle", "tasks-segment" in t.text)
        status_m = re.search(r'/partials/tasks/([0-9a-f-]{36})/status', t.text)
        complete_m = re.search(r'/partials/tasks/([0-9a-f-]{36})/complete', t.text)
        task_id = status_m.group(1) if status_m else (complete_m.group(1) if complete_m else None)

        # D — status transition HTMX
        if task_id:
            done = client.post(
                f"/partials/tasks/{task_id}/status",
                data={"status": "done", "filter": "open", "view": "board"},
            )
            ok("D1 status POST 200", done.status_code == 200)
            ok("D2 tasks-body refresh", "tasks-body" in done.text or "task-card" in done.text)
            ok("D3 complete action label", "Complete" in t.text or "Complete" in done.text)
        else:
            ok("D1 status POST 200", False, "no task id")
            ok("D2 tasks-body refresh", False, "skipped")
            ok("D3 complete action label", False, "skipped")

        # E — Command Center widget
        dash = client.get("/")
        ok("E1 dashboard 200", dash.status_code == 200)
        ok("E2 open-tasks widget", "cc-widget-open-tasks" in dash.text)
        count_m = re.search(r"(\d+) open", dash.text)
        ok("E3 open count visible", count_m is not None, count_m.group(0) if count_m else "")

        # F — opp chip from pursuit context
        opp = client.post(
            "/api/opportunities",
            json={"name": f"Opp Chip {tag}", "lifecycle_state": "pursuing"},
        )
        oid = opp.json().get("id", "")
        client.post(
            "/partials/capture/quick",
            data={
                "dump": "schedule call with PM about gate deck",
                "opp_id": oid,
                "opp_name": f"Opp Chip {tag}",
            },
        )
        tasks = client.get("/tasks")
        ok("F1 opp name on /tasks", f"Opp Chip {tag}" in tasks.text)
        ok("F2 /capture/{id} chip", f"/capture/{oid}" in tasks.text)

        # G — sidebar nav
        ok("G1 sidebar Tasks link", 'href="/tasks"' in tasks.text and "list-todo" in tasks.text)

        # H — task drawer + notes (16g)
        ok("H1 drawer shell", "task-drawer-root" in tasks.text)
        drawer_id = status_m.group(1) if status_m else (complete_m.group(1) if complete_m else None)
        if drawer_id:
            drawer = client.get(f"/partials/tasks/{drawer_id}/drawer")
            ok("H2 drawer panel 200", drawer.status_code == 200)
            ok("H3 work notes UI", "Work notes" in drawer.text)
            noted = client.post(
                f"/partials/tasks/{drawer_id}/notes",
                data={"body": f"operator proof note {tag}", "filter": "open", "view": "board"},
            )
            ok("H4 note append 200", noted.status_code == 200)
            ok("H5 note in drawer", f"operator proof note {tag}" in noted.text)
            deep = client.get(f"/tasks?task={drawer_id}")
            ok("H6 deep link", f'openTaskDrawer("{drawer_id}")' in deep.text)
        else:
            ok("H2 drawer panel 200", False, "no task id")
            ok("H3 work notes UI", False, "skipped")
            ok("H4 note append 200", False, "skipped")
            ok("H5 note in drawer", False, "skipped")
            ok("H6 deep link", False, "skipped")

    passed = sum(1 for _, p, _ in results if p)
    total = len(results)
    print(f"\n=== Operator proof: {passed}/{total} ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())