"""Append Clew/research enrichment sections to vault candidates — candidate only."""

from __future__ import annotations

from dataclasses import dataclass

from thread.config import Settings
from thread.research.capture_research import load_run
from thread.services.vault_write import VaultWriteResult, load_candidate_note, save_candidate_note


class CandidateEnrichError(Exception):
    pass


@dataclass(frozen=True)
class AutoEnrichPlan:
    source: str
    clew_mode: str = "spend_trend"
    research_query: str = ""


def infer_auto_enrich(*, page_type: str, title: str) -> AutoEnrichPlan:
    """Platform picks enrich source — operator does not configure facets."""
    pt = (page_type or "synthesis").strip().lower()
    name = (title or "vault candidate").strip()
    if pt in {"concept", "synthesis", "framework", "process"}:
        return AutoEnrichPlan(source="clew", clew_mode="spend_trend")
    return AutoEnrichPlan(source="research", research_query=name[:120])


@dataclass(frozen=True)
class EnrichResult:
    candidate_path: str
    section_title: str
    source: str
    provenance_ref: str
    write: VaultWriteResult


def build_research_enrichment(
    settings: Settings,
    *,
    run_id: str | None = None,
    query: str | None = None,
) -> tuple[str, str, str]:
    if run_id:
        run = load_run(settings, run_id)
        if not run:
            raise CandidateEnrichError(f"Research run not found: {run_id}")
        lines: list[str] = []
        for finding in run.get("findings") or []:
            if not isinstance(finding, dict):
                continue
            title = str(finding.get("title") or "Finding")
            summary = str(finding.get("summary") or "")
            lines.append(f"- **{title}**: {summary}")
        interpretation = str(run.get("interpretation") or "").strip()
        if interpretation:
            lines.append("")
            lines.append(interpretation)
        body = "\n".join(lines).strip() or "(no findings in run)"
        q = str(run.get("query") or "research")
        return f"Research — {q[:72]}", body, f"research:{run_id}"

    if query and query.strip():
        q = query.strip()
        body = (
            f"Bounded research stub for **{q}**.\n\n"
            "- Run full research on workspace or `/api/research` for live sources.\n"
            "- This section is candidate synthesis until you approve promote."
        )
        return f"Research — {q[:72]}", body, f"research:stub:{q[:48]}"

    raise CandidateEnrichError("Research enrich requires run_id or query")


def build_clew_enrichment(
    *,
    mode: str = "spend_trend",
    agency: str = "",
    recipient: str = "",
) -> tuple[str, str, str]:
    clean_mode = (mode or "spend_trend").strip()
    lines = [
        f"Clew trace stub — mode `{clean_mode}`.",
        "",
        "Use **Clew** (`/clew`) for full Sankey/bar traces; this block appends draft context only.",
    ]
    if agency.strip():
        lines.append(f"- Agency facet: {agency.strip()}")
    if recipient.strip():
        lines.append(f"- Recipient facet: {recipient.strip()}")
    body = "\n".join(lines)
    ref = f"clew:{clean_mode}:{agency.strip() or 'any'}:{recipient.strip() or 'any'}"
    return f"Clew — {clean_mode}", body, ref


def append_candidate_enrichment(
    settings: Settings,
    candidate_rel: str,
    *,
    title: str,
    body: str,
    source: str,
    provenance_ref: str,
) -> EnrichResult:
    loaded = load_candidate_note(settings, candidate_rel)
    section = (
        f"\n\n## {title.strip()}\n\n"
        f"> Enrichment candidate · `{provenance_ref}` · source:{source}\n\n"
        f"{body.strip()}\n"
    )
    new_body = loaded["body"].rstrip() + section
    write = save_candidate_note(
        settings,
        candidate_rel,
        name=loaded["name"],
        body=new_body,
        page_type=loaded["page_type"],
        related=list(loaded["related"]),
    )
    return EnrichResult(
        candidate_path=candidate_rel,
        section_title=title.strip(),
        source=source,
        provenance_ref=provenance_ref,
        write=write,
    )


async def enrich_candidate_note(
    settings: Settings,
    candidate_rel: str,
    *,
    source: str,
    research_run_id: str | None = None,
    research_query: str | None = None,
    clew_mode: str = "spend_trend",
    agency: str = "",
    recipient: str = "",
) -> EnrichResult:
    src = (source or "").strip().lower()
    if src == "research":
        title, body, ref = build_research_enrichment(
            settings,
            run_id=research_run_id,
            query=research_query,
        )
    elif src == "clew":
        title, body, ref = build_clew_enrichment(mode=clew_mode, agency=agency, recipient=recipient)
    else:
        raise CandidateEnrichError(f"Unknown enrich source: {source}")
    return append_candidate_enrichment(
        settings,
        candidate_rel,
        title=title,
        body=body,
        source=src,
        provenance_ref=ref,
    )