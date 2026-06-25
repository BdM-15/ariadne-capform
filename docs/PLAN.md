# Ariadne's Thread — MVP Plan (v5)

> **Ariadne's Thread** (short: **Thread**) — solo-operator opportunity command center in `ariadne-capform`.
> Single `python app.py` · PostgreSQL-only · Grok/xAI primary reasoning · review-gated everywhere · Theseus ink/neon skin.
>
> **This file is the MVP path.** Parked features, inspiration, and history live in
> [`BACKLOG.md`](BACKLOG.md) and [`PLAN-archive-v4.md`](PLAN-archive-v4.md). Nothing was deleted in the v5 reorg — only re-sequenced.

**Last updated:** 2026-06-24 — M0 complete: indexes verified, E2E sign-off passes, test suite stabilized (19 → 3 residual infra failures).

---

## 🎯 North star — the MVP sign-off test

> **Can a solo operator find a pursuit, watch it, track it, open a packet, fill fields from intel,
> and produce supporting artifacts — without fighting the UI or waiting on unfinished plumbing?**

This is **not** thin plumbing. The operator's job is to **identify → capture → win**, so MVP means the
full loop has **real functional depth**: Data Insights deep enough to actually decide; the Living Briefing
Packet with every MS-critical data element mapped to a working fill path; Skills/AI doing real work; Clew
tracing money and relationships; a genuinely useful Command Center and Tasks lane; and a Studio that turns
intel + packet into pWin artifacts (decks, money-flow graphics) — **from the identify stage onward**.

### Why v5 exists (the honest reset)

Earlier plans marked plumbing **✅** and **deferred the substance** (entity depth, packet fill mapping,
skill wiring, Studio). That made MVP _look_ near while the operator still couldn't do the job. v5 fixes the
definition of "done" and re-pulls the wrongly-deferred substance back onto the critical path.

### The honesty rule (status has three states)

| State              | Means                                                                            |
| ------------------ | -------------------------------------------------------------------------------- |
| ✅ **Done**        | The operator can complete this job **without fighting the UI or hitting a stub** |
| 🟡 **Scaffolded**  | Wired / partially built but **shallow** — counts as **NOT MVP-done**             |
| ⬜ **Not started** | —                                                                                |

A track is only **✅** when it passes the sign-off bar for _its_ slice of the loop. "The route exists" is 🟡, not ✅.

---

## The three lanes (one record, real depth)

Thread helps you do three jobs end-to-end on **one opportunity record**. Studio/Win is **in MVP** —
artifacts support campaigns starting at identification (e.g. a money-flow trace deck to justify a pursuit).

| Lane             | Operator job                                     | MVP must deliver                                                                                                                                                            |
| ---------------- | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1 · Identify** | Find & qualify pursuits before investing capture | Deep Data Insights + decision-grade entity profiles + robust Clew tracing → Watch → Track                                                                                   |
| **2 · Capture**  | MS-gated strategy, intel, gate decisions         | Living Briefing Packet with **every MS1-critical field mapped to a working fill path** (deterministic MCP/tools + non-deterministic web research / prose skills / graphics) |
| **3 · Win**      | pWin artifacts & presentation material           | Studio produces eval map, win themes, outline, compliance shred, **money-flow/trace graphics, huashu decks** — usable from identify onward                                  |

Review gate sits across all three: every AI/skill/research/MCP output lands as `candidate` until approved.

---

## Non-negotiables (doctrine — condensed)

> Full doctrine essays (command & control, federal data composition, knowledge compounding,
> facet model, cross-lane handoff) are preserved in [`PLAN-archive-v4.md`](PLAN-archive-v4.md).

1. **Cloud-primary reasoning, self-hosted data** — Grok/xAI for capture/proposal/synthesis; Ollama admin offload only. Truth in PostgreSQL + Obsidian vault.
2. **Review-gated everywhere** — Intake → Candidate → Trusted; nothing auto-promotes.
3. **Full provenance** — evidence links, citations, MCP refs, URLs, `award_key` lineage.
4. **Living Briefing Packet** — slide-deck-shaped MS artifact; data elements from the dictionary; `route_kind` drives fill; living across MS gates.
5. **Two-store knowledge that compounds** — vault (synthesis) vs PostgreSQL (execution truth); use → knowledge → better fill next pursuit.
6. **PostgreSQL only** — single DB for workflow AND intel.
7. **Server-owned truth** — domain rules live in Python `services/`, never the client. Routes thin → services fat → models dumb.
8. **One command to run** — `python app.py` from root `.venv`. Ports: API **9622** · Studio 9623 · Postgres 55432. **Never 9621** (reserved for Project Theseus).
9. **Web research enrichment** — bounded, approval-gated; free/local providers first (SearXNG/Crawl4AI).
10. **Command & control ≠ metrics dump** — `/` is visibility + ≤2-click action; deep analytics live on `/insights`.
11. **No default search dimension** — NAICS, agency, sub-agency, recipient, PSC are **peer facets**; zero platform-shipped presets. Exception: operator's own ~10-code NAICS portfolio (explicit config).
12. **Theseus visual language** — ink/neon skin is presentation only; never conflate skin with plumbing.

