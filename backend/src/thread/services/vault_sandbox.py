"""Vault sandbox — quarantine test writes from production knowledge."""

from __future__ import annotations

import re

from thread.config import Settings


class VaultSandboxError(Exception):
    """Raised when a vault operation would contaminate production knowledge."""


def _err(message: str) -> VaultSandboxError:
    return VaultSandboxError(message)

SANDBOX_PREFIX = "generated-projections/sandbox/"
_TEST_SOURCE_RE = re.compile(r"source:\s*test\b", re.I)


def sandbox_enabled(settings: Settings) -> bool:
    return bool(settings.vault_sandbox_mode)


def test_promote_allowed(settings: Settings) -> bool:
    return bool(settings.vault_allow_test_promote)


def is_sandbox_path(rel_path: str) -> bool:
    return rel_path.replace("\\", "/").lstrip("/").startswith(SANDBOX_PREFIX)


def is_test_marked(
    *,
    meta: dict[str, str] | None = None,
    rel_path: str = "",
    citations: str = "",
    page_id: str = "",
) -> bool:
    meta = meta or {}
    rel = rel_path.replace("\\", "/")
    if is_sandbox_path(rel):
        return True
    if rel.startswith("generated-projections/") and "sandbox" not in rel:
        pass
    cid = (page_id or meta.get("id") or "").lower()
    if cid.startswith("test-") or cid.startswith("candidate-test-"):
        return True
    cites = citations or meta.get("citations") or ""
    if _TEST_SOURCE_RE.search(cites):
        return True
    tags = meta.get("tags") or ""
    if re.search(r"\btest\b", tags, re.I):
        return True
    if meta.get("source", "").lower() == "test":
        return True
    return False


def assert_trusted_write_allowed(settings: Settings, rel_path: str) -> None:
    """Block trusted writes outside sandbox when sandbox mode is on."""
    if not sandbox_enabled(settings):
        return
    if test_promote_allowed(settings):
        return
    if is_sandbox_path(rel_path):
        return
    raise _err(
        "Vault sandbox mode is ON — trusted writes only allowed under "
        f"{SANDBOX_PREFIX} (set THREAD_ALLOW_TEST_PROMOTE=true to override)"
    )


def assert_promote_allowed(
    settings: Settings,
    *,
    meta: dict[str, str] | None = None,
    rel_path: str = "",
    citations: str = "",
) -> None:
    """Block promoting test-tagged candidates to trusted zones."""
    if not is_test_marked(meta=meta, rel_path=rel_path, citations=citations):
        return
    if test_promote_allowed(settings):
        return
    raise _err(
        "Test-tagged vault content cannot promote to trusted "
        "(source:test, test tag, or sandbox path). "
        "Set THREAD_ALLOW_TEST_PROMOTE=true only for deliberate fixture promotion."
    )


def assert_batch_mutation_allowed(settings: Settings) -> None:
    """Block whole-vault repair/semantic/normalize while sandbox mode is on."""
    if sandbox_enabled(settings) and not test_promote_allowed(settings):
        raise _err(
            "Vault sandbox mode is ON — batch vault repair/semantic/normalize "
            f"disabled on production vault. Test via {SANDBOX_PREFIX} candidates only, "
            "or disable THREAD_VAULT_SANDBOX."
        )


def sandbox_candidate_rel(slug: str, today: str) -> str:
    return f"{SANDBOX_PREFIX}{slug}-{today}.md"


def apply_test_markers(meta: dict[str, str], *, source: str = "test") -> dict[str, str]:
    out = dict(meta)
    out["trust"] = "candidate"
    out["source"] = source
    existing_tags = out.get("tags", "")
    tokens = {t.strip() for t in re.split(r"[,;]", existing_tags.strip("[]")) if t.strip()}
    tokens.update({"test", "fixture"})
    out["tags"] = ", ".join(sorted(tokens))
    cid = out.get("id", "")
    if cid and not cid.startswith("test-"):
        out["id"] = f"test-{cid.removeprefix('candidate-')}"
    elif not cid:
        out["id"] = "test-unknown"
    cites = out.get("citations", "")
    if "source:test" not in cites.lower():
        out["citations"] = f"source:test • {cites}".strip(" •") if cites else "source:test"
    return out