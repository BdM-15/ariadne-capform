"""Idempotent vault seed — Karpathy LLM-wiki / Obsidian three-layer model.

Layer 1 (raw, immutable): PostgreSQL intel + docs/reference — never written by LLM.
Layer 2 (wiki, LLM-owned): markdown under knowledge/thread/ with wikilinks + frontmatter.
Layer 3 (schema): foundation/capture-llm-wiki.md — contract for how LLM maintains Layer 2.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from thread.config import Settings
from thread.domain.packet_field_seed import PACKET_ANSWERABLE_SEEDS

REQUIRED_DIRS = (
    "foundation",
    "foundation/reference",
    "data-elements",
    "entities",
    "entities/agencies",
    "entities/competitors",
    "relationships",
    "milestones",
    "skills-capabilities",
    "reusable-insights",
    "generated-projections",
    "global",
    "global/domain_intel",
    "global/domain_intel/capabilities",
    "global/domain_intel/milestones",
    "global/domain_intel/uei",
    "training",
    "training/datasets",
    "training/examples",
    "training/prompts",
    "education",
    "pursuits",
)

# Full capture-insights knowledge port (idempotent merge — skip existing files).
# domain_intel = bid/no-bid fit, capabilities, UEI past-performance awareness.
# training = SLM fine-tune scaffold (datasets/examples/prompts fill as Thread runs).
# Schema (capture-llm-wiki.md) is Thread-owned — see VAULT_REFERENCE_COPIES + _upgrade_vault_schema.
CAPTURE_INSIGHTS_COPIES: tuple[tuple[str, str], ...] = (
    ("global/global_wiki", "global/global_wiki"),
    ("global/domain_intel", "global/domain_intel"),
    ("brain/agencies", "entities/agencies"),
    ("brain/competitors", "entities/competitors"),
    ("training", "training"),
    ("education", "education"),
)

VAULT_REFERENCE_COPIES: tuple[tuple[str, str], ...] = (
    ("vault/capture-llm-wiki.md", "foundation/capture-llm-wiki.md"),
    ("vault/OBSIDIAN_DESKTOP.md", "foundation/reference/obsidian-desktop.md"),
)

REFERENCE_COPIES: tuple[tuple[str, str], ...] = (
    ("briefing_packet/BRIEFING_PACKET_DATA_DICTIONARY.md", "foundation/reference/briefing-packet-data-dictionary.md"),
    ("briefing_packet/BRIEFING_PACKET_MODEL.md", "foundation/reference/briefing-packet-model.md"),
    ("call_plan/CALL_PLAN_DATA_DICTIONARY.md", "foundation/reference/call-plan-data-dictionary.md"),
    ("call_plan/CALL_PLAN_MODEL.md", "foundation/reference/call-plan-model.md"),
    ("risk_register/RISK_REGISTER_DATA_DICTIONARY.md", "foundation/reference/risk-register-data-dictionary.md"),
    ("risk_register/RISK_REGISTER_MODEL.md", "foundation/reference/risk-register-model.md"),
)

MILESTONE_PAGES: tuple[tuple[str, str, str], ...] = (
    (
        "milestone_1",
        "Milestone 1 — Qualification",
        "Shipley qualification gate. Packet MS1-critical fields must be answered or explicitly gap-flagged.",
    ),
    (
        "milestone_2",
        "Milestone 2 — Pursuit / No Pursuit",
        "Pursuit decision gate. Competitive landscape, pricing posture, and recommendation sharpen here.",
    ),
    (
        "milestone_3",
        "Milestone 3 — Bid / No-Bid",
        "Bid decision gate. Solution strategy, risks, and price-to-win narrative converge.",
    ),
    (
        "milestone_4",
        "Milestone 4 — Pricing Approval",
        "Pricing approval gate. Final commercial narrative and leadership sign-off.",
    ),
)

_INDEX_STUB = "Karpathy/Obsidian brain for Thread"
_SCHEMA_VERSION_RE = re.compile(r"^schema_version:\s*(\d+)\s*$", re.MULTILINE)


@dataclass
class SeedReport:
    path: str
    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.created)


def _rel(vault: Path, path: Path) -> str:
    return str(path.relative_to(vault))


def _schema_version(path: Path) -> int:
    if not path.is_file():
        return 0
    match = _SCHEMA_VERSION_RE.search(path.read_text(encoding="utf-8"))
    return int(match.group(1)) if match else 0


def _upgrade_vault_schema(src: Path, dest: Path, report: SeedReport, vault: Path) -> None:
    if not src.is_file():
        return
    src_ver = _schema_version(src)
    dest_ver = _schema_version(dest)
    if dest.exists() and dest_ver >= src_ver:
        report.skipped.append(_rel(vault, dest))
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    report.created.append(_rel(vault, dest))


def _ensure_obsidian_desktop_scaffold(ref_root: Path, vault: Path, report: SeedReport) -> None:
    template = ref_root / "vault" / "obsidian"
    if not template.is_dir():
        return
    obsidian = vault / ".obsidian"
    for item in template.rglob("*"):
        if item.is_dir():
            continue
        target = obsidian / item.relative_to(template)
        if target.exists():
            report.skipped.append(_rel(vault, target))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        report.created.append(_rel(vault, target))


def _copy_file_if_missing(src: Path, dest: Path, report: SeedReport, vault: Path) -> None:
    if dest.exists():
        report.skipped.append(_rel(vault, dest))
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    report.created.append(_rel(vault, dest))


def _merge_tree(src: Path, dest: Path, report: SeedReport, vault: Path) -> None:
    if not src.exists():
        return
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        target = dest / item.relative_to(src)
        if target.exists():
            report.skipped.append(_rel(vault, target))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        report.created.append(_rel(vault, target))


def _write_if_missing(path: Path, content: str, report: SeedReport, vault: Path) -> None:
    if path.exists():
        report.skipped.append(_rel(vault, path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    report.created.append(_rel(vault, path))


def _data_element_page(seed) -> str:
    route = seed.answer_route
    sources = ", ".join(route.sources) if route else ""
    hint = route.hint if route else ""
    det = "true" if route and route.deterministic else "false"
    feeds = ", ".join(route.feeds) if route and route.feeds else ""
    return f"""---
