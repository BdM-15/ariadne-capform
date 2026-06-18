from pathlib import Path

from thread.bootstrap.vault_seed import ensure_vault_seed
from thread.config import Settings
from thread.services.knowledge_digest import (
    _excerpt_from_markdown,
    _parse_frontmatter,
    build_knowledge_digest_widget,
)


def test_parse_frontmatter_and_excerpt():
    md = """---
name: "Cyber Capability"
type: "capability"
---

# Cyber Capability

We deliver enterprise SOC and zero-trust engineering for federal clients.
"""
    meta = _parse_frontmatter(md)
    assert meta["name"] == "Cyber Capability"
    excerpt = _excerpt_from_markdown(md)
    assert "SOC" in excerpt


def test_build_knowledge_digest_from_vault(tmp_path: Path):
    vault = tmp_path / "vault"
    ref = tmp_path / "ref"
    ref.mkdir()
    (ref / "briefing_packet").mkdir()
    (ref / "briefing_packet" / "BRIEFING_PACKET_DATA_DICTIONARY.md").write_text("# d\n", encoding="utf-8")

    seed = tmp_path / "seed"
    cap = seed / "global" / "domain_intel" / "capabilities"
    cap.mkdir(parents=True)
    (cap / "cloud-services.md").write_text(
        """---
name: "Cloud Services PP"
---
# Cloud Services

FedRAMP-aligned cloud migration and DevSecOps for civilian agencies.
""",
        encoding="utf-8",
    )

    settings = Settings(
        knowledge_vault_path=vault,
        knowledge_seed_source=seed,
        reference_docs_root=ref,
    )
    ensure_vault_seed(settings)

    widget = build_knowledge_digest_widget(settings)
    assert widget.vault_ready is True
    assert widget.capability_count >= 1
    assert widget.has_domain_intel is True
    titles = [i.title for i in widget.items]
    assert any("Cloud" in t or "Domain Intel" in t for t in titles)
    cap_items = [i for i in widget.items if i.kind == "capability"]
    assert cap_items
    assert "FedRAMP" in cap_items[0].excerpt or "cloud" in cap_items[0].excerpt.lower()


def test_build_knowledge_digest_empty_vault(tmp_path: Path):
    vault = tmp_path / "empty_vault"
    vault.mkdir()
    settings = Settings(knowledge_vault_path=vault)
    widget = build_knowledge_digest_widget(settings)
    assert widget.vault_ready is True
    assert widget.items == ()
    assert widget.has_domain_intel is False