from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from thread.config import Settings, get_settings
from thread.db.session import get_db
from thread.domain.schemas import (
    VaultCandidateWriteIn,
    VaultListingOut,
    VaultPageOut,
    VaultWriteResultOut,
)
from thread.services.knowledge import KnowledgeVaultError, list_vault_entries, read_vault_page
from thread.services.vault_lint import lint_vault, normalize_vault
from thread.services.vault_repair import repair_vault_full
from thread.services.vault_ofm import clean_packet_field_links
from thread.services.vault_sandbox import VaultSandboxError, assert_batch_mutation_allowed
from thread.services.vault_semantic_graph import apply_semantic_crosslinks

from thread.services.vault_write import (
    VaultWriteError,
    queue_vault_candidate_review,
    write_candidate_note,
)

router = APIRouter(prefix="/knowledge/vault", tags=["knowledge"])


def _batch_guard(settings: Settings) -> None:
    try:
        assert_batch_mutation_allowed(settings)
    except VaultSandboxError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.get("", response_model=VaultListingOut)
async def vault_root(settings: Settings = Depends(get_settings)) -> VaultListingOut:
    vault = settings.resolve(settings.knowledge_vault_path)
    try:
        data = list_vault_entries(vault, "")
    except KnowledgeVaultError as exc:
        raise HTTPException(404, str(exc)) from exc
    return VaultListingOut(**data)


@router.get("/list", response_model=VaultListingOut)
async def vault_list(
    path: str = Query("", description="Relative vault path"),
    settings: Settings = Depends(get_settings),
) -> VaultListingOut:
    vault = settings.resolve(settings.knowledge_vault_path)
    try:
        data = list_vault_entries(vault, path)
    except KnowledgeVaultError as exc:
        raise HTTPException(404, str(exc)) from exc
    return VaultListingOut(**data)


@router.get("/page", response_model=VaultPageOut)
async def vault_page(
    path: str = Query(..., description="Relative path to .md or .json file"),
    settings: Settings = Depends(get_settings),
) -> VaultPageOut:
    vault = settings.resolve(settings.knowledge_vault_path)
    try:
        data = read_vault_page(vault, path)
    except KnowledgeVaultError as exc:
        raise HTTPException(404, str(exc)) from exc
    return VaultPageOut(**data)


@router.post("/candidate", response_model=VaultWriteResultOut)
async def vault_write_candidate(
    body: VaultCandidateWriteIn,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> VaultWriteResultOut:
    try:
        result = write_candidate_note(
            settings,
            name=body.name,
            body=body.body,
            page_type=body.page_type,
            citations=body.citations,
            related=body.related,
            source="api",
        )
        if body.queue_review:
            provenance_target = body.target_path
            if not provenance_target and body.page_type == "agency":
                provenance_target = f"entities/agencies/{result.path.split('/')[-1]}"
            await queue_vault_candidate_review(
                db,
                candidate_path=result.path,
                target_path=provenance_target,
                opportunity_id=body.opportunity_id,
            )
            await db.commit()
    except VaultWriteError as exc:
        raise HTTPException(400, str(exc)) from exc
    return VaultWriteResultOut(
        path=result.path,
        created=result.created,
        appended=result.appended,
        index_updated=result.index_updated,
        log_appended=result.log_appended,
        skipped_dedup=result.skipped_dedup,
    )


@router.get("/status")
async def vault_status(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "sandbox_mode": settings.vault_sandbox_mode,
        "allow_test_promote": settings.vault_allow_test_promote,
        "sandbox_prefix": "generated-projections/sandbox/",
    }


@router.get("/lint")
async def vault_lint(settings: Settings = Depends(get_settings)) -> dict:
    report = lint_vault(settings).to_dict()
    report["sandbox_mode"] = settings.vault_sandbox_mode
    return report


@router.post("/normalize")
async def vault_normalize(
    apply: bool = Query(False, description="Apply frontmatter fixes and rebuild index"),
    settings: Settings = Depends(get_settings),
) -> dict:
    if apply:
        _batch_guard(settings)
    return normalize_vault(settings, dry_run=not apply).to_dict()


@router.post("/repair")
async def vault_repair(
    apply: bool = Query(False, description="Hubs, alias map, wikilink repair, normalize, lint"),
    settings: Settings = Depends(get_settings),
) -> dict:
    if apply:
        _batch_guard(settings)
    return repair_vault_full(settings, dry_run=not apply).to_dict()


@router.post("/semantic-link")
async def vault_semantic_link(
    apply: bool = Query(False, description="Append semantic Related wikilinks across the vault"),
    settings: Settings = Depends(get_settings),
) -> dict:
    if apply:
        _batch_guard(settings)
    report = apply_semantic_crosslinks(settings, dry_run=not apply)
    out = report.to_dict()
    if apply:
        from thread.services.vault_lint import lint_vault, rebuild_index_catalog

        rebuild_index_catalog(settings)
        out["lint_after"] = lint_vault(settings).to_dict()
    return out


@router.post("/clean-packet-links")
async def vault_clean_packet_links(
    apply: bool = Query(False, description="Remove field-page-to-field-page links from data-elements/ Related"),
    settings: Settings = Depends(get_settings),
) -> dict:
    if apply:
        _batch_guard(settings)
    report = clean_packet_field_links(settings, dry_run=not apply)
    out = report.to_dict()
    if apply:
        from thread.services.vault_lint import lint_vault

        out["lint_after"] = lint_vault(settings).to_dict()
    return out