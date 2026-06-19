---
name: vault_maintainer
description: Maintain knowledge/thread per Karpathy llm-wiki — ingest, query, lint with review gate, dedup, index/log updates. Requires obsidian-markdown for OFM syntax.
metadata:
  capability: knowledge
  personas_primary: capture_manager
  display_name: Vault Maintainer
  requires_skills: obsidian-markdown
---

# Vault Maintainer (`vault_maintainer`)

Thread-specific Karpathy wiki maintainer. Works with vendored **kepano** `obsidian-markdown` skill.

**Schema:** `knowledge/thread/foundation/capture-llm-wiki.md` (Layer 3)

## Before any edit

1. Load `obsidian-markdown` skill (wikilinks, frontmatter, callouts)
2. Read `foundation/capture-llm-wiki.md`
3. Confirm trust level — **no trusted write** without review promotion unless explicitly building `generated-projections/` candidate

## Test / sandbox (no production contamination)

- `THREAD_VAULT_SANDBOX=true` — candidates → `generated-projections/sandbox/` only; blocks trusted ingest + batch repair/semantic on prod vault
- Test pages: `trust: candidate`, `tags: test`, `citations: source:test`, `id: test-*`
- Promote blocked for test-tagged content unless `THREAD_ALLOW_TEST_PROMOTE=true`
- Lint: `test_in_trusted_zone` = contamination alarm (trusted page with test markers)
- `pytest` uses temp dirs — never touches `knowledge/thread/`

## Vault root

`knowledge/thread/` — not `data/knowledge/` or `brain/`

| Target | Purpose |
|--------|---------|
| `entities/agencies/` | Funding / customer orgs |
| `entities/competitors/` | Recipients, primes, subs |
| `global/domain_intel/` | Bid-fit capabilities, UEI/PP |
| `global/global_wiki/` | Evergreen doctrine |
| `pursuits/<slug>/` | Per-opportunity synthesis |
| `generated-projections/` | Pre-review LLM drafts |
| `relationships/` | Money-flow / teaming notes |

## Ingest checklist

- [ ] Raw signal cited (`award_key`, MCP tool, URL, `review_id`)
- [ ] Dedup: grep existing pages for same `award_key` / `review_id`
- [ ] Frontmatter: `name`, `type`, `id`, `trust`, `citations`, `last_updated`
- [ ] Append `## Added/Updated <date>` — never delete trusted sections
- [ ] `## Related` with `[[wikilinks]]` to ≥2 existing pages
- [ ] Touch related pages (entity + domain_intel + pursuit when applicable)
- [ ] Update `index.md` catalog row per touched page
- [ ] Append `log.md`: `## [YYYY-MM-DD] ingest | <title> | review:<id>`

## Query checklist

- [ ] Read `index.md` first
- [ ] Prefer wiki over raw PG unless verifying claim
- [ ] Cite wiki path + Layer 1 source in answer
- [ ] File non-ephemeral syntheses back into vault

## Platform lint / normalize (batch — not hand-edit every page)

- `GET /api/knowledge/vault/lint` — orphans, legacy ids, broken wikilinks
- `POST /api/knowledge/vault/repair?apply=true` — hubs, alias map, fix `[[brain/]]`→`[[entities]]`, rename README hubs, semantic cross-link, rebuild index
- `POST /api/knowledge/vault/semantic-link?apply=true` — append semantic `## Related` wikilinks (capability↔concept↔milestone↔data-element); compounds on trusted ingest
- `POST /api/knowledge/vault/normalize?apply=true` — OFM pass: YAML list `tags`, Related list bullets, relocate mis-placed wikilinks (repair includes normalize)
- Fix broken links by resolving true targets — never delete wikilinks
- **Graph gate:** run repair + semantic-link until `issue_count: 0` broken links; reduce true orphans (agencies, competitors, capabilities) before adding features

## Lint checklist

- [ ] Orphans (no inbound links)
- [ ] Contradictions (same key, conflicting text)
- [ ] Stale `last_updated` vs known PG refresh
- [ ] Missing pages for heavily linked concepts
- [ ] `trust: candidate` older than 30d still in entity folders
- [ ] Log: `## [YYYY-MM-DD] lint | <summary>`

## Review gate (Thread)

All Clew, research, MCP, Grok outputs → `candidate` in app until `POST /api/review/{id}/approve`.

Vault trusted writes mirror review promotion — set `trust: trusted` + `review_id` in frontmatter.

## Pair with Obsidian desktop

User may open same folder in Obsidian for graph/backlinks. Edits must follow append + schema rules above.

## Related skills

- `obsidian-markdown` — syntax (required)
- `obsidian-bases` — tables/views (optional)
- `defuddle` — web clip ingress (optional)
- `clew_intel` — money-flow candidate findings → ingest after review