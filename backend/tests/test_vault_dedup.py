"""Phase 15d — vault dedup hints + merge target options."""

from pathlib import Path

import pytest

from thread.config import Settings
from thread.services.vault_dedup import (
    DedupHint,
    MergeTargetOption,
    build_merge_target_options,
    find_dedup_hints,
    patch_provenance_target,
    resolve_auto_promote_target,
    validate_promote_target,
)
from thread.services.vault_write import VaultWriteError, append_trusted_page, write_candidate_note


def _seed_vault(vault: Path) -> None:
    vault.mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n\n## Pages\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    (vault / "entities" / "agencies").mkdir(parents=True)
    (vault / "generated-projections" / "sandbox").mkdir(parents=True)


def test_find_dedup_hints_name_match(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    append_trusted_page(
        Settings(knowledge_vault_path=vault),
        "entities/agencies/army-cio.md",
        name="Army CIO",
        page_type="agency",
        page_id="entity-agency-army-cio",
        review_id="00000000-0000-0000-0000-000000000001",
        citations="source:test",
        section_body="Existing agency intel.",
        related=[],
    )
    settings = Settings(knowledge_vault_path=vault)
    hints = find_dedup_hints(
        settings,
        candidate_rel="generated-projections/sandbox/army-cio-2026-06-19.md",
        meta={"name": "Army CIO", "type": "agency"},
        body="New candidate about Army CIO.",
        default_target="entities/agencies/army-cio-2026-06-19.md",
    )
    paths = {h.rel_path for h in hints}
    assert "entities/agencies/army-cio.md" in paths
    assert any(h.score >= 80 for h in hints)


def test_find_dedup_hints_default_path_exists(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    target = vault / "global" / "domain_intel" / "synthesis"
    target.mkdir(parents=True)
    (target / "cyber-trend.md").write_text(
        "---\nname: Cyber Trend\ntype: synthesis\ntrust: trusted\n---\n# Cyber\n",
        encoding="utf-8",
    )
    settings = Settings(knowledge_vault_path=vault)
    default = "global/domain_intel/synthesis/cyber-trend.md"
    hints = find_dedup_hints(
        settings,
        candidate_rel="generated-projections/sandbox/cyber-trend.md",
        meta={"name": "Cyber Trend", "type": "synthesis"},
        body="Update",
        default_target=default,
    )
    assert hints[0].rel_path == default
    assert hints[0].score == 100


def test_resolve_auto_promote_target_prefers_top_dedup_hint():
    hints = (
        DedupHint(
            rel_path="entities/agencies/army-cio.md",
            title="Army CIO",
            page_type="agency",
            reason="name match",
            score=90,
        ),
    )
    options = (
        MergeTargetOption(
            rel_path="entities/agencies/new-army-cio.md",
            label="Default",
            is_default=True,
            from_dedup=False,
        ),
    )
    path, summary = resolve_auto_promote_target("entities/agencies/new-army-cio.md", hints, options)
    assert path == "entities/agencies/army-cio.md"
    assert "Army CIO" in summary


def test_resolve_auto_promote_target_falls_back_to_default():
    options = (
        MergeTargetOption(
            rel_path="global/foo.md",
            label="Default",
            is_default=True,
            from_dedup=False,
        ),
    )
    path, _ = resolve_auto_promote_target("global/foo.md", (), options)
    assert path == "global/foo.md"


def test_build_merge_target_options_includes_default_and_dedup(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault)
    hints = find_dedup_hints(
        settings,
        candidate_rel="generated-projections/sandbox/x.md",
        meta={"name": "Army CIO", "type": "agency"},
        body="text",
        default_target="entities/agencies/new-army-cio.md",
    )
    options = build_merge_target_options("entities/agencies/new-army-cio.md", hints)
    assert options[0].is_default
    assert options[0].rel_path == "entities/agencies/new-army-cio.md"


def test_validate_promote_target_rejects_generated(tmp_path: Path):
    with pytest.raises(VaultWriteError, match="generated-projections"):
        validate_promote_target("generated-projections/sandbox/x.md")


def test_patch_provenance_target():
    updated = patch_provenance_target(
        [{"kind": "vault_candidate", "ref": "generated-projections/x.md", "target": ""}],
        "entities/agencies/foo.md",
    )
    assert updated[0]["target"] == "entities/agencies/foo.md"


def test_promote_uses_patched_target(tmp_path: Path):
    import uuid

    from thread.db.models import ReviewRecord
    from thread.services.vault_write import promote_vault_candidate

    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault)
    existing = append_trusted_page(
        settings,
        "entities/agencies/merge-here.md",
        name="Merge Here",
        page_type="agency",
        page_id="entity-merge-here",
        review_id=str(uuid.uuid4()),
        citations="source:test",
        section_body="Original.",
        related=[],
    )
    created = write_candidate_note(
        settings,
        name="Merge Candidate",
        body="Candidate section.",
        page_type="agency",
        citations="source:test",
        source="test",
    )
    record = ReviewRecord(
        id=uuid.uuid4(),
        entity_type="vault_candidate",
        entity_id=created.path,
        trust_level="candidate",
        review_state="pending_review",
        provenance=patch_provenance_target(
            [{"kind": "vault_candidate", "ref": created.path, "target": "entities/agencies/other.md"}],
            existing.path,
        ),
    )
    result = promote_vault_candidate(settings, record)
    assert result is not None
    assert existing.path in result.paths
    merged = (vault / existing.path).read_text(encoding="utf-8")
    assert "Candidate section" in merged