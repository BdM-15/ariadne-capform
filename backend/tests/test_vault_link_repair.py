from pathlib import Path

from thread.config import Settings
from thread.services.vault_link_index import build_link_index, build_vault_stem_options
from thread.services.vault_lint import lint_vault
from thread.services.vault_repair import repair_vault_full


def _mini_vault(vault: Path) -> None:
    vault.mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    (vault / "foundation").mkdir(parents=True)
    (vault / "foundation" / "capture-llm-wiki.md").write_text(
        "---\nname: capture-llm-wiki\nid: foundation-capture-llm-wiki\ntype: schema\ntrust: trusted\n---\n# Schema\n",
        encoding="utf-8",
    )
    concept = vault / "global" / "global_wiki" / "capture" / "concepts"
    concept.mkdir(parents=True)
    (concept / "follow-the-money.md").write_text(
        """---
name: Follow the money
type: concept
id: concept-follow-the-money
trust: trusted
---
# Follow the money
Which [[brain/]] entries?
""",
        encoding="utf-8",
    )
    (vault / "global" / "global_wiki" / "regulations").mkdir(parents=True)
    (vault / "global" / "global_wiki" / "regulations" / "naics-code-and-size-standard-strategy.md").write_text(
        """---
name: NAICS strategy
type: concept
id: global-naics
trust: trusted
---
# NAICS
""",
        encoding="utf-8",
    )


def test_link_index_resolves_brain_alias(tmp_path: Path):
    vault = tmp_path / "vault"
    _mini_vault(vault)
    (vault / "entities").mkdir()
    (vault / "entities" / "entities.md").write_text(
        "---\nname: Entities\nid: entities-hub\ntype: meta\ntrust: trusted\naliases: brain, brain/\n---\n# Entities\n",
        encoding="utf-8",
    )
    idx = build_link_index(vault)
    assert idx.resolve("brain/") == "entities"
    assert idx.resolve("entities") == "entities"


def test_repair_fixes_broken_brain_links(tmp_path: Path):
    vault = tmp_path / "vault"
    _mini_vault(vault)
    settings = Settings(knowledge_vault_path=vault)
    report = repair_vault_full(settings, dry_run=False)
    text = (vault / "global" / "global_wiki" / "capture" / "concepts" / "follow-the-money.md").read_text(
        encoding="utf-8"
    )
    assert "[[entities]]" in text
    assert "[[brain/]]" not in text
    lint = lint_vault(settings)
    broken = [i for i in lint.issues if i.code == "broken_link"]
    assert broken == []


def test_build_vault_stem_options_lists_unique_stems(tmp_path: Path):
    vault = tmp_path / "vault"
    _mini_vault(vault)
    options = build_vault_stem_options(vault)
    stems = {option.stem for option in options}
    assert "capture-llm-wiki" in stems
    assert "follow-the-money" in stems
    assert options[0].stem == "capture-llm-wiki"