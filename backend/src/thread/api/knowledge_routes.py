from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from thread.config import Settings, get_settings
from thread.domain.schemas import VaultListingOut, VaultPageOut
from thread.services.knowledge import KnowledgeVaultError, list_vault_entries, read_vault_page

router = APIRouter(prefix="/knowledge/vault", tags=["knowledge"])


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