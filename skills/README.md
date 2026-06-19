# Thread platform skills

Discovered by `thread.skills.registry.discover_skills` from `skills/*/SKILL.md`.

## Capture & intel

| Skill | Purpose |
|-------|---------|
| `clew_intel` | Money-flow / teaming analysis over PG intel |
| `mcp_federal_tools` | USAspending + SAM MCP guidance |
| `vault_maintainer` | Karpathy wiki ingest/query/lint for `knowledge/thread/` |
| `idea_capturer` | Fleeting thought → schema-valid vault candidate (Vault Inbox) |

## Obsidian / vault (vendored from [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills))

MIT license — see `kepano-obsidian-skills.LICENSE`.

| Skill | Purpose |
|-------|---------|
| `obsidian-markdown` | Wikilinks, frontmatter, callouts, embeds |
| `obsidian-bases` | `.base` views and formulas |
| `json-canvas` | `.canvas` boards |
| `obsidian-cli` | Obsidian CLI integration |
| `defuddle` | Clean web → markdown |

**Grok Build:** installed to `.grok/skills/` (project) and `~/.grok/skills/` (user). Load `obsidian-markdown` + `vault_maintainer` before any vault work. Re-sync after vendored updates:

```powershell
$skills = 'obsidian-markdown','obsidian-bases','json-canvas','obsidian-cli','defuddle','vault_maintainer'
foreach ($s in $skills) { Copy-Item -Recurse -Force "skills\$s" ".grok\skills\$s" }
```

## Meta

| Skill | Purpose |
|-------|---------|
| `skill-creator` | Scaffold new skills |

## Vault schema

`docs/reference/vault/capture-llm-wiki.md` → seeded to `knowledge/thread/foundation/capture-llm-wiki.md` on bootstrap.