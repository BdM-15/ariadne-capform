from pathlib import Path

from thread.bootstrap.vault_seed import ensure_vault_seed
from thread.config import Settings
from thread.domain.packet_field_seed import PACKET_FIELD_SEEDS


def _minimal_reference(ref: Path) -> None:
    ref.mkdir(parents=True)
    (ref / "briefing_packet").mkdir()
    (ref / "briefing_packet" / "BRIEFING_PACKET_DATA_DICTIONARY.md").write_text("# dict\n", encoding="utf-8")


def test_ensure_vault_seed_idempotent(tmp_path: Path):
    vault = tmp_path / "vault"
    ref = tmp_path / "ref"
    _minimal_reference(ref)

    settings = Settings(
        knowledge_vault_path=vault,
        knowledge_seed_source=tmp_path / "missing_seed",
        reference_docs_root=ref,
    )

    first = ensure_vault_seed(settings)
    assert first.changed
    assert (vault / "data-elements" / "opportunity_name.md").exists()
    assert (vault / "milestones" / "milestone_1.md").exists()
    assert (vault / "log.md").exists()
    assert len(list((vault / "data-elements").glob("*.md"))) == len(PACKET_FIELD_SEEDS)

    second = ensure_vault_seed(settings)
    assert not second.changed


def test_merge_capture_insights_brain(tmp_path: Path):
    vault = tmp_path / "vault"
    seed = tmp_path / "seed"
    ref = tmp_path / "ref"
    _minimal_reference(ref)

    agency_dir = seed / "brain" / "agencies"
    agency_dir.mkdir(parents=True)
    (agency_dir / "dhs.md").write_text("# DHS\n", encoding="utf-8")

    settings = Settings(
        knowledge_vault_path=vault,
        knowledge_seed_source=seed,
        reference_docs_root=ref,
    )
    report = ensure_vault_seed(settings)
    assert (vault / "entities" / "agencies" / "dhs.md").exists()
    assert any("dhs.md" in c for c in report.created)