# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`docs/PLAN.md`** — MVP north star, three lanes (Identify / Capture / Win), honesty rule for status.
- **`docs/reference/`** — domain dictionaries (briefing packet, Shipley, USAspending, vault).
- **`docs/adr/`** — read ADRs that touch the area you're about to work in (create lazily when decisions crystallize).

If any of these files don't exist, **proceed silently**.

## File structure

Single-context repo:

```
/
├── docs/PLAN.md
├── docs/reference/
├── docs/adr/          (lazy — created as decisions land)
├── backend/src/thread/
└── knowledge/thread/  (Obsidian vault)
```

## Use the project's vocabulary

Thread uses **opportunity**, **packet**, **review gate**, **candidate/trusted**, **lane** (Identify / Capture / Win). Use those terms in issues, refactors, and test names — not generic synonyms.

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding.