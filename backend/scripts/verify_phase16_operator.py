#!/usr/bin/env python3
"""Live operator verification — Phase 16a-d against running app (:9622)."""

from __future__ import annotations

import re
import sys
import uuid
from dataclasses import dataclass

import httpx

BASE = "http://127.0.0.1:9622"
TIMEOUT = 60.0


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str


def _check(name: str, cond: bool, detail: str) -> StepResult:
    return StepResult(name, cond, detail)


def main() -> int:
    tag = uuid.uuid4().hex[:8]
    results: list[StepResult] = []

    with httpx.Client(base_url=BASE, timeout=TIMEOUT) as client:
        # 0 — app up
        health = client.get("/api/health")
        results.append(
            _check(
                "health",
                health.status_code == 200 and health.json().get("postgres_ready"),
                f"status={health.status_code} pg={health.json().get('postgres_ready')}",
            )
        )

        # 1 — knowledge dump → Vault Inbox (not Tasks)
        knowledge_dump = (
            f"edge computing capability note {tag} — Jason Gray mentioned new sensor stack for company knowledge"
        )
        k_res = client.post("/partials/capture/quick", data={"dump": knowledge_dump})
        k_html = k_res.text
        results.append(_check("knowledge_fab_200", k_res.status_code == 200, f"status={k_res.status_code}"))
        results.append(
            _check(
                "knowledge_routes_vault",
                "Added to Vault Inbox" in k_html and "Added to Tasks" not in k_html,
                "Vault Inbox success branch",
            )
        )
        results.append(
            _check(
                "knowledge_has_inbox_link",
                "knowledge-vault-inbox" in k_html or "Open in Vault Inbox" in k_html,
                "studio/inbox link present",
            )
        )

        # 2 — meeting dump → Tasks
        meeting_dump = (
            f"schedule a meeting for LIS SECREP transition prep {tag} with Molly B and Teresa Deming"
        )
        m_res = client.post("/partials/capture/quick", data={"dump": meeting_dump})
        m_html = m_res.text
        results.append(_check("meeting_fab_200", m_res.status_code == 200, f"status={m_res.status_code}"))
        results.append(
            _check(
                "meeting_routes_tasks",
                "Added to Tasks" in m_html and "Added to Vault Inbox" not in m_html,
                "Tasks success branch",
            )
        )
        results.append(
            _check("meeting_open_tasks_link", "/tasks" in m_html and "Open Tasks" in m_html, "CTA to /tasks")
        )
        title_match = re.search(r'class="capture-fab-flash-title">([^<]+)<', m_html)
        polished_title = title_match.group(1).strip() if title_match else ""
        results.append(
            _check(
                "meeting_polished_title",
                bool(polished_title) and tag not in polished_title.lower() and "schedule" in polished_title.lower(),
                f"title={polished_title!r}",
            )
        )

        # 3 — /tasks lists meeting task + checkoff
        t_res = client.get("/tasks")
        t_html = t_res.text
        results.append(_check("tasks_page_200", t_res.status_code == 200, f"status={t_res.status_code}"))
        results.append(
            _check(
                "tasks_shows_meeting",
                polished_title in t_html or "Schedule" in t_html or "Meeting" in t_html,
                "meeting visible on /tasks",
            )
        )
        results.append(_check("tasks_has_filters", "Overdue" in t_html and "Today" in t_html, "filter tabs"))
        checkoff = re.search(r'hx-post="/partials/tasks/([0-9a-f-]{36})/complete"', t_html)
        results.append(
            _check(
                "tasks_checkoff_form",
                checkoff is not None,
                f"task_id={checkoff.group(1) if checkoff else 'missing'}",
            )
        )

        # 4 — opp-linked task via API + FAB context
        opp_name = f"Verify Opp {tag}"
        opp_res = client.post(
            "/api/opportunities",
            json={"name": opp_name, "lifecycle_state": "pursuing"},
        )
        opp_id = opp_res.json().get("id") if opp_res.status_code == 200 else ""
        opp_fab = client.post(
            "/partials/capture/quick",
            data={
                "dump": f"schedule prep call for gate review {tag}",
                "opp_id": opp_id,
                "opp_name": opp_name,
            },
        )
        tasks_opp = client.get("/tasks")
        results.append(_check("opp_create", opp_res.status_code == 200 and bool(opp_id), f"opp_id={opp_id}"))
        results.append(
            _check(
                "opp_chip_on_tasks",
                opp_name in tasks_opp.text and f"/capture/{opp_id}" in tasks_opp.text,
                "pursuit chip links workspace",
            )
        )

        # 5 — Command Center widget
        dash = client.get("/")
        d_html = dash.text
        results.append(_check("dashboard_200", dash.status_code == 200, f"status={dash.status_code}"))
        results.append(
            _check(
                "dashboard_open_tasks_widget",
                "cc-widget-open-tasks" in d_html and "open" in d_html.lower(),
                "widget mounted",
            )
        )
        results.append(
            _check(
                "dashboard_widget_links_tasks",
                "/tasks" in d_html,
                "widget deep-link",
            )
        )

        # 6 — checkoff HTMX partial (operator tick)
        if checkoff:
            task_id = checkoff.group(1)
            done_res = client.post(f"/partials/tasks/{task_id}/complete")
            done_html = done_res.text
            results.append(_check("checkoff_200", done_res.status_code == 200, f"status={done_res.status_code}"))
            results.append(
                _check(
                    "checkoff_shows_done",
                    "Done" in done_html,
                    "HTMX row swap to done state",
                )
            )
            # open count should still reflect other open tasks
            dash2 = client.get("/")
            results.append(
                _check(
                    "dashboard_after_checkoff",
                    "cc-widget-open-tasks" in dash2.text,
                    "widget still renders after checkoff",
                )
            )

        # 7 — sidebar Tasks nav
        tasks_nav = client.get("/tasks")
        results.append(
            _check(
                "sidebar_tasks_link",
                'href="/tasks"' in tasks_nav.text and "list-todo" in tasks_nav.text,
                "Tasks in Command nav",
            )
        )

    passed = sum(1 for r in results if r.ok)
    total = len(results)
    print(f"\n=== Phase 16 operator verification ({passed}/{total}) ===\n")
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        print(f"  [{mark}] {r.name}: {r.detail}")

    if passed < total:
        print("\nSome operator flows failed — see above.")
        return 1
    print("\nAll operator flows verified against live app.")
    return 0


if __name__ == "__main__":
    sys.exit(main())