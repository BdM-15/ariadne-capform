"""Plain-language guides for the Knowledge vault page."""

from __future__ import annotations

from typing import Any

KNOWLEDGE_GUIDES: dict[str, dict[str, Any]] = {
    "knowledge": {
        "title": "Knowledge vault",
        "accent": "magenta",
        "purpose": (
            "Your capture team's long-term memory — Obsidian-style markdown pages for agencies, "
            "competitors, bid-fit capabilities, pursuit notes, and briefing-packet doctrine. "
            "Trusted content compounds here after you approve items on /review."
        ),
        "when": (
            "Morning bid-fit checks, competitor positioning, agency relationship notes, "
            "or validating what the platform already knows before you Track a pursuit."
        ),
        "output": (
            "Browsable wiki pages with wikilinks and frontmatter. Clew, Pulse research, and skill "
            "runs queue candidates — only review-approved writes land in trusted vault paths."
        ),
        "context_impact": (
            "Vault lives at knowledge/thread/ (gitignored locally). Sandbox mode quarantines test "
            "writes under generated-projections/sandbox/. Toggle sandbox on Settings → Knowledge vault."
        ),
        "how_to_use": [
            "Use the tree on the left to browse folders — entities/, global/domain_intel/, pursuits/, etc.",
            "Click a .md file to preview rendered markdown; .json pages show raw structured data.",
            "Run Lint under Vault operations to see broken links, orphans, or test contamination.",
            "Use Test ingest to draft a candidate — it appears in Vault review below (Approve or Reject).",
            "Approve on /review to promote trusted ingests; semantic links compound on each approved write.",
            "Turn off sandbox in Settings when you're done experimenting and ready to maintain production vault.",
        ],
        "tips": [
            "Browse is read-only — all writes go through vault ops, test ingest, or review approve.",
            "Packet-field pages should link to concepts, not each other — use Semantic + clean pass if mesh creeps back.",
            "Pair with Pulse Knowledge digest for morning bid-fit; deep edits happen here.",
            "Vault ops Guide explains each button — start with Lint (dry) before any apply action.",
        ],
    },
    "vault_ops": {
        "title": "Vault operations",
        "accent": "cyan",
        "purpose": (
            "Maintain and grow the knowledge graph — lint for problems, preview fixes dry-run, "
            "apply repairs and semantic cross-links, and test-ingest candidates without touching trusted pages."
        ),
        "when": (
            "After bulk imports, before a capture sprint, when lint reports issues, or when sandbox-testing "
            "a new ingest pipeline."
        ),
        "output": (
            "Lint counts and summaries; dry-run previews; applied passes update markdown Related sections, "
            "frontmatter, and hub links. Test ingest creates sandbox notes and queues /review."
        ),
        "context_impact": (
            "With sandbox on: batch apply (Repair, Semantic apply) is blocked — use dry runs and test ingest only. "
            "THREAD_ALLOW_TEST_PROMOTE on Settings lets test notes promote to trusted (off by default)."
        ),
        "how_to_use": [
            "Lint — scan the whole vault; fix broken links, orphans, test-in-trusted-zone, and junk counts.",
            "Normalize (dry) — preview frontmatter and Related-section cleanup without writing files.",
            "Semantic (dry) — preview doctrine cross-links (concepts, agencies) without writing files.",
            "Repair + link (apply, sandbox off) — full pass: hub repair, link fix, semantic links, normalize.",
            "Semantic (apply, sandbox off) — write semantic Related links and rebuild index catalog.",
            "Test ingest — write a sandbox candidate with test markers; optional queue to /review for promote.",
        ],
        "tips": [
            "Always Lint first — know the issue count before applying anything.",
            "Dry runs are safe in sandbox or production; apply buttons need sandbox off.",
            "Test ingest page types: synthesis, concept, agency, competitor — pick what you're drafting.",
            "Review approve runs ingest with semantic stats; failures surface as flash on the review panel.",
        ],
    },
}

VAULT_OP_TIPS: dict[str, str] = {
    "lint": "Scan for broken wikilinks, orphan pages, test notes in trusted folders, and packet-field mesh.",
    "normalize_dry": "Preview frontmatter fixes and Related-section cleanup — no files written.",
    "semantic_dry": "Preview semantic cross-links from doctrine — no files written.",
    "repair": "Full repair: fix hubs and links, run semantic pass, normalize — writes to live vault.",
    "semantic_apply": "Append semantic Related links across the vault and rebuild the link index.",
    "test_ingest": "Write a sandbox candidate (test markers) and optionally queue /review — not trusted until approved.",
}


def guide_for_knowledge() -> dict[str, Any]:
    return dict(KNOWLEDGE_GUIDES["knowledge"])


def guide_for_vault_ops() -> dict[str, Any]:
    return dict(KNOWLEDGE_GUIDES["vault_ops"])