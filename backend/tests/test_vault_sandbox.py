import uuid
from pathlib import Path

import pytest

from thread.config import Settings
from thread.db.models import ReviewRecord
from thread.services.vault_sandbox import SANDBOX_PREFIX, VaultSandboxError, assert_batch_mutation_allowed
from thread.services.vault_write import (
    VaultWriteError,
    append_trusted_page,
    promote_vault_candidate,
    write_candidate_note,
)


def _seed_vault(vault: Path) -> None:
    vault.mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n\n## Pages\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    (vault / "generated-projections" / "sandbox").mkdir(parents=True)


def test_source_test_writes_to_sandbox(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault)
    result = write_candidate_note(
        settings,
        name="Fixture Note",
        body="sandbox body",
        citations="source:test",
    )
    assert result.path.startswith(SANDBOX_PREFIX)
    text = (vault / result.path).read_text(encoding="utf-8")
    assert "trust: candidate" in text
    assert "test" in text.lower()


def test_sandbox_mode_blocks_trusted_write(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault, vault_sandbox_mode=True)
    with pytest.raises(VaultWriteError, match="sandbox mode"):
        append_trusted_page(
            settings,
            "entities/agencies/army.md",
            name="Army",
            page_type="agency",
            page_id="entity-agency-army",
            review_id=str(uuid.uuid4()),
            citations="source:clew_intel",
            section_body="test",
        )


def test_sandbox_mode_blocks_batch_repair(tmp_path: Path):
    settings = Settings(knowledge_vault_path=tmp_path / "vault", vault_sandbox_mode=True)
    with pytest.raises(VaultSandboxError, match="batch"):
        assert_batch_mutation_allowed(settings)


def test_test_candidate_cannot_promote_without_override(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault)
    write_candidate_note(
        settings,
        name="Promote Block",
        body="body",
        citations="source:test",
    )
    rel = next(vault.rglob("sandbox/*.md"))
    record = ReviewRecord(
        id=uuid.uuid4(),
        entity_type="vault_candidate",
        entity_id=str(rel.relative_to(vault)).replace("\\", "/"),
        trust_level="trusted",
        review_state="accepted",
        provenance=[{"kind": "vault_candidate", "ref": str(rel.relative_to(vault)).replace("\\", "/")}],
    )
    with pytest.raises(VaultWriteError, match="Test-tagged"):
        promote_vault_candidate(settings, record)