"""Bootstrap Obsidian vault from capture-insights + ariadne conventions."""

from __future__ import annotations

import shutil
from pathlib import Path

from thread.config import Settings


REQUIRED_DIRS = (
    "foundation",
    "data-elements",
    "entities",
    "relationships",
    "milestones",
    "skills-capabilities",
    "reusable-insights",
    "generated-projections",
)


def bootstrap_vault(settings: Settings) -> dict:
    vault = settings.resolve(settings.knowledge_vault_path)
    seed = settings.resolve(settings.knowledge_seed_source)
    ref = settings.resolve(settings.reference_docs_root)

    if (vault / "index.md").exists():
        return {"bootstrapped": False, "reason": "vault already exists", "path": str(vault)}

    vault.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_DIRS:
        (vault / name).mkdir(parents=True, exist_ok=True)

    if seed.exists():
        for sub in ("schema", "global/global_wiki"):
            src = seed / sub
            if src.exists():
                dest_parent = vault / "foundation" if sub == "schema" else vault / "global"
                dest_parent.mkdir(parents=True, exist_ok=True)
                if sub == "schema":
                    for f in src.glob("*.md"):
                        shutil.copy2(f, vault / "foundation" / f.name)
                else:
                    shutil.copytree(src, vault / "global" / "global_wiki", dirs_exist_ok=True)

    readme = vault / "index.md"
    readme.write_text(
        "# Ariadne's Thread Knowledge Vault\n\n"
        "Karpathy/Obsidian brain for Thread. See `docs/reference/README.md` for packet dictionaries.\n",
        encoding="utf-8",
    )

    schema_link = vault / "foundation" / "thread-wiki-schema.md"
    if not schema_link.exists() and (ref / "briefing_packet" / "BRIEFING_PACKET_DATA_DICTIONARY.md").exists():
        shutil.copy2(
            ref / "briefing_packet" / "BRIEFING_PACKET_DATA_DICTIONARY.md",
            schema_link,
        )

    return {"bootstrapped": True, "path": str(vault)}