---

## 🎨 Design principles — alive, not sterile

Ariadne must be **fun to use**, not boring like commercial GovCon tools. These are acceptance criteria, not vibes:

1. **Ink/neon richness everywhere** — Theseus skin on every surface; no flat corporate gray.
2. **Data storytelling** — every chart answers one question or enables a hone; **no metric dumps**.
3. **Snappy / instant** — cached slices, parallel queries, optimistic HTMX; the operator never waits on a spinner to think.
4. **Delightful microinteractions** — transitions, hovers, gate-pill animations; the UI feels responsive and alive.
5. **AI as a partner, not a form** — copilots draft, summarize, chain lookups; the operator approves via the gate — never a wall of empty fields.
6. **Command-first** — act in **≤2 clicks**, keyboard-friendly; no action buried behind chat-only UX.

> **Widget/screen acceptance test:** Can the operator _act_ (review, track, open opp, run research, open lens, fill a field) in ≤2 clicks without reading a paragraph? If not, it doesn't ship.

---

## 📊 MVP readiness scorecard (honest)

| Track                       | Job in the loop          | State | What "done" requires (MVP bar)                                                                                                                    |
| --------------------------- | ------------------------ | :---: | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Data Insights**           | Find & decide            |  🟡   | Overview + entity drill exist but shallow. Need decision-grade storytelling charts + derived metrics + Explain that genuinely supports a go/no-go |
| **Entity profiles**         | Decide on a pursuit      |  🟡   | Agency/Competitor dossiers: heat maps, Sankeys, adjacent competitors, recompete timing, certs — **decision-grade**, not lite                      |
| **Clew**                    | Trace money & relations  |  🟡   | Static Sankeys today. Need interactive expand (browse-style), trace handoff, money-flow output that feeds Studio artifacts                        |
| **Living Packet**           | Capture / fill           |  🟡   | Slide UX + 141-field catalog ✅; **every MS1-critical field mapped to a working fill route** (deterministic + non-deterministic + graphics)       |
| **Skills / AI wiring**      | Do the work              |  🟡   | Skill grid + run UX ✅; wire skills/MCP/Grok as **real packet-fill & research executors**, not a gallery                                          |
| **Command & Control (`/`)** | Daily cockpit            |  🟡   | Widgets exist but thin; make every region a genuine ≤2-click action surface with AI copilot strip                                                 |
| **Tasks**                   | Executive-assistant lane |  🟡   | Page + board exist; finish drawer/work-notes/checklist/opp-link/today-roadmap so admin truly offloads                                             |
| **Studio / Win**            | Produce artifacts        |  ⬜   | `/studio`: eval map, win themes, outline, compliance shred, money-flow/huashu decks — usable from identify onward                                 |
| **Foundation**              | Run it all               |  ✅   | `app.py`, PG, intel bulk load (64.2M prime), Alembic, vault, LLM router, research MVP, HTMX shell                                                 |

---

## 🧭 The build sequence (purpose-built path — don't get lost)

Build in operator-journey order so each milestone leaves a **working, deeper loop** and the finish line
stays visible. Design principles (fun-not-boring) apply **throughout**, not only at the end. Each milestone
references the original slice IDs so continuity with the archive is intact.

### M0 · Stabilize foundation _(close out in-flight)_

