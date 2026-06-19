"""Vault operator actions — lint, repair, ingest helpers for Knowledge UI."""

from __future__ import annotations

from dataclasses import dataclass, field

from thread.config import Settings
from thread.services.vault_lint import lint_vault, normalize_vault
from thread.services.vault_ofm import clean_packet_field_links
from thread.services.vault_repair import repair_vault_full
from thread.services.vault_sandbox import VaultSandboxError, assert_batch_mutation_allowed
from thread.services.vault_semantic_graph import apply_semantic_crosslinks


@dataclass
class VaultOpsResult:
    action: str
    ok: bool
    applied: bool
    summary: str
    details: dict = field(default_factory=dict)

    def to_context(self) -> dict:
        return {
            "action": self.action,
            "ok": self.ok,
            "applied": self.applied,
            "summary": self.summary,
            "details": self.details,
        }


def run_vault_op(settings: Settings, action: str, *, apply: bool) -> VaultOpsResult:
    action = action.strip().lower()
    try:
        if action == "lint":
            report = lint_vault(settings).to_dict()
            issues = report.get("issue_count", 0)
            test_hits = sum(1 for i in report.get("issues", []) if i.get("code") == "test_in_trusted_zone")
            return VaultOpsResult(
                action=action,
                ok=issues == 0,
                applied=False,
                summary=f"{issues} issue(s)" + (f" · {test_hits} test contamination" if test_hits else ""),
                details=report,
            )

        if apply:
            assert_batch_mutation_allowed(settings)

        if action == "normalize":
            report = normalize_vault(settings, dry_run=not apply).to_dict()
            return VaultOpsResult(
                action=action,
                ok=True,
                applied=apply,
                summary=f"scanned {report['pages_scanned']} · fixed {report['frontmatter_fixed']}",
                details=report,
            )

        if action == "repair":
            report = repair_vault_full(settings, dry_run=not apply).to_dict()
            return VaultOpsResult(
                action=action,
                ok=True,
                applied=apply,
                summary=f"links repaired {report['links_repaired']} · semantic +{report.get('semantic_links_added', 0)}",
                details=report,
            )

        if action == "semantic":
            report = apply_semantic_crosslinks(settings, dry_run=not apply).to_dict()
            lint_after = None
            if apply:
                from thread.services.vault_lint import rebuild_index_catalog

                rebuild_index_catalog(settings)
                lint_after = lint_vault(settings).to_dict()
            return VaultOpsResult(
                action=action,
                ok=True,
                applied=apply,
                summary=f"links +{report['links_added']} on {report['pages_updated']} pages",
                details={"report": report, "lint_after": lint_after},
            )

        if action == "clean-packet":
            report = clean_packet_field_links(settings, dry_run=not apply).to_dict()
            lint_after = lint_vault(settings).to_dict() if apply else None
            return VaultOpsResult(
                action=action,
                ok=True,
                applied=apply,
                summary=f"removed {report['links_removed']} field-to-field links",
                details={"report": report, "lint_after": lint_after},
            )

        return VaultOpsResult(action=action, ok=False, applied=False, summary=f"Unknown action: {action}")

    except VaultSandboxError as exc:
        return VaultOpsResult(action=action, ok=False, applied=False, summary=str(exc))