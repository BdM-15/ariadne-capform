# Obsidian Desktop + Thread Vault

Optional IDE for `knowledge/thread/`. Karpathy pattern: browse graph, follow wikilinks, manual append — agents do bulk maintenance.

## Open vault

1. Obsidian → **Open folder as vault**
2. Select repo path: `<repo>/knowledge/thread/`
3. First app bootstrap seeds `.obsidian/` if missing

Vault content is gitignored (`knowledge/thread/`). Obsidian config inside vault is local to your machine.

## Recommended plugins (install via Community Plugins)

| Plugin | Use |
|--------|-----|
| **Dataview** | Query frontmatter (`type`, `tags`, `trust`, `award_key`) |
| **Omnisearch** | Fast vault search while PG/pgvector matures |
| **Graph Analysis** | Orphan / hub detection (lint aid) |
| **Obsidian Web Clipper** | Clip articles → `generated-projections/` for review |
| **Defuddle** | Clean HTML → markdown (pairs with `defuddle` skill) |

Not required for Thread app — `/knowledge` HTMX browser works without desktop.

## Conventions

- Match `foundation/capture-llm-wiki.md` frontmatter (`type`, `id`, `trust`, `citations`)
- Use `[[wikilinks]]` — see `skills/obsidian-markdown/SKILL.md`
- **Append** new sections; do not delete trusted history
- Candidate notes: `trust: candidate` or file under `generated-projections/`
- Promote to trusted via Thread `/review` when integrated with 17b-vault write path

## Agents + desktop together

Grok Build / skill runner: load `obsidian-markdown` + `vault_maintainer` from repo `skills/`.

Heavy lint or synthesis can run in agent; you inspect results in Obsidian graph/reading view in real time (Karpathy workflow).

## Related

- [[capture-llm-wiki]] — vault schema
- Platform skills: `skills/README.md`