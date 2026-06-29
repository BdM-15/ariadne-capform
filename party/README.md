# Hermes Agent Party Profiles

Isolated Hermes Desktop agent profiles for the Ariadne capture party. Each hero lives in its own folder under `profiles/` with four files:

| File | Role |
|------|------|
| `SOUL.md` | Core mission, behaviors, and voice |
| `IDENTITY.md` | Hero name, class, and strengths |
| `USER.md` | Operator context (Benjamin / Ariadne-Capform) |
| `AGENTS.md` | Tooling rules and delegation boundaries |

## Heroes

- **guildmaster** — Quest coordinator; turns packet gaps into side quests
- **healer** — UI, Party Command, and operator-facing surfaces
- **artificer** — Integrations, MCP, and infrastructure
- **rogue** — Research, intel, and competitive signals
- **mage** — Reasoning chains, skills, and LLM orchestration
- **knight** — Compliance, evidence, and Shipley discipline
- **bard** — Narrative logs, reports, and motivation

Profiles are intentionally isolated: import a hero folder into Hermes Desktop as a separate workspace profile. They do not share memory or `AGENTS.md` with the main Ariadne-Capform repo agent rules.

Mission metrics and quest state for the party dashboard live in the **Tavern** system (`tavern/`) — PostgreSQL tables + `/tavern/*` API on the main app (`:9622`).