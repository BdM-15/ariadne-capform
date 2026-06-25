# Hermes Agent — Ariadne Integration Reference

> **Status:** 🅿️ **Parked / post-MVP reference.** This is a _capability capture_, not an MVP commitment.
> Build the find→fill→artifact loop deep first (see [`PLAN.md`](PLAN.md) M0–M3). Hermes amplifies a deep,
> review-gated platform; pointed at a half-built one it just generates candidates for screens that can't act yet.
>
> **Purpose:** capture the **full power** of Hermes — mapped to Ariadne's doctrine — so nothing is missed when we
> implement. Companion to [`BACKLOG.md`](BACKLOG.md) (Hermes / autonomous-operator vision).
>
> **Source:** [hermes-agent.nousresearch.com/docs](https://hermes-agent.nousresearch.com/docs) ·
> [GitHub](https://github.com/NousResearch/hermes-agent) · **License: MIT** (permissive — safe to vendor/adapt,
> unlike AGPL inspiration repos) · reviewed 2026-06-24.

---

## 1. What Hermes is (in one paragraph)

Hermes Agent (Nous Research) is a **terminal-native, self-improving autonomous agent** with persistent memory,
agent-created skills, a 21+ platform messaging gateway, cron automation, subagent delegation, and an
OpenAI-compatible API server. It runs _anywhere_ (local, Docker, SSH, Daytona, Modal, Singularity — the last two
serverless/hibernating), works with any OpenAI-compatible provider (Nous Portal, OpenRouter, OpenAI, Anthropic,
Google, **local Ollama**), and ships ~90 bundled + ~60 optional skills on the open [agentskills.io](https://agentskills.io)
standard. Its differentiator is a **closed learning loop**: it creates skills from experience, improves them during
use, nudges itself to persist knowledge, and builds a deepening model of the user across sessions.

**The fit thesis for Ariadne:** Hermes is the _engine_ that could one day **operate** Ariadne — running retrieval
chains, drafting packet fills, monitoring SAM, authoring/refining skills — **while you sleep**, landing everything
in the review queue for human ratification. Ariadne stays the **system of record + review gate + UI**; Hermes
becomes the autonomous worker behind it. **Never** the other way around.

---

## 2. End-state pillars (why we want it — ⭐)

| Pillar                              | Hermes feature(s)                                                                                                  | Ariadne payoff                                                                                                    |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| **Overnight operator**              | Cron + Persistent Goals (Ralph loop) + Delegation + Gateway delivery                                               | Wakes you to a stacked, gated morning briefing — monitoring, chains, draft fills done overnight                   |
| **Self-improving skills & process** | Autonomous skill creation + skill self-improvement during use + **Curator** (usage/staleness/archival, LLM review) | `skills/` gets better on _your_ markets over time; routine fill recipes sharpen themselves — under git + review   |
| **Closed learning loop**            | Agent-curated memory + nudges + FTS5 recall + LLM summarization + trajectory export (Atropos RL)                   | Approved outcomes compound; feeds `training/examples/` → local SLM fine-tune on KBR R&S / facility-services lanes |

**Guardrail across all three:** _autonomous preparation, human ratification._ Outputs land as `candidate`;
nothing auto-promotes, sends, or commits to trusted state (Ariadne non-negotiable #2).

---

## 3. Full capability catalog → Ariadne mapping

> Everything Hermes offers, with the Ariadne use and the doctrine guardrail. **Adopt** = clear MVP+ fit ·
> **Adapt** = use with constraints · **Avoid (MVP)** = real value but premature or conflicting now.

### 3.1 Memory & learning

| Hermes capability                                                                             | What it does                                        | Ariadne mapping                                                                                                                                                                                    | Verdict              |
| --------------------------------------------------------------------------------------------- | --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| **Memory System** (`MEMORY.md`, `USER.md`, session search)                                    | Cross-session persistent memory                     | **Do not introduce a 3rd store.** Bridge Hermes memory ↔ Ariadne **vault + PG** (the two-store truth). Hermes "working memory" stays scratch; trusted facts flow through review gate into vault/PG | **Adapt**            |
| **Closed learning loop** (nudges, agent-curated memory)                                       | Self-persisting knowledge                           | Drives the ⭐ learning loop; every persisted item is a **candidate**                                                                                                                               | **Adopt (post-MVP)** |
| **FTS5 recall + LLM summarization**                                                           | Fast cross-session retrieval                        | Complements `pgvector` (Phase 17c) + vault search; could front Ariadne's hybrid retrieval                                                                                                          | **Adapt**            |
| **Memory providers** (Honcho, Mem0, OpenViking, Hindsight, RetainDB, ByteRover, Supermemory…) | Pluggable external memory + dialectic user modeling | Optional; **PG + vault remain SSOT**. Honcho user-modeling could personalize copilot tone — low priority                                                                                           | **Avoid (MVP)**      |
| **Trajectory export + Atropos RL**                                                            | Batch trajectories for RL fine-tune                 | Feeds `training/examples/` JSONL → local SLM per `capture-llm-wiki.md`                                                                                                                             | **Adopt (post-MVP)** |

### 3.2 Skills

| Hermes capability                                             | What it does                            | Ariadne mapping                                                                                         | Verdict              |
| ------------------------------------------------------------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------- | -------------------- |
| **Skills System** (progressive disclosure, agent-managed)     | On-demand `SKILL.md` knowledge docs     | **Same format Ariadne already uses** (`skills/*/SKILL.md`). Direct interop                              | **Adopt**            |
| **Autonomous skill creation**                                 | Agent writes new skills from experience | Extends `skill-creator`; new skills land as **git-versioned candidates** → human review before live use | **Adopt (post-MVP)** |
| **Skill self-improvement during use**                         | Refines skills as it runs               | Sharpens `clew_intel`, `mcp_federal_tools`, fill recipes — gated                                        | **Adopt (post-MVP)** |
| **Curator** (usage tracking, staleness, archival, LLM review) | Background skill maintenance            | Pairs with `vault_maintainer` discipline; keeps `skills/` from rotting                                  | **Adopt (post-MVP)** |
| **Skills Hub / agentskills.io** (~90 bundled + ~60 optional)  | Portable community skills               | Mine for capture-relevant skills (research, docs, GTD); vet before adopting                             | **Adapt**            |

### 3.3 Autonomy & orchestration

| Hermes capability                                                    | What it does                                          | Ariadne mapping                                                                                                                                  | Verdict                                                     |
| -------------------------------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------- |
| **Cron jobs** (natural-language, multi-skill, any-platform delivery) | Scheduled automation                                  | **Phase 17j** forward-pipeline: SAM watches, recompete monitors, "Keep It Sold" → review queue                                                   | **Adopt (post-MVP)**                                        |
| **Persistent Goals** (Ralph loop)                                    | Keep working toward a standing goal across turns      | Overnight operator's engine — "fill this packet's MS1 gaps" runs until done or blocked                                                           | **Adopt (post-MVP)**                                        |
| **Delegation** (`delegate_task`, isolated subagents)                 | Parallel child agents                                 | Maps to Ariadne **named retrieval chains** (recompete → incumbent → SAM UEI → web → packet field) as fan-out → converge; each output `candidate` | **Adapt** — encode as named chains, not open-ended autonomy |
| **Kanban Multi-Agent** (durable SQLite task board)                   | Coordinate multiple Hermes profiles                   | Could back the **Tasks** lane / overnight work board — but Ariadne's `operator_tasks` PG is SSOT                                                 | **Avoid (MVP)**                                             |
| **Code Execution** (`execute_code`, Programmatic Tool Calling)       | Collapse multi-step pipelines into one inference call | Powerful for deterministic intel chains (PG → MCP → format) in one shot                                                                          | **Adapt** — sandbox + provenance required                   |
| **Hooks** (lifecycle: log, alert, webhook)                           | Run code at key points                                | Emit review-queue events, audit external calls                                                                                                   | **Adopt (post-MVP)**                                        |
| **Batch Processing**                                                 | Trajectories at scale                                 | Bulk intel enrichment / training data gen                                                                                                        | **Avoid (MVP)**                                             |

### 3.4 Interfaces & I/O

| Hermes capability                              | What it does                                                   | Ariadne mapping                                                                                                                                   | Verdict              |
| ---------------------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| **API Server** (OpenAI-compatible)             | Expose Hermes as an LLM endpoint                               | Drop-in provider in `backend/src/thread/llm/router.py` (~10-line add) — _if_ ever wanted                                                          | **Adapt**            |
| **Python Library** (embed `AIAgent`)           | Use Hermes in-process                                          | Could run inside `app.py` as the orchestration engine — but adds heavy dep; weigh vs route-first                                                  | **Avoid (MVP)**      |
| **Messaging Gateway** (21+ platforms)          | Telegram, Discord, Slack, Signal, SMS, Email, Teams, WhatsApp… | **Telegram intake** (`ariadnesthreadhermesbot`) → existing capture FAB + `capture_intent.py` → gated candidate. One door, not a new pipeline      | **Adopt (post-MVP)** |
| **Webhooks** (GitHub/GitLab → agent run)       | Event-triggered runs                                           | Trigger chains from external events (e.g. SAM RSS, repo events)                                                                                   | **Adapt**            |
| **Voice / Browser / Vision / Image gen / TTS** | Multimodal tools                                               | Voice intake on the go; browser/vision overlap with Crawl4AI/MinerU (don't duplicate); **image gen ≠ huashu** (huashu owns presentation graphics) | **Adapt**            |
| **ACP** (VS Code, Zed, JetBrains)              | Hermes inside editors                                          | Dev-time accelerator only — unrelated to Ariadne runtime                                                                                          | **Avoid (MVP)**      |

### 3.5 Platform, providers & ops

| Hermes capability                                                                                           | What it does                         | Ariadne mapping                                                                                                      | Verdict              |
| ----------------------------------------------------------------------------------------------------------- | ------------------------------------ | -------------------------------------------------------------------------------------------------------------------- | -------------------- |
| **Terminal backends** (local, Docker, SSH, **Daytona**, **Modal**, Singularity)                             | Run anywhere; serverless hibernation | Production overnight operator on a cheap VPS / serverless — cost-effective always-on. Defer until loop depth exists  | **Adopt (post-MVP)** |
| **Providers + routing + fallback + credential pools**                                                       | Multi-provider with failover         | Mirrors Ariadne's Grok-primary + Ollama-admin doctrine; Hermes routing could _replace_ hand-rolled router later      | **Adapt**            |
| **Local LLM support** (Ollama / llama.cpp / MLX)                                                            | Run sensitive prompts locally        | **Critical for GovCon** — keep proprietary/PII prompts on local Ollama, never external                               | **Adopt**            |
| **MCP Integration** (+ tool filtering)                                                                      | Connect any MCP server               | **Direct reuse** of `tools/mcps/` (1102 federal tools, SAM, USAspending). Filtering keeps tool surface safe          | **Adopt**            |
| **Security** (command approval, user authz, container isolation, **Checkpoints & Rollback** via shadow git) | Guardrails for autonomy              | Maps to Ariadne review gate + provenance; checkpoints protect destructive ops                                        | **Adopt**            |
| **Context files** (`.hermes.md`, `AGENTS.md`, `SOUL.md`, personality)                                       | Shape every conversation             | `SOUL.md` = Ariadne capture persona (Shipley, review-gated, command-first); `AGENTS.md` aligns with planned DOX tree | **Adopt**            |

---

## 4. Concept mapping (Hermes ↔ Ariadne)

| Hermes                           | Ariadne equivalent (keep as SSOT)                                                                       | Integration seam                               |
| -------------------------------- | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| Memory (`MEMORY.md` / providers) | **PG intel + Obsidian vault** (two-store doctrine)                                                      | Hermes scratch memory → review gate → vault/PG |
| Skills (`SKILL.md`, Skills Hub)  | **`skills/`** (`clew_intel`, `mcp_federal_tools`, `vault_maintainer`, `idea_capturer`, `skill-creator`) | Same `SKILL.md` standard — direct interop      |
| MCP servers                      | **`tools/mcps/`** + `mcp` adapter                                                                       | Shared MCP layer                               |
| API server                       | **`llm/router.py`**                                                                                     | Add as one provider                            |
| Gateway (Telegram…)              | **Capture FAB + `capture_intent.py`**                                                                   | Telegram → intake endpoint → candidate         |
| Cron / Persistent Goals          | **Phase 17j** + named retrieval chains                                                                  | Scheduled chains → review queue                |
| Curator + skill self-improvement | **`skill-creator` + `vault_maintainer`**                                                                | Gated skill authoring/refinement               |
| `SOUL.md` / personality          | Capture persona + design principles                                                                     | Encodes Shipley + command-first tone           |
| Checkpoints & rollback           | Review gate + provenance                                                                                | Safety for autonomous writes                   |
| Trajectory export / Atropos      | **`training/examples/`** JSONL                                                                          | Local SLM fine-tune loop                       |

---

## 5. Doctrine alignment & guardrails

**Must respect (Ariadne non-negotiables):**

1. **Review-gated everywhere (#2)** — Hermes _prepares_ candidates; humans promote. No auto-promote/send/commit.
2. **Two-store knowledge (#5)** — PG + vault stay SSOT. Hermes memory is working scratch, not a third truth store.
3. **Server-owned truth (#7)** — domain rules stay in Ariadne `services/`. Hermes calls them; it doesn't own them.
4. **One command to run (#8)** — if adopted in-process, must not break `python app.py`; if out-of-process, it's a _separate_ worker that talks to Ariadne's API, not a fork of the UX.
5. **GovCon data sensitivity** — sensitive/proprietary prompts route to **local Ollama**; log every external call; redact before any cloud provider.
6. **ponytail** — adopt Hermes to _delete_ hand-rolled plumbing (router, gateway, cron), not to _add_ a parallel stack. If it doesn't simplify, don't adopt it.

**Explicitly avoid (even post-MVP, unless justified):** Kanban as a second task store · external memory providers as SSOT · open-ended autonomous goals without chain boundaries · using Hermes as the UI (Ariadne HTMX stays the face) · multi-platform sprawl (Telegram is enough; skip Discord/Slack/WhatsApp/etc.).

---

## 6. Architecture (platform-first — when ready)

```
                ┌────────────────────────────────────────────┐
   Telegram ───►│  Hermes worker (separate process / VPS)     │
   (mobile)     │  • cron + persistent goals (Ralph loop)     │
                │  • subagent delegation = named chains        │
                │  • skill author/curator (gated)              │
                │  • local Ollama for sensitive prompts        │
                └───────────────┬────────────────────────────┘
                                │ calls Ariadne API + MCP + skills
                                ▼
   ┌──────────────────────────────────────────────────────────┐
   │  Ariadne (system of record + review gate + HTMX UI)        │
   │  llm/router · services/ · tools/mcps/ · skills/            │
   │  PG (truth) + Obsidian vault (synthesis)                   │
   │  REVIEW QUEUE ← every Hermes output lands here as candidate │
   └──────────────────────────────────────────────────────────┘
                                ▲
   You (morning) ──── ratify candidates via review gate ────────┘
```

**Seam of choice:** Hermes runs as a **separate worker** that talks to Ariadne over its **existing API + MCP +
skills** surfaces. This keeps Ariadne the owner of truth/UI and lets the worker live on a cheap always-on
VPS/serverless backend. The in-process Python-library option is heavier and risks the single-launcher doctrine —
prefer the worker model.

---

## 7. Phased adoption path (gated on MVP)

> **Gate 0:** Do not start until [`PLAN.md`](PLAN.md) **M1–M3** prove the loop has real depth and the named
> retrieval chains exist as route-first recipes. The chains are the substrate Hermes runs.

| Stage                           | Scope                                                                                | Pre-req                   |
| ------------------------------- | ------------------------------------------------------------------------------------ | ------------------------- |
| **H1 · Provider**               | Add Hermes API server as an optional provider in `llm/router.py`; A/B vs Grok/Ollama | MVP loop stable           |
| **H2 · Telegram intake**        | `ariadnesthreadhermesbot` → Ariadne intake endpoint → capture FAB → gated candidate  | H1 + capture FAB          |
| **H3 · MCP + skills reuse**     | Point Hermes at `tools/mcps/` + `skills/`; verify gated outputs                      | H1                        |
| **H4 · Cron monitors**          | SAM watches / recompete monitors (Phase 17j) → review queue                          | 17j design + H3           |
| **H5 · Named-chain delegation** | Encode retrieval chains as Hermes delegated subagents; converge → candidates         | route-first chains proven |
| **H6 · Overnight operator**     | Persistent Goals + cron + delegation; morning briefing of gated candidates           | H4 + H5 + security        |
| **H7 · Self-improving skills**  | Autonomous skill authoring + Curator; git-versioned, review-gated                    | H5 + `skill-creator`      |
| **H8 · Closed learning loop**   | Trajectory export → `training/examples/` → local SLM fine-tune                       | approved-outcome corpus   |
| **H9 · Production worker**      | Daytona/Modal/VPS always-on; Tailscale; local Ollama for sensitive                   | all above + threat model  |

---

## 8. Risks & mitigations

| Risk                                                       | Mitigation                                                                                           |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **GovCon data exposure**                                   | Local Ollama for sensitive prompts; redact before cloud; log all external calls; container isolation |
| **Scope creep / never-finish** (the problem we just fixed) | Hard gate: no Hermes work until M1–M3 done; this doc stays parked                                    |
| **Third memory store fragments truth**                     | PG + vault remain SSOT; Hermes memory is scratch only                                                |
| **Autonomous overreach**                                   | Review gate on every output; checkpoints/rollback; bounded named chains, not open goals              |
| **Parallel stack instead of simplification**               | Adopt only to _delete_ hand-rolled plumbing (ponytail); otherwise skip                               |
| **Vendor/runtime drift**                                   | MIT license → can vendor/pin; prefer worker-over-API seam to stay loosely coupled                    |

---

## 9. Corrections to the earlier Grok integration plan

The June-24 Grok plan (`hermes-integration-plan-updated-june-24-2026.md`) was directionally useful but **not
grounded in the repo** and **undersold Hermes**. Corrections:

- **Wrong paths:** it cited `backend/utils/llm_router.py` and "HTMX templates in `frontend/`". Real paths:
  `backend/src/thread/llm/router.py` and `backend/src/thread/ui/` (the `frontend/` Next.js is **retired**).
- **Undercaptured power:** it omitted Curator, Persistent Goals (Ralph loop), Kanban multi-agent, Code Execution,
  Checkpoints/Rollback, trajectory export/RL, memory providers, ACP, webhooks, `SOUL.md` — all captured above.
- **Premature production:** it front-loaded Hetzner/Telegram/Docker before loop depth. Re-sequenced behind Gate 0.
- **Memory framing:** it treated Hermes memory as a feature to _add_; correct framing is _bridge to_ vault/PG, not a new store.

---

## 10. Open questions (resolve before H1)

1. **Worker vs in-process?** Recommend separate worker over Ariadne's API (keeps single-launcher doctrine). Confirm.
2. **How much memory bridges to vault/PG vs stays Hermes-local scratch?** Define the promotion contract.
3. **Which named chains ship first** as Hermes-delegated subagents (recompete→incumbent→SAM→web→packet field)?
4. **Local model for sensitive prompts** — Ollama model + redaction policy for GovCon.
5. **Hosting** — Daytona/Modal serverless vs fixed VPS; Tailscale access; data isolation posture.

---

_Parked reference — promote stages into [`PLAN.md`](PLAN.md) only after MVP loop depth (M1–M3). Last reviewed 2026-06-24._
