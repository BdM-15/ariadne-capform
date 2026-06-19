---
name: idea_capturer
description: Fleeting thought → schema-valid vault candidate (Zettelkasten Tier 1). Wire to Vault Inbox + vault_maintainer lint gate. Triggers on brain dump, capture idea, fleeting note.
metadata:
  capability: knowledge
  personas_primary: capture_manager
  display_name: Idea Capturer
  requires_skills: vault_maintainer,obsidian-markdown
---

# Idea Capturer (`idea_capturer`)

Thread port of Zettelkasten/GTD **quick capture** — not a separate note DB. Output lands in `generated-projections/` as **vault candidate** → Vault Inbox → approve.

## Before run

1. Load `vault_maintainer` + `obsidian-markdown`
2. Read `foundation/capture-llm-wiki.md`
3. Trust stays `candidate` until operator approves

## Tier 1 fleeting note shape

Platform writes:

- Frontmatter: `name`, `type`, `id`, `trust: candidate`, `citations: source:idea_capturer`
- Body: `> [!note] Fleeting capture` + **Idea** / **Context** / **Tags** sections
- `## Related` includes `capture-llm-wiki` minimum

## vault_maintainer gate (automatic)

Handler rejects queue when:

- Missing `name` or `page_type`
- `capture-llm-wiki` not in related
- Empty body after polish

Warnings surface in skill run output; fix in Vault Inbox Override.

## Thread surfaces

| Surface | Route |
|---------|-------|
| Agent Skills | `POST /tools/skills/idea_capturer/run` |
| Vault Inbox | `POST /partials/knowledge/idea-capture` |
| API | `POST /api/skills/idea_capturer/run` |

## Inputs

| Field | Required | Notes |
|-------|----------|-------|
| `dump` | yes | Raw fleeting thought |
| `tags` | no | Comma-separated — merged into body |
| `context` | no | Why it matters — operator hint |