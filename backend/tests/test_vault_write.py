import uuid
from pathlib import Path

import pytest

from thread.config import Settings
from thread.db.models import CapabilityRun, ReviewRecord
from thread.services.vault_write import (
    VaultWriteError,
    append_trusted_page,
    ingest_approved_review,
    load_candidate_note,
    save_candidate_note,
    write_candidate_note,
)


def _seed_vault(vault: Path) -> None:
    vault.mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n\n## Catalog\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    (vault / "entities" / "agencies").mkdir(parents=True)


def test_write_candidate_note(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault)
    result = write_candidate_note(
        settings,
        name="Test Synthesis",
        body="Body text",
        citations="source:test",
    )
    assert result.created
    assert result.path.startswith("generated-projections/sandbox/")
    page = vault / result.path
    assert page.is_file()
    text = page.read_text(encoding="utf-8")
    assert "trust: candidate" in text
    assert "Test Synthesis" in text
    assert "## Pages" in (vault / "index.md").read_text(encoding="utf-8")


def test_save_candidate_note_updates_body(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault)
    created = write_candidate_note(
        settings,
        name="Original",
        body="First body",
        citations="source:test",
        source="test",
    )
    save_candidate_note(
        settings,
        created.path,
        name="Renamed",
        body="Edited body with [[capture-llm-wiki]]",
        page_type="concept",
        related=["capture-llm-wiki", "milestone_1"],
    )
    loaded = load_candidate_note(settings, created.path)
    assert loaded["name"] == "Renamed"
    assert loaded["page_type"] == "concept"
    assert "Edited body" in loaded["body"]
    assert "capture-llm-wiki" in loaded["related"]
    text = (vault / created.path).read_text(encoding="utf-8")
    assert "trust: candidate" in text
    assert "Vault Inbox" in text


def test_save_candidate_note_rejects_trusted_path(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault)
    with pytest.raises(VaultWriteError, match="generated-projections"):
        save_candidate_note(settings, "entities/agencies/x.md", name="X", body="nope")


def test_append_trusted_page_and_dedup(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault)
    review_id = str(uuid.uuid4())
    first = append_trusted_page(
        settings,
        "entities/agencies/army.md",
        name="Army",
        page_type="agency",
        page_id="entity-agency-army",
        review_id=review_id,
        citations="source:clew_intel",
        section_body="- $10M obligation path",
        related=["capture-llm-wiki"],
    )
    assert first.created
    second = append_trusted_page(
        settings,
        "entities/agencies/army.md",
        name="Army",
        page_type="agency",
        page_id="entity-agency-army",
        review_id=review_id,
        citations="source:clew_intel",
        section_body="- duplicate",
        related=[],
    )
    assert second.skipped_dedup


def test_protected_path_rejected(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault)
    with pytest.raises(VaultWriteError, match="Protected"):
        append_trusted_page(
            settings,
            "foundation/capture-llm-wiki.md",
            name="Hack",
            page_type="meta",
            page_id="x",
            review_id=str(uuid.uuid4()),
            citations="",
            section_body="nope",
        )


@pytest.mark.asyncio
async def test_ingest_clew_skill_run(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault)
    run_id = uuid.uuid4()
    review_id = uuid.uuid4()
    record = ReviewRecord(
        id=review_id,
        entity_type="skill_run",
        entity_id=f"{run_id}:clew_intel",
        trust_level="trusted",
        review_state="accepted",
    )
    cap_run = CapabilityRun(
        id=run_id,
        skill_id="clew_intel",
        status="pending_review",
        transcript={
            "input": {"agency": "Department of Army", "mode": "money_flow"},
            "output": {
                "mode": "money_flow",
                "facet_summary": "agency: Army",
                "summary": "Top paths",
                "flows": [
                    {"recipient": "Acme Corp", "agency": "Department of Army", "millions": 12.5, "actions": 3}
                ],
            },
        },
    )

    class _Session:
        async def get(self, _model, key):
            return cap_run if key == run_id else None

    result = await ingest_approved_review(_Session(), settings, record)
    assert result is not None
    assert len(result.paths) >= 2
    assert (vault / "relationships").exists()
    assert any("clew-money-flow" in p.replace("_", "-") for p in result.paths)