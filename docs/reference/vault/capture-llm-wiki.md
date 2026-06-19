---
name: "capture-llm-wiki"
type: "schema"
id: "foundation-capture-llm-wiki"
schema_version: 2
tags: ["karpathy-wiki", "schema", "vault"]
---

# capture-llm-wiki Schema (Karpathy LLM Wiki + Thread Capture Ontology)

**Layer 3 contract** for how agents maintain `knowledge/thread/`. Read this before any vault write.

**Karpathy pattern** ([llm-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)):
- Obsidian = IDE (desktop optional; `/knowledge` browser in app)
- LLM = programmer (Grok Build, skills runner, external agents)
- Wiki `.md` = codebase — persistent, compounding artifact

**Thread addition:** trusted wiki writes only after **review gate** (`candidate` → `trusted`). Wiki informs; PostgreSQL executes packet fields.

## 1. Three layers (mandatory)

| Layer | Location | Who writes | Rule |
|-------|----------|------------|------|
| **1 Raw** | PostgreSQL `intel_*`, `docs/reference/`, MCP snapshots, MinerU parse output | Ingest, MCP, humans | **Immutable** — LLM reads, never edits |
| **2 Wiki** | `knowledge/thread/` (`entities/`, `global/`, `pursuits/`, …) | LLM + human after review | **Append, never erase** trusted sections |
| **3 Schema** | `foundation/capture-llm-wiki.md` (this file) | Humans + platform seed | Co-evolve; `schema_version` bumps on platform updates |

## 2. Folder conventions (`knowledge/thread/`)

```
knowledge/thread/
  index.md                     # Content catalog — update on every trusted ingest
  log.md                       # Append-only timeline — greppable ingest/query/lint lines
  foundation/                  # Schema + reference mirrors (Layer 3)
    capture-llm-wiki.md        # This file
    reference/                 # Packet/call-plan/risk mirrors
  entities/
    agencies/                  # Customer / funding org pages
    competitors/               # Recipients, primes, subs
  global/
    global_wiki/               # Evergreen doctrine (Shipley, FAR, workload)
    domain_intel/              # Bid-fit: capabilities/, uei/, milestones/
  pursuits/<slug>/             # Per-opportunity wiki (created on Track)
  data-elements/               # One page per briefing packet field key
  milestones/                  # MS1–MS4 gate context
  relationships/               # Follow-the-money graph notes
  generated-projections/       # LLM drafts **before** review promotion
  training/                    # SLM fine-tune exports
  education/
  .obsidian/                   # Desktop Obsidian config (seeded, optional)
```

## 3. Platform skills (use before vault edits)

Vendored under repo `skills/` (Grok Build + Thread skill runner):

| Skill | When |
|-------|------|
| `obsidian-markdown` | **Required** — wikilinks, properties, callouts, embeds (kepano) |
| `vault_maintainer` | Thread ingest/query/lint + review gate + dedup rules |
| `obsidian-bases` | Entity tables / filtered views (optional) |
| `json-canvas` | Relationship canvases (optional) |
| `obsidian-cli` | Obsidian desktop automation (optional) |
| `defuddle` | Clean web clip → markdown ingress (optional) |

**Agent bootstrap prompt:**
> Read `foundation/capture-llm-wiki.md` and load `obsidian-markdown` + `vault_maintainer`. You maintain `knowledge/thread/` per Karpathy ingest/query/lint. Never modify Layer 1 raw. Trusted writes only after review promotion.

## 4. Page format (Obsidian Flavored Markdown)

Every wiki page **must** start with YAML frontmatter:

```yaml
---
name: "Exact Entity or Concept Name"
type: "agency" | "competitor" | "concept" | "opportunity" | "data-element" | "synthesis" | ...
id: "entity-agency-dhs" | "pursuit-acme-recompete" | ...
trust: "candidate" | "trusted"
review_id: "uuid-or-null"
added: "2026-06-18T12:00:00Z"
last_updated: "2026-06-18"
citations: "award_key:CONT_AWD_... • agency:Army • source:clew_intel • review:..."
tags: ["recompete", "shipley"]
aliases: ["DHS", "Department of Homeland Security"]
---
```

**Body sections** (append on re-ingest; never delete trusted history):

```markdown
## Key signals + citations
- Grounded bullets with `award_key`, NAICS, MCP tool, URL

## Synthesis
Evidence-based analysis (LLM or human)

## Open questions
- ...

## Related
[[agency-name]] [[competitor-name]] [[milestone_1]] [[data-element/opportunity_name]]

## Added/Updated 2026-06-18
Append-only section per ingest pass
```

**Dedup rule:** Before append, grep vault for same `award_key` or `review_id`. Same identity → merge into existing dated section; do not duplicate claims.

## 5. Capture ontology

- **Entities:** agencies, competitors/recipients, programs, NAICS, vehicles, pricing types
- **Signals** (always cite Layer 1): intensity, money flows, recompete/expiring, vehicles/pricing, geo concentration
- **Capture concepts:** win themes, discriminators, PP, teaming, pricing, risk, customer intimacy
- **Provenance:** Every claim needs citation. Never invent award data.
- **Wikilinks:** `[[entities/agencies/dhs]]` or `[[dhs]]` if alias set — graph must stay connected

## 6. Workflows

### Ingest (trusted promotion or approved automation)

1. Read raw signal (PG row, MCP result, research URL, MinerU chunk)
2. Check `review_id` / `award_key` dedup
3. Update 1 primary page + 3–10 related pages (entity, `domain_intel`, `pursuits/<slug>/`, `relationships/`)
4. Append `## Added/Updated <date>` — never overwrite prior trusted sections
5. Update `index.md` row for each touched page
6. Append `log.md` line: `## [2026-06-18] ingest | Entity Name | review:<id>`

**Candidate path:** write under `generated-projections/` or `trust: candidate` frontmatter until `/review` approve.

### Query

1. Read `index.md` first
2. Open relevant pages via wikilinks
3. Synthesize with citations to wiki + raw Layer 1
4. File valuable answers back as new pages or append sections

### Lint (periodic)

- Contradictions between pages (same `award_key`, conflicting claims)
- Stale `last_updated` vs newer PG intel
- Orphan pages (no inbound `[[wikilinks]]`)
- Concepts mentioned without own page
- Missing `Related` section
- Append lint summary to `log.md`: `## [date] lint | N issues`

## 7. Obsidian desktop (optional)

Point Obsidian vault folder at **`knowledge/thread/`** (absolute path on your machine).

- Bootstrap seeds `.obsidian/` with safe defaults (see `foundation/reference/obsidian-desktop.md`)
- Use graph view for hub/orphan detection
- Plugins (user choice): Dataview, Graph Analysis, Omnisearch, Web Clipper, Defuddle
- Desktop edits **append**; align with schema. Platform `/knowledge` browser stays read-only until 17b-vault write API

## 8. Thread implementation status

| Capability | Status |
|------------|--------|
| Vault seed + browse (`/knowledge`) | ✅ |
| Karpathy `index.md` + `log.md` | ✅ seeded; auto-update on ingest **17b-vault** |
| Review gate before trusted write | ✅ doctrine; write API **17b-vault** |
| Skills vendored (kepano + `vault_maintainer`) | ✅ |
| Lint automation | 📋 skill-guided; scheduled job future |
| pgvector vault search | 📋 Phase 17c |

---

**Schema version:** 2 (Thread paths, platform skills, review gate, Obsidian desktop)