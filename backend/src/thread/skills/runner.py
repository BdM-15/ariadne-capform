"""Execute built-in skill handlers — outputs stay candidate."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings
from thread.db.models import CapabilityRun
from thread.domain.enums import TrustLevel
from thread.intel import pg_queries
from thread.clew import ANALYSIS_MODES, facet_from_payload, run_facet_analysis
from thread.intel.facet_query import describe_query
from thread.mcp.service import MCPService
from thread.services.review_gate import create_review_record
from thread.services.idea_capturer import IdeaCaptureError, capture_idea_to_vault
from thread.skills.registry import SkillDescriptor, discover_skills


@dataclass
class SkillRunResult:
    skill_id: str
    run_id: str
    status: str
    output: dict[str, Any]
    review_id: str | None = None
    errors: list[str] = field(default_factory=list)


async def run_skill(
    settings: Settings,
    session: AsyncSession,
    skill_id: str,
    payload: dict[str, Any] | None = None,
) -> SkillRunResult:
    skills = discover_skills(settings.resolve(settings.skills_root))
    descriptor = skills.get(skill_id)
    if not descriptor:
        raise KeyError(f"Unknown skill: {skill_id}")

    run_id = str(uuid.uuid4())
    body = payload or {}
    errors: list[str] = []
    output: dict[str, Any]

    if skill_id == "clew_intel":
        output = await _run_clew_intel(settings, session, body, errors)
    elif skill_id == "mcp_federal_tools":
        output = await _run_mcp_federal_tools(settings, body, errors)
    elif skill_id == "skill-creator":
        output = _run_skill_creator(settings, skills)
    elif skill_id == "idea_capturer":
        output = await _run_idea_capturer(settings, session, body, errors)
    else:
        output = {"message": f"Skill {skill_id} registered; handler not wired yet."}

    review_id: str | None = None
    skip_skill_review = skill_id == "idea_capturer" and bool(output.get("review_id"))
    if skip_skill_review:
        review_id = str(output["review_id"])
    elif output and not errors:
        record = await create_review_record(
            session,
            entity_type="skill_run",
            entity_id=f"{run_id}:{skill_id}",
            trust_level=TrustLevel.CANDIDATE,
            provenance=[{"kind": "skill", "ref": skill_id, "excerpt": str(output)[:300]}],
        )
        review_id = str(record.id)

    status = "completed" if not errors else "partial"
    run = CapabilityRun(
        id=uuid.UUID(run_id),
        skill_id=skill_id,
        status="pending_review" if review_id else status,
        transcript={"output": output, "errors": errors, "input": body},
    )
    session.add(run)
    await session.flush()

    return SkillRunResult(
        skill_id=skill_id,
        run_id=run_id,
        status=status,
        output=output,
        review_id=review_id,
        errors=errors,
    )


async def _run_clew_intel(
    settings: Settings,
    session: AsyncSession,
    body: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    mode = str(body.get("mode") or "snapshot")
    stats = await pg_queries.get_intel_stats(session)
    if not stats.get("prime_awards_ready") or stats.get("prime_award_count", 0) == 0:
        errors.append("Intel tables empty — run migration first")
        return {"mode": mode}

    facet_query = facet_from_payload(body)
    if facet_query and mode in ANALYSIS_MODES:
        out = await run_facet_analysis(session, facet_query, mode, limit=int(body.get("limit", 12)))
        if out.get("error"):
            errors.append(str(out["error"]))
        out["facet_summary"] = describe_query(facet_query)
        return out

    naics = str(body.get("naics") or settings.default_naics)
    if mode == "expiring":
        rows = await pg_queries.get_expiring_contracts(
            session, [naics], months_ahead=int(body.get("months_ahead", 24)), limit=int(body.get("limit", 10))
        )
        return {"naics": naics, "mode": mode, "contracts": rows}
    if mode == "market":
        return await pg_queries.get_market_summary(session, [naics])
    return await pg_queries.get_quick_opportunity_snapshot(session, naics)


async def _run_mcp_federal_tools(
    settings: Settings,
    body: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    server = body.get("server")
    tool = body.get("tool")
    if not server or not tool:
        errors.append("server and tool required")
        return {}
    mcp = MCPService(settings)
    result = await mcp.invoke(server, tool, body.get("arguments") or {})
    if not result.get("ok"):
        errors.append(result.get("error") or "MCP invoke failed")
    return result


async def _run_idea_capturer(
    settings: Settings,
    session: AsyncSession,
    body: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    dump = str(body.get("dump") or "").strip()
    try:
        result = await capture_idea_to_vault(
            settings,
            session,
            dump=dump,
            tags=str(body.get("tags") or ""),
            context_note=str(body.get("context") or ""),
        )
    except IdeaCaptureError as exc:
        errors.append(str(exc))
        return {"skill": "idea_capturer"}

    if not result.gate.ok:
        errors.extend(result.gate.issues)

    return {
        "skill": "idea_capturer",
        "candidate_path": result.candidate_path,
        "title": result.title,
        "review_id": str(result.review_id) if result.review_id else None,
        "inbox_href": result.inbox_href,
        "vault_maintainer_gate": result.gate.ok,
        "gate_issues": list(result.gate.issues),
        "title_provider": result.title_provider,
        "polish_provider": result.polish_provider,
    }


def _run_skill_creator(settings: Settings, skills: dict[str, SkillDescriptor]) -> dict[str, Any]:
    root = settings.resolve(settings.skills_root)
    return {
        "skills_root": str(root),
        "existing_skills": sorted(skills.keys()),
        "scaffold_hint": "Create skills/<name>/SKILL.md with YAML frontmatter (name, description).",
    }