name: "{seed.label}"
type: "data-element"
id: "element-{seed.key}"
field_key: "{seed.key}"
packet_section: "{seed.section.value}"
value_kind: "{seed.value_kind.value}"
route_kind: "{seed.route_kind.value}"
reference_slide: "{seed.reference_slide}"
answer_sources: "{sources}"
answer_deterministic: {det}
answer_feeds: "{feeds}"
source: "docs/reference/briefing_packet/BRIEFING_PACKET_DATA_DICTIONARY.md"
tags: ["packet-field", "data-element"]
---

# {seed.label}

**Field key:** `{seed.key}`

## Question
{seed.question}

## Answer routes (Phase 20 stub)
{hint}
Sources: `{sources or "human_input"}`

## Layer 1 — raw truth (immutable)
- PostgreSQL `packet_field_answers` row for this `field_key`
- Intel provenance via `award_key` / MCP / research URLs when populated

## Layer 2 — wiki role
LLM may synthesize prose *about* this element in pursuit pages — always cite Layer 1.
Never overwrite trusted packet values from wiki; mirror as `candidate` through review gate.

## Related
[[thread-wiki-schema]] [[capture-llm-wiki]]
"""


def _build_index_md() -> str:
    return """---
name: "Ariadne's Thread Knowledge Vault"
type: "meta"
id: "vault-index"
tags: ["index", "karpathy-wiki"]
---

# Ariadne's Thread Knowledge Vault

Karpathy **LLM-wiki** pattern (Obsidian = IDE, LLM = programmer, `.md` = codebase):

| Layer | Location | Who writes |
|-------|----------|------------|
| **1 Raw** | PostgreSQL intel, `docs/reference/` | Humans, ingest, MCP — **immutable** |
| **2 Wiki** | This vault (`global/`, `entities/`, `pursuits/`, …) | LLM + human — **append, never erase** |
| **3 Schema** | `foundation/capture-llm-wiki.md` | Humans evolve rules; LLM follows |

## Catalog

- `foundation/` — schema + reference mirrors (Layer 3)
- `data-elements/` — one page per briefing packet field key
- `entities/` — agencies & competitors (`[[wikilinks]]` targets)
- `global/global_wiki/` — evergreen doctrine (Shipley, FAR, workload) — third-party patterns
- `global/domain_intel/` — **bid fit layer**: capabilities, MS gates, UEI/PP awareness (USAspending + SAM + scrape → fit/no-fit)
- `training/` — SLM fine-tune exports (`datasets/`, `examples/`, `prompts/`) — grows as platform runs
- `education/` — onboarding / methodology notes
- `skills/` (repo) — vendored `obsidian-markdown` + `vault_maintainer` for Grok Build / agents
- `.obsidian/` — optional Obsidian desktop config (seeded from `docs/reference/vault/obsidian/`)
- `pursuits/<slug>/` — per-opportunity wiki (created when opportunity tracked)
- `milestones/` — MS1–MS4 gate context
- `relationships/` — follow-the-money / graph notes (future `edges.jsonl`)
- `generated-projections/` — LLM drafts before review promotion
- `log.md` — append-only ingest / lint / query log

Read [[capture-llm-wiki]] before maintaining this vault.
"""


def _ensure_training_scaffold(vault: Path, seed_root: Path, report: SeedReport) -> None:
    """Ensure training subdirs exist even if capture-insights only has README."""
    for sub in ("datasets", "examples", "prompts"):
        _write_if_missing(
            vault / "training" / sub / ".gitkeep",
            "",
            report,
            vault,
        )
    readme_src = seed_root / "training" / "README.md"
    if readme_src.exists():
        _copy_file_if_missing(readme_src, vault / "training" / "README.md", report, vault)
    else:
        _write_if_missing(
            vault / "training" / "README.md",
            "# Training\n\nJSONL/Parquet for local SLM fine-tune. See foundation/capture-llm-wiki.md.\n",
            report,
            vault,
        )


def _build_domain_intel_thread_note() -> str:
    return """---
