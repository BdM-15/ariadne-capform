from pathlib import Path

from thread.bootstrap.vault_seed import ensure_vault_seed
from thread.config import Settings
from thread.domain.packet_field_seed import PACKET_ANSWERABLE_SEEDS


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
    assert len(list((vault / "data-elements").glob("*.md"))) == len(PACKET_ANSWERABLE_SEEDS)

    second = ensure_vault_seed(settings)
    assert not second.changed


def test_merge_domain_intel_and_training(tmp_path: Path):
    vault = tmp_path / "vault"
    seed = tmp_path / "seed"
    ref = tmp_path / "ref"
    _minimal_reference(ref)

    cap_dir = seed / "global" / "domain_intel" / "capabilities"
    cap_dir.mkdir(parents=True)
    (cap_dir / "cybersecurity-capability.md").write_text("# Cyber\n", encoding="utf-8")
    (seed / "training").mkdir(parents=True)
    (seed / "training" / "README.md").write_text("# Training\n", encoding="utf-8")

    settings = Settings(
        knowledge_vault_path=vault,
        knowledge_seed_source=seed,
        reference_docs_root=ref,
    )
    report = ensure_vault_seed(settings)
    assert (vault / "global" / "domain_intel" / "capabilities" / "cybersecurity-capability.md").exists()
    assert (vault / "training" / "README.md").exists()
    assert (vault / "training" / "datasets" / ".gitkeep").exists()
    assert (vault / "global" / "domain_intel" / "thread-role.md").exists()
    assert report.changed


def test_thread_vault_schema_and_obsidian_scaffold(tmp_path: Path):
    vault = tmp_path / "vault"
    ref = tmp_path / "ref"
    _minimal_reference(ref)
    (ref / "vault").mkdir()
    (ref / "vault" / "capture-llm-wiki.md").write_text(
        "---\nschema_version: 2\n---\n# Thread schema\n",
        encoding="utf-8",
    )
    (ref / "vault" / "OBSIDIAN_DESKTOP.md").write_text("# Obsidian\n", encoding="utf-8")
    obsidian_tpl = ref / "vault" / "obsidian"
    obsidian_tpl.mkdir()
    (obsidian_tpl / "app.json").write_text("{}", encoding="utf-8")

    settings = Settings(
        knowledge_vault_path=vault,
        knowledge_seed_source=tmp_path / "missing_seed",
        reference_docs_root=ref,
    )
    report = ensure_vault_seed(settings)
    assert (vault / "foundation" / "capture-llm-wiki.md").read_text(encoding="utf-8").startswith("---")
    assert "schema_version: 2" in (vault / "foundation" / "capture-llm-wiki.md").read_text(encoding="utf-8")
    assert (vault / "foundation" / "reference" / "obsidian-desktop.md").exists()
    assert (vault / ".obsidian" / "app.json").exists()
    assert report.changed


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