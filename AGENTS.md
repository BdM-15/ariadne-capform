# Ariadne's Thread (ariadne-capform) — Grok agent rules

Shipley-aligned capture command center. Full MVP plan: [`docs/PLAN.md`](docs/PLAN.md).

## Engineering guardrails

Ponytail minimalism + deep-module architecture + vertical-slice TDD apply by default (global + [`.grok/rules/00-engineering-guardrails.md`](.grok/rules/00-engineering-guardrails.md)).

- Features and bug fixes: test-first through public interfaces.
- Architecture changes: read `docs/PLAN.md` and `docs/reference/` first; prefer deepening modules over shallow pass-throughs.
- Before claiming done: run pytest from `.venv` (see guardrails file).

## Agent skills

### Issue tracker

GitHub Issues at `BdM-15/ariadne-capform`. See [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md).

### Triage labels

Default Matt Pocock vocabulary. See [`docs/agents/triage-labels.md`](docs/agents/triage-labels.md).

### Domain docs

Single-context; `docs/PLAN.md` is the domain north star. See [`docs/agents/domain.md`](docs/agents/domain.md).

## Quick commands

```powershell
python app.py                                          # dev server :9622
.venv\Scripts\python.exe -m pytest backend/tests/ -v   # tests
```

## Product rules

- Review gate: intake → candidate → trusted. Nothing auto-promotes.
- Grok/xAI primary reasoning; Ollama admin offload only when configured.