name: "Domain Intel — Thread Role"
type: "meta"
id: "domain-intel-thread-role"
tags: ["domain-intel", "bid-no-bid", "uei"]
---

# Domain Intel in Ariadne's Thread

**Tier purpose:** Company-specific bid fit — not generic doctrine (`global_wiki/`) and not per-RFP (`pursuits/`).

## LLM uses this for
- **Bid / no-bid** — match opportunity signals (USAspending, SAM.gov, web research) against `capabilities/`
- **Past performance awareness** — crosswalk recipient UEI / award history to what we can credibly claim (`uei/`)
- **Focus** — filter noise; large orgs cannot manually digest all contract history

## Rules
- Append new capability or UEI synthesis; do not overwrite trusted entries without review
- Cite Layer 1: `award_key`, SAM notice ID, scrape URL, PG row
- Promote packet fields via review gate — wiki informs, PostgreSQL executes

## Related
[[capture-llm-wiki]] [[usaspending-plain-english]]
"""


def _build_log_md() -> str:
    return """---
name: "Vault Activity Log"
type: "meta"
id: "vault-log"
tags: ["log", "karpathy-wiki"]
---

# Vault Activity Log

Append-only chronological record (ingests, queries, lints).
Per [[capture-llm-wiki]] — LLM/app adds dated entries; never delete history.
"""


def ensure_vault_seed(settings: Settings) -> SeedReport:
    vault = settings.resolve(settings.knowledge_vault_path)
    seed_root = settings.resolve(settings.knowledge_seed_source)
    ref_root = settings.resolve(settings.reference_docs_root)
    usaspending_doc = settings.repo_root / "docs" / "usaspending" / "data-dictionary-plain-english.md"

    report = SeedReport(path=str(vault))
    vault.mkdir(parents=True, exist_ok=True)

    for name in REQUIRED_DIRS:
        dir_path = vault / name
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            report.created.append(_rel(vault, dir_path))

    for src_rel, dest_rel in CAPTURE_INSIGHTS_COPIES:
        _merge_tree(seed_root / src_rel, vault / dest_rel, report, vault)

    _ensure_training_scaffold(vault, seed_root, report)

    for src_rel, dest_rel in VAULT_REFERENCE_COPIES:
        src = ref_root / src_rel
        dest = vault / dest_rel
        if src_rel.endswith("capture-llm-wiki.md"):
            _upgrade_vault_schema(src, dest, report, vault)
        elif src.exists():
            _copy_file_if_missing(src, dest, report, vault)

    _ensure_obsidian_desktop_scaffold(ref_root, vault, report)

    for src_rel, dest_rel in REFERENCE_COPIES:
        src = ref_root / src_rel
        if src.exists():
            _copy_file_if_missing(src, vault / dest_rel, report, vault)

    if usaspending_doc.exists():
        _copy_file_if_missing(
            usaspending_doc,
            vault / "foundation" / "usaspending-plain-english.md",
            report,
            vault,
        )

    dict_src = ref_root / "briefing_packet" / "BRIEFING_PACKET_DATA_DICTIONARY.md"
    if dict_src.exists():
        _copy_file_if_missing(dict_src, vault / "foundation" / "thread-wiki-schema.md", report, vault)

    for seed in PACKET_ANSWERABLE_SEEDS:
        dest = vault / "data-elements" / f"{seed.key}.md"
        _write_if_missing(dest, _data_element_page(seed), report, vault)

    for gate_key, title, body in MILESTONE_PAGES:
        dest = vault / "milestones" / f"{gate_key}.md"
        content = f"""---
name: "{title}"
type: "milestone"
id: "{gate_key}"
tags: ["milestone", "shipley"]
---

# {title}

{body}

## Related
[[capture-llm-wiki]] [[thread-wiki-schema]]
"""
        _write_if_missing(dest, content, report, vault)

    _write_if_missing(
        vault / "relationships" / "README.md",
        """---
name: "Relationship Graph Notes"
type: "concept"
id: "relationships-readme"
---

# Relationships

Follow-the-money edges and entity graphs land here.
Future: import from `data/graph/edges.jsonl` with `[[wikilinks]]` back to entities.
""",
        report,
        vault,
    )

    _write_if_missing(vault / "pursuits" / ".gitkeep", "", report, vault)
    _write_if_missing(
        vault / "global" / "domain_intel" / "thread-role.md",
        _build_domain_intel_thread_note(),
        report,
        vault,
    )
    _write_if_missing(vault / "log.md", _build_log_md(), report, vault)

    index_path = vault / "index.md"
    if not index_path.exists():
        _write_if_missing(index_path, _build_index_md(), report, vault)
    elif _INDEX_STUB in index_path.read_text(encoding="utf-8") and len(index_path.read_text(encoding="utf-8")) < 400:
        index_path.write_text(_build_index_md(), encoding="utf-8")
        report.created.append("index.md (upgraded stub)")

    return report