- **Status:** ✅ Complete (2026-06-24)
- Intel composite indexes verified valid on `intel_usaspending_prime_awards` (`naics_agency`, `naics_mod`, `naics_office`, `naics_pop_end`, `awarding_office`, plus base indexes).
- MVP funnel E2E (`test_insights_mvp_signoff_funnel`) passes.
- Test stabilization delivered: suite improved from 19 failures to 3 residual test-infrastructure failures.
- Residual notes (tracked in [BACKLOG.md](BACKLOG.md#test-isolation-debt-m0-findings-2026-06-24), not M0 blockers):
  1.  Windows asyncpg/TestClient loop flake (`test_task_drawer_partial_404`, order-dependent).
  2.  Shared operator Postgres pollution in one inbox-count assertion (`test_intel_inbox_excludes_vault_and_skill_creator`).
  3.  MinerU status-note test drift (`test_ingest_quick_capture_pdf_only`).
- **Exit met:** baseline find→fill→artifact loop runs clean (shallow but stable).

### M1 · Identify with real depth _(Data Insights · Entity profiles · Clew)_

- **17e-g-a/b** Decision-grade **Agency & Competitor profiles** — relationship heat maps, money-flow & teaming Sankeys, adjacent competitors, recompete timing, certs.
- **17e-g-c** Competition lens — set-aside, extent competed, pricing buckets, vehicle×pricing, FFP shaping radar.
- **17e-g-d** Trace lens inline (Sankeys + heat map on active slice); **2e-c** Overview visual polish (storytelling, not metric dump).
- **Clew robust** — interactive node expand (17b-interact-lite), trace handoff, money-flow output reusable as an artifact.
- **Exit:** operator runs a slice and can genuinely **decide what to pursue**, and export a trace/money-flow artifact.

**M1 progress:**

- ✅ **17e-g-a.1** (2026-06-24) — office Agency drill upgraded lite → decision-grade: unified into one parallel `_agency_profile` so awarding-office drill now returns money-flow Sankey, agency×recipient heat map, pricing mix, top agencies, and recompete shape-gate timing (was skipped for speed). Net −7 LOC; full agency profile now parallelized.
- ⬜ Next candidates: **17e-g-a (graph)** funding-office BFS/DR customer-trace graph · **17e-g-c** slice-wide FFP shaping radar (`ffp_shaping_radar` primitive exists, unwired) · **17e-g-b** competitor-profile depth audit.


### M2 · Capture with mapped fill paths _(Living Packet · Skills wiring)_

- **Map every MS1-critical data element → working fill route:** deterministic (USAspending PG, 1102/SAM MCP), non-deterministic (web research, Grok prose skills), and **graphics** (Clew money-flow, huashu).
- **Wire Skills as real executors** — `clew_intel`, `mcp_federal_tools`, research, vault skills run _from_ packet fields & data-needs strip, not just `/tools/skills`.
- **20c-a** ranked data-needs (✅) surfaced as guidance; **20d** MS-critical field execution + skill-wired chains.
- **Exit:** open a packet; every MS1-critical field fills via a working route; routine clears via tools, judgment stays human.

### M3 · Win lane _(Studio · artifacts · huashu)_

- **Phase 21 Studio** (`/studio`): eval ↔ win-theme map, outline, PTW, compliance shred candidates — review-gated artifacts for humans.
- **Artifact generators**: money-flow/trace graphics (from Clew) + **huashu** presentation/media; packet → deck export.
- Make artifacts reachable **from identify onward** (campaign support), not only late capture.
- **Exit:** operator produces a supporting artifact (deck / graphic / one-pager) from packet + intel.

### M4 · Operator cockpit _(Command & Control · Tasks — can partly parallel M1–M3)_

- **C&C `/`** — make each widget a genuine ≤2-click action surface; AI copilot quick-actions; attention over volume.
- **Tasks** — finish EA lane: board/list (16f), drawer + work notes (16g), checklist toggle (16h), opp-link chip (16d), today roadmap + C&C widget (16c).
- **Exit:** morning → C&C shows what needs attention; tasks captured & triaged frictionlessly.

### M5 · Delight & simplify pass _(fun-not-boring + ponytail)_

- Apply the 6 design principles across the whole loop (microinteractions, snappy, storytelling, copilot feel).
- **Ponytail refactor** — split `ui/routes.py` (3,313 LOC) into a `ui/routes/` package by lane; de-duplicate the `charts.py` + `echarts_options.py` viz pair (see [BACKLOG · Simplification](BACKLOG.md#-simplification-backlog-ponytail-doctrine)).
- **Exit:** loop feels **alive**, codebase is simpler, and the **MVP sign-off test passes for real**.

> **Parallelism:** M4 (cockpit) and design-principle polish can run alongside M1–M3. M1→M2→M3 is the hard dependency chain (can't fill a packet well until you can identify well; can't produce artifacts until packet + intel exist).

---

## 🧩 Architecture & ponytail (summary)

**Capability-first Python + Theseus-skinned command center.** Layers stay separate: Skin (`theseus.css`) ·
Shell (`ui/` HTMX + Jinja) · API (`api/`) · Domain (`domain/` + `services/`) · Capability
(`intel`, `llm`, `skills`, `mcp`, `research`, `bootstrap`). Routes thin → services fat → models dumb.
Every LLM/skill/MCP/research output → `candidate` + provenance → review gate.

**ponytail doctrine** (_why write 50 lines when one will do_): keep it simple, but **do not over-split files
under ~200 LOC** — `services/` is already granular. The real debt is the **under-organized monolith**
`ui/routes.py` (3,313 LOC). Document simplifications now; refactor deliberately in **M5**. Detailed targets
live in [BACKLOG · Simplification backlog](BACKLOG.md#-simplification-backlog-ponytail-doctrine).

---

## ✅ Foundation already solid (condensed)

| Area                                                                             | Status                          |
| -------------------------------------------------------------------------------- | ------------------------------- |
| `python app.py` launcher · PostgreSQL 16 (`:55432`) · Docker Compose             | ✅                              |
| Intel bulk load — 64.2M prime + 1.5M sub · base + NAICS/office composite indexes | ✅ (complete, verified valid)   |
| Alembic workflow migrations · vault bootstrap · reference corpus                 | ✅                              |
| LLM router (Grok primary, Ollama admin) · web research MVP (SearXNG/Crawl4AI)    | ✅                              |
| HTMX shell (Pulse, Insights, Filament/Capture, Knowledge, Review, Tools, Tasks)  | ✅ shell · 🟡 depth             |
| Skill runtime + 8 MCP manifests + `/tools/skills` & `/tools/mcp`                 | ✅ runtime · 🟡 wired-into-fill |
| Theseus skin synced; review gate; provenance kinds; 141-field packet catalog     | ✅                              |

> Full completed-slice provenance (12a–m, 14a–l, 15–15h, 16a–h, 17a–b.1, 20a–c-a, 22b–e) is preserved in
> [`PLAN-archive-v4.md`](PLAN-archive-v4.md).

---

## 🔑 Key surfaces & API (quick reference)

| Surface                 | Route                         | MVP role                                                                          |
| ----------------------- | ----------------------------- | --------------------------------------------------------------------------------- |
| Command Center          | `/`                           | Attention + ≤2-click actions (M4)                                                 |
| Portfolio Pulse         | `/pulse`                      | Morning briefing: watchlist + inbox + digest + pursuits                           |
| Data Insights           | `/insights`                   | Identification command surface — slice → Overview → entity profiles → lenses (M1) |
| Clew                    | `/clew`                       | Follow-the-money / relationship workbench (M1)                                    |
| Filament (Capture home) | `/capture`                    | Post-identify pursuits                                                            |
| Living Briefing Packet  | `/capture/{id}`               | Slide workspace + fill routes (M2)                                                |
| Tasks                   | `/tasks`                      | Executive-assistant lane (M4)                                                     |
| Knowledge vault         | `/knowledge`                  | Vault browser + review lane                                                       |
| Studio (Win)            | `/studio`                     | pWin artifacts (M3 — ⬜ new)                                                      |
| Tools                   | `/tools/mcp`, `/tools/skills` | MCP + skill catalogs (wire into fill, M2)                                         |

Core API (`/api/health`, `/portfolio/pulse`, `/opportunities`, `/…/packet`, `/review/*`, `/intel/*`,
`/knowledge/vault/*`) is live; `/api/research/*`, `/api/skills/*`, `/api/intel/mcp/*` are the M2 wiring gaps.

---

## 📌 Resume here

**North star:** pass the sign-off test _for real_ (find → watch → track → open packet → fill → artifact).

1. **M1** — Insights entity depth (17e-g-a/b), Competition & Trace lenses (17e-g-c/d), Clew interactivity, Overview polish (2e-c).
2. Then **M2 → M3**, with **M4** cockpit + fun-not-boring polish running alongside.

**M0 note:** completed and closed; residual test-infra debt is tracked in [BACKLOG.md](BACKLOG.md#test-isolation-debt-m0-findings-2026-06-24).

**Capture new ideas** in [`BACKLOG.md` → Idea Inbox](BACKLOG.md#-idea-inbox-capture-fast-triage-later) — one line, triage later, don't derail the milestone.

**Rules (anti–scope-creep):** one slice per PR · no new backend unless the UI needs it · pytest before commit ·
update this `PLAN.md` in the same commit when status/routes/sequence change · promote a backlog item into a
milestone only when that milestone needs it.
