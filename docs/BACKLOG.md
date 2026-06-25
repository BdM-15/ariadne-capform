# Ariadne's Thread — Backlog & Idea Inbox

> Companion to [`PLAN.md`](PLAN.md) (the MVP path). **Nothing here is lost — it is parked.**
> Full historical detail (every completed slice, inspiration essay, DR parity table, data audit)
> lives verbatim in [`PLAN-archive-v4.md`](PLAN-archive-v4.md). This file is the **living triage list**:
> capture ideas fast on top, promote the right ones into `PLAN.md` when an MVP milestone needs them.

**How to use this file**

1. **Capture** any new idea as a one-line bullet under **Idea Inbox** — no decisions, no formatting tax.
2. **Triage** later: move it into a parked section below, or promote it into a `PLAN.md` milestone.
3. **Promote** only when a milestone genuinely needs it — keep MVP focus.

**Triage legend:** `[inbox]` raw · `[parked]` triaged, post-MVP · `[promote?]` candidate for next milestone · `[ref]` reference only

---

## 🧺 Idea Inbox (capture fast, triage later)

- `[parked]` **huashu** integration — graphic/presentation/media generator as a packet & Studio fill path (graphics route_kind; campaign decks, money-flow visuals). Promote into **M3 — Win lane** when Studio scaffolds.
- `[parked]` **ponytail pass** — apply [ponytail](https://github.com/DietrichGebert/ponytail) simplicity philosophy ("why write 50 lines when one will do") to `ui/routes.py` (3,313 lines) and the `intel/charts.py` + `echarts_options.py` viz pair. See **Simplification backlog** below.

### Hermes / autonomous-operator vision (parked — post-MVP infra)

> **Full capability reference:** [`HERMES_INTEGRATION.md`](HERMES_INTEGRATION.md) — every Hermes feature
> (memory, self-improving skills, Curator, cron, Persistent Goals/Ralph loop, subagent delegation, Kanban,
> code execution, gateway, checkpoints, trajectory/RL) mapped to Ariadne doctrine, with a Gate-0 phased
> adoption path (H1–H9) and corrections to the earlier Grok plan. MIT-licensed.
>
> **Verdict (2026-06-24):** Do **not** build during MVP — adds a second agent runtime + memory store + deployment target that cut against _one-command-to-run_, _two-store knowledge_, and _deferred orchestration_. Capture the salvageable ideas; revisit only after the find→fill→artifact loop has real depth (PLAN M1–M3). Reviewed against [PLAN.md](PLAN.md) doctrine; see chat 2026-06-24.

- `[parked]` **Overnight operator ("works while I sleep")** ⭐ north-star — an agent runs monitoring + retrieval chains + draft fills overnight and **stacks the morning review queue with candidates**. Doctrine guardrail: **autonomous _preparation_, human _ratification_** — never auto-promote/send/commit (#2 review-gated). Natural end-state of **named retrieval chains + 17j** + route-first orchestration; build _after_ loop depth, not as new infra.
- `[parked]` **Self-improving skills & process (Hermes signature)** ⭐ — agent **authors and refines skills** (extends `skill-creator`), proposes **workflow/process improvements**, and tunes fill-route recipes as it learns the operator's patterns. Guardrail: skills are **git-versioned**; new/changed skills land as **candidates** → human review before they run on live capture (never silent self-modification).
- `[parked]` **Closed learning loop** ⭐ — approved packet/research/fill outcomes feed `training/examples/` (→ JSONL for local SLM fine-tune) and `learning-records/`, so retrieval, fill suggestions, and skill quality **compound on each pursuit**. Ties to existing **knowledge-compounding doctrine** + deferred _training-example curation_; the agent gets measurably better over time on _your_ markets (e.g. KBR R&S / facility-services lanes).
- `[parked]` **Telegram mobile intake** — `ariadnesthreadhermesbot` (text/voice) as another door into the existing **capture FAB + `capture_intent.py`** review-gated pipeline → Postgres/vault candidate. Post-MVP ingress; no new memory system.
- `[parked]` **Always-on SAM watches / "Keep It Sold" monitoring** — overlaps **Phase 17j** (forward-pipeline orchestration, already parked). Fold into 17j, not a separate system.
- `[ref]` **Hermes as optional LLM provider** — `llm/router.py` is already extensible; an OpenAI-compatible endpoint is a ~10-line add _if_ ever wanted. Note only; do not build. (Source plan misreads repo paths — `backend/utils/llm_router.py`/`frontend/` HTMX are wrong; real paths are `backend/src/thread/llm/router.py` and `backend/src/thread/ui/`.)
- _(add new ideas here — one line each)_

---

## Parked features by lane (post-MVP — kept, sequenced after MVP)

> Each entry notes the original phase/slice ID so continuity with `PLAN-archive-v4.md` is preserved.

### Identify — deeper than MVP needs

- `[parked]` **17j — SAM forward-pipeline orchestration** (17j-a monitor recommender · 17j-b Explain→task/export · 17j-c Live SAM lens depth/notice-type filters · 17j-d unified pursuit clock · 17j-e SAM+PG fusion for net-new buyers). Closes the loop from "recompete pipe is thin" → recommended SAM monitors → Watch → Track.
- `[parked]` **17b-interact** — DataRepublican browse-style Sankey: click node → narrow facet → re-run; focus/remove node; progressive disclosure.
- `[parked]` **17c — semantic facet search** — `pgvector` on USAspending labels + SAM snapshots + vault entities + MinerU chunks; semantic facet autocomplete ("Army CIO" → real PG label); hybrid retrieval.
- `[parked]` **17c-graph** — BFS expose-style force/graph canvas; `intel_relationships` + `edges.jsonl`; people/relations overlay (17e-g-e parent-vehicle peers folds in here).
- `[parked]` **17d / 17d-agency** — SAM [Federal Hierarchy Public API](https://open.gsa.gov/api/fh-public-api/) → `intel_federal_orgs` PG; cascading dept→sub→office pickers; distinct-value facet autocomplete (quick win before semantic search).
- `[parked]` **17k-office-trace** (17k-a FH resolve tool · 17k-b intensity→agency trace · 17k-c web-enrich fallback · 17k-d office BFS expose) — awarding-office → funding-office customer map.
- `[parked]` **17e-h — profile exports** — schema registry (17e-h-a) + vault promote (17e-h-b) + docx (17e-h-c) + pptx (17e-h-d) + opportunity profile reuse (17e-h-e). _Note: huashu may cover the pptx/graphics path — reconcile during M3._
- `[ref]` **Geo / POP state map**, **parent vehicle peer roster** — post-MVP visual inventory items.

### Capture — beyond MVP fill mapping

- `[parked]` **20c-b** — bootstrap generates `foundation/packet-routing-matrix.md`; refresh `data-elements/` frontmatter; vault lint catalog↔wiki `field_key` sync.
- `[parked]` **20c-c** — optional Grok "why these next" advisor on top 3–5 open gaps (reads vault prose + packet context).
- `[parked]` **20c-d** — sibling routing matrices for `RISK_REGISTER` + `CALL_PLAN` dictionaries.
- `[parked]` **19e** — MinerU solicitation → `ExtractionBundle` candidate fields.
- `[parked]` **Full 141-field fill perfection** — MVP bar is "every MS1-critical field has a working route; others routed but not all perfected." Perfecting all 141 is post-MVP.

### Knowledge / vault — compounding runtime

- `[parked]` **17b-vault** — Clew trusted → Karpathy wiki ingest (vault browser ✅; write-ingest path TBD).
- `[parked]` **Phase 21 Incubator 21b–21d** — Develop (ingest plan JSON) · context packer · Publish executes plan → trusted pages. (21a seed/hold ✅.)
- `[parked]` **16e** — completed task → vault checklist candidate (review-gated).
- `[parked]` **Deferred knowledge runtime** — bid/no-bid fit service · UEI / past-performance crosswalk · training-example curation (`training/examples/` → JSONL for local SLM) · Thread-native research artifacts store.

### Operator mastery & docs

- `[parked]` **Phase 22 — Education lane** (22a reference HTML + glossary · 22b curriculum lessons · 22b-2 Lesson 02 · 22d learning records → guide depth · 22e-2 multi-turn sessions · 22e-3 session notes + DOX context). Tiers 1–2 (tooltips, guide modals) ship with MVP; deep curriculum is post-MVP.
- `[parked]` **DOX** — sparse `AGENTS.md` tree ([agent0ai/dox](https://github.com/agent0ai/dox)) for backend/docs; feeds 22e-3 + Grok Build. One agent session after MVP sign-off.

### Data / intel ETL

- `[parked]` **23b** — intel dedup matview (`DISTINCT ON …`) for Clew aggregates; extra analytics view rules; `pg_trgm` GIN for leading-wildcard agency ILIKE; analytics matviews. (23a SQL analytics views ✅.)
- `[ref]` **Intel data posture audit** (raw-load vs Data_Insights cleansing; 25,849 dup txn keys; 2.8M deobligations; un-normalized `DEPT OF DEFENSE`) — full honest assessment in archive. Document negative obligations in `docs/usaspending/`; net-`SUM()` in queries.

### Orchestration / platform

- `[parked]` **LangGraph chain executor** — adopt only when skill chains need state/checkpointing (route-first + thin chains first).
- `[parked]` **Neo4j** import from `edges.jsonl`.
- `[parked]` **Theseus** on `:9621`-family (use Ariadne `:9622`+) — solicitation merge (activation Ph 4–6).
- `[parked]` **Semantic vault search** (OpenAI embeddings) — config stub exists.
- `[parked]` **Twenty `packet_field_catalog.py` cross-read** — one-time sanity check vs CRM object model.

---

## 🧹 Simplification backlog (ponytail doctrine)

> **Document now, refactor deliberately** (M5 + ongoing). Principle: _why write 50 lines when one will do._
> Constraint: do **not** over-split files under ~200 LOC; the risk here is **under**-organized routes, not modularization.

| Target                                         |           Now | Smell                                                                          | Direction                                                                                                                         |
| ---------------------------------------------- | ------------: | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| `ui/routes.py`                                 |     **3,313** | One-file monolith for every HTMX route                                         | Split by lane into `ui/routes/` package (identify, capture, knowledge, tasks, tools, command) — keep thin route → fat `services/` |
| `intel/charts.py` + `intel/echarts_options.py` | 1,605 + 1,374 | Chart SQL + ECharts option builders intertwined; duplicated option scaffolding | Extract shared ECharts option factory; one chart recipe per question; ponytail the repeated option dicts                          |
| `services/vault_write.py`                      |           998 | Candidate write + promote + frontmatter + index all in one                     | Consider splitting write vs promote vs index only if a clean seam exists (>200 LOC rule still applies)                            |
| `intel/graph_trace.py`                         |           848 | BFS + edge typing + formatting together                                        | Defer until 17c-graph; isolate edge-type registry                                                                                 |

**Ponytail review checklist (apply opportunistically during any edit):**

- Is there a one-liner / stdlib / existing helper that replaces this block?
- Are two near-duplicate functions begging to be one parametrized function?
- Does a route do domain work that belongs in `services/`?
- Can a hand-rolled loop become a comprehension / `itertools` / SQL aggregate?

---

## 📚 Reference & inspiration index (read-only)

> Full tables and essays preserved verbatim in [`PLAN-archive-v4.md`](PLAN-archive-v4.md). Index here for quick lookup.

| Topic                                                                                                        | Where                                                          | Use                                                                  |
| ------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------- | -------------------------------------------------------------------- |
| **Hermes Agent — full integration reference**                                                                | [`HERMES_INTEGRATION.md`](HERMES_INTEGRATION.md)               | Capability capture + Ariadne mapping + Gate-0 adoption path (parked) |
| Inspiration repos (ariadne-thread, capture-insights, proj-theseus, deer-flow, Odysseus, Superset, 1102 MCPs) | [`PLAN-archive-v4.md`](PLAN-archive-v4.md) "Inspiration repos" | Patterns only — no code dependency                                   |
| Rejected tooling (Appsmith, Twenty, Superset-as-primary, deer-flow harness)                                  | "Non-goals" + `EXTERNAL_TOOLING_ASSESSMENT.md`                 | Why each was rejected                                                |
| **DataRepublican** parity + method catalog + edge types                                                      | "DataRepublican inspiration"                                   | Follow-the-money methods → Clew/Insights; not a DR fork              |
| **GovDash** competitor mapping                                                                               | "GovDash inspiration"                                          | Adopt solo-operator patterns, skip team CRM                          |
| External skills research (idea-capturer, GTD, Zettelkasten)                                                  | "External skills research"                                     | Port `idea-capturer`; borrow GTD ideas only                          |
| Federal data composition + retrieval chains + cross-lane handoff                                             | "Federal data composition"                                     | Source roles, named chains, depart/return links                      |
| Intel data posture (raw vs production-grade)                                                                 | "Intel data posture"                                           | Honest load assessment + audit counts                                |
| LLM strategy, web-crawl providers, orchestration                                                             | respective sections                                            | Provider priority, routing, LangGraph flags                          |
| Full completed-slice checklists (12a–m, 14a–l, 15–15h, 16a–h, 17a–b.1, 20a–c-a, 22b–e)                       | "Plan todos" + phase sections                                  | Provenance of what's already built                                   |

---

_Last updated: 2026-06-24 — created during v5 reorg. Keep entries short; promote to `PLAN.md` when a milestone needs them._
