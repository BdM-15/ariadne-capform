import uuid
from pathlib import Path

import pytest

from thread.config import Settings
from thread.db.models import ReviewRecord
from thread.services.vault_lint import lint_vault, normalize_vault
from thread.services.vault_write import promote_vault_candidate, write_candidate_note


def _seed_vault(vault: Path) -> None:
    vault.mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n\n## Catalog\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    legacy = vault / "entities" / "competitors" / "legacy-corp.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        """---
name: Legacy Corp
type: competitor
id: brain-Legacy Corp-1-99
added: 2026-06-01T12:00:00
---

# Legacy Corp

Old capture-insights port.
""",
        encoding="utf-8",
    )


def test_lint_flags_legacy_id(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    report = lint_vault(Settings(knowledge_vault_path=vault))
    codes = {i.code for i in report.issues}
    assert "legacy_id" in codes
    assert report.fixable >= 1


def test_normalize_upgrades_frontmatter(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    report = normalize_vault(Settings(knowledge_vault_path=vault), dry_run=False)
    assert report.frontmatter_fixed >= 1
    text = (vault / "entities" / "competitors" / "legacy-corp.md").read_text(encoding="utf-8")
    assert "trust: trusted" in text
    assert "entity-competitor-legacy-corp" in text
    assert "## Related" in text


def test_promote_vault_candidate(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault)
    (vault / "entities" / "competitors").mkdir(parents=True, exist_ok=True)

    result = write_candidate_note(
        settings,
        name="New Intel",
        body="Candidate body paragraph.",
        page_type="competitor",
        citations="source:review • award_key:CONT_AWD_SAMPLE",
    )
    assert not result.path.startswith("generated-projections/sandbox/")
    record = ReviewRecord(
        id=uuid.uuid4(),
        entity_type="vault_candidate",
        entity_id=result.path,
        trust_level="trusted",
        review_state="accepted",
        provenance=[{"kind": "vault_candidate", "ref": result.path, "target": "entities/competitors/new-intel.md"}],
    )
    ingest = promote_vault_candidate(settings, record)
    assert ingest is not None
    target = vault / "entities" / "competitors" / "new-intel.md"
    assert target.is_file()
    assert "Candidate body paragraph" in target.read_text(encoding="utf-8")
    assert not (vault / result.path).exists()
    assert (vault / "generated-projections" / "archived").exists()