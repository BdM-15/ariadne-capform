from pathlib import Path

from thread.config import Settings
from thread.services.vault_lint import lint_vault
from thread.services.vault_semantic_graph import apply_semantic_crosslinks


def _semantic_vault(vault: Path) -> None:
    vault.mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")

    caps = vault / "global" / "domain_intel" / "capabilities"
    caps.mkdir(parents=True)
    (caps / "cybersecurity-capability.md").write_text(
        """---
name: Cybersecurity Capability
type: capability
id: capability-cybersecurity
trust: trusted
summary: CMMC NIST DFARS cybersecurity compliance for federal contracts
---
# Cybersecurity
Federal cybersecurity compliance posture.
""",
        encoding="utf-8",
    )
    (caps / "data-analytics-capability.md").write_text(
        """---
name: Data Analytics Capability
type: capability
id: capability-data-analytics
trust: trusted
summary: Analytics engineering digital twin platforms
---
# Data analytics
""",
        encoding="utf-8",
    )

    concepts = vault / "global" / "global_wiki" / "capture" / "concepts"
    concepts.mkdir(parents=True)
    (concepts / "dfars-cybersecurity-requirements.md").write_text(
        """---
name: DFARS Cybersecurity Requirements
type: concept
id: concept-dfars-cyber
trust: trusted
---
# DFARS
Defense federal acquisition regulation supplement cybersecurity clauses.
""",
        encoding="utf-8",
    )
    (concepts / "price-to-win-analysis.md").write_text(
        """---
name: Price to Win Analysis
type: concept
id: concept-ptw
trust: trusted
---
# PTW
Pricing strategy for competitive bids.
""",
        encoding="utf-8",
    )

    de = vault / "data-elements"
    de.mkdir(parents=True)
    (de / "competitive_landscape_summary.md").write_text(
        """---
name: Competitive Landscape
type: data-element
id: de-competitive-landscape
trust: trusted
---
# Competitive landscape
Packet field for competitive position section.
""",
        encoding="utf-8",
    )


def test_semantic_links_cyber_keyword_cluster(tmp_path: Path):
    vault = tmp_path / "vault"
    _semantic_vault(vault)
    settings = Settings(knowledge_vault_path=vault)

    report = apply_semantic_crosslinks(settings, dry_run=False)
    assert report.links_added > 0
    assert report.pages_updated > 0

    cyber_text = (vault / "global" / "domain_intel" / "capabilities" / "cybersecurity-capability.md").read_text(
        encoding="utf-8"
    )
    assert "[[dfars-cybersecurity-requirements]]" in cyber_text

    dfars_text = (vault / "global" / "global_wiki" / "capture" / "concepts" / "dfars-cybersecurity-requirements.md").read_text(
        encoding="utf-8"
    )
    assert "[[cybersecurity-capability]]" in dfars_text


def test_semantic_dry_run_no_writes(tmp_path: Path):
    vault = tmp_path / "vault"
    _semantic_vault(vault)
    settings = Settings(knowledge_vault_path=vault)
    before = (vault / "global" / "domain_intel" / "capabilities" / "cybersecurity-capability.md").read_text(
        encoding="utf-8"
    )

    report = apply_semantic_crosslinks(settings, dry_run=True)
    assert report.dry_run
    after = (vault / "global" / "domain_intel" / "capabilities" / "cybersecurity-capability.md").read_text(
        encoding="utf-8"
    )
    assert before == after


def test_data_element_links_to_section_concepts(tmp_path: Path):
    vault = tmp_path / "vault"
    _semantic_vault(vault)
    concepts = vault / "global" / "global_wiki" / "capture" / "concepts"
    (concepts / "competitor-posture.md").write_text(
        """---
name: Competitor Posture
type: concept
id: concept-competitor-posture
trust: trusted
---
# Competitor posture
""",
        encoding="utf-8",
    )
    settings = Settings(knowledge_vault_path=vault)
    apply_semantic_crosslinks(settings, dry_run=False)
    text = (vault / "data-elements" / "competitive_landscape_summary.md").read_text(encoding="utf-8")
    assert "[[competitor-posture]]" in text
    assert "[[price-to-win-analysis]]" not in text


def test_semantic_pass_keeps_lint_clean(tmp_path: Path):
    vault = tmp_path / "vault"
    _semantic_vault(vault)
    settings = Settings(knowledge_vault_path=vault)
    apply_semantic_crosslinks(settings, dry_run=False)
    lint = lint_vault(settings)
    broken = [i for i in lint.issues if i.code == "broken_link"]
    assert broken == []