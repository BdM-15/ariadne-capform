from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings, get_settings
from thread.db.session import get_db
from thread.domain.schemas import SkillOut, SkillRunCreate, SkillRunOut
from thread.skills.registry import discover_skills
from thread.skills.runner import run_skill

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=list[SkillOut])
async def list_skills(settings: Settings = Depends(get_settings)) -> list[SkillOut]:
    skills = discover_skills(settings.resolve(settings.skills_root))
    return [
        SkillOut(id=s.id, description=s.description, path=str(s.path))
        for s in sorted(skills.values(), key=lambda x: x.id)
    ]


@router.get("/{skill_id}", response_model=SkillOut)
async def get_skill(skill_id: str, settings: Settings = Depends(get_settings)) -> SkillOut:
    skills = discover_skills(settings.resolve(settings.skills_root))
    skill = skills.get(skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    return SkillOut(id=skill.id, description=skill.description, path=str(skill.path))


@router.post("/{skill_id}/run", response_model=SkillRunOut)
async def invoke_skill(
    skill_id: str,
    payload: SkillRunCreate,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SkillRunOut:
    try:
        result = await run_skill(settings, db, skill_id, payload.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    await db.commit()
    return SkillRunOut(
        skill_id=result.skill_id,
        run_id=result.run_id,
        status=result.status,
        output=result.output,
        review_id=result.review_id,
        errors=result.errors,
    )