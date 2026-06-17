# Ariadne's Thread

Shipley-aligned capture command center for a single professional managing multiple opportunities.

## Quick start

```powershell
cd C:\Users\benma\ariadne-capform
# Edit .env — paste XAI_API_KEY and optional research/MCP keys
python app.py
```

`python app.py` handles everything: `.venv` bootstrap (first run), Docker Postgres on **port 55432**, vault seed, frontend dev server, and API.

- API: http://127.0.0.1:9622
- UI: http://127.0.0.1:3000
- PostgreSQL: `127.0.0.1:55432` (Thread-dedicated — not 5432)

## Reference corpus

Domain dictionaries live in [`docs/reference/`](docs/reference/README.md):

- **Living Briefing Packet** — `briefing_packet/BRIEFING_PACKET_DATA_DICTIONARY.md` seeds packet fields
- **Call Plan** — customer engagement workflow
- **Risk Register** — slide 13 risk rows
- **USAspending** — `docs/usaspending/` official + plain-English dictionaries
- **Shipley Capture Guide** — `docs/reference/shipley/`

Packet field seeds: [`backend/src/thread/domain/packet_field_seed.py`](backend/src/thread/domain/packet_field_seed.py)

## Architecture

| Layer | Technology |
|-------|------------|
| Workflow truth | PostgreSQL (opportunities, packet, review gates) |
| Intel | PostgreSQL tables migrated from capture-insights DuckDB (one-time) |
| Knowledge brain | Obsidian vault at `knowledge/thread/` |
| Reasoning | Grok/xAI primary; Ollama admin offload |
| Orchestration | Route-first now; LangGraph skill chains on `:9623` when `LANGGRAPH_ENABLED` |
| Web research | SearXNG + Crawl4AI (free), SerpAPI/Olostep/Firecrawl fallbacks |
| Federal data | 1102 MCP manifests in `tools/mcps/` |

**Review rule:** Intake → Candidate → Trusted. Nothing auto-promotes.

## Extension path

1. Complete intel migration + pg_queries from capture-insights
2. Research module + Research UI tab
3. Skill runtime execution
4. Document intake → MinerU → ExtractionBundle
5. Theseus adapter on port 9621 for Phase 4–6 activation