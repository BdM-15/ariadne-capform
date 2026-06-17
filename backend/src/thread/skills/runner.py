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
from thread.mcp.service import MCPService
from thread.services.review_gate import create_review_record
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

    if skill_id == "datarepublican_intel":
        output = await _run_datarepublican_intel(settings, session, body, errors)
    elif skill_id == "mcp_federal_tools":
        output = await _run_mcp_federal_tools(settings, body, errors)
    elif skill_id == "skill-creator":
        output = _run_skill_creator(settings, skills)
    else:
        output = {"message": f"Skill {skill_id} registered; handler not wired yet."}

    review_id: str | None = None
    if output and not errors:
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


async def _run_datarepublican_intel(
    settings: Settings,
    session: AsyncSession,
    body: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    naics = str(body.get("naics") or settings.default_naics)
    mode = str(body.get("mode") or "snapshot")
    stats = await pg_queries.get_intel_stats(session)
    if not stats.get("prime_awards_ready") or stats.get("prime_award_count", 0) == 0:
        errors.append("Intel tables empty — run migration first")
        return {"naics": naics, "mode": mode}

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


def _run_skill_creator(settings: Settings, skills: dict[str, SkillDescriptor]) -> dict[str, Any]:
    root = settings.resolve(settings.skills_root)
    return {
        "skills_root": str(root),
        "existing_skills": sorted(skills.keys()),
        "scaffold_hint": "Create skills/<name>/SKILL.md with YAML frontmatter (name, description).",
    }