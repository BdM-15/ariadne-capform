"""Vault Inbox plain-language card helpers."""

from thread.services.vault_inbox_display import (
    build_intent_line,
    display_title,
    extract_dump_snippet,
    page_type_label,
    promote_destination_label,
)


def test_page_type_label():
    assert page_type_label("synthesis") == "Knowledge note"
    assert page_type_label("competitor") == "Competitor profile"


def test_extract_dump_snippet_strips_boilerplate():
    body = (
        "# Title\n\n"
        "> Candidate — approve in Knowledge\n\n"
        "> [!note] Candidate draft\n\n"
        "I want to create a knowledge repository from reviewer feedback.\n\n"
        "## Related\n- none\n"
    )
    assert "knowledge repository" in extract_dump_snippet(body)
    assert "Related" not in extract_dump_snippet(body)


def test_build_intent_line():
    line = build_intent_line(
        page_type="synthesis",
        title="Reviewer feedback repo",
        promote_summary="New trusted page",
    )
    assert "Knowledge note" in line


def test_promote_destination_label():
    assert promote_destination_label("global/domain_intel/synthesis/foo.md") == "global / domain_intel"


def test_display_title_humanizes_slug_stem():
    title = display_title(
        "i-want-to-create-a-knowledge-repository-from-reviewer-feedback-and-anony-2026-06-19",
        candidate_path="generated-projections/sandbox/foo.md",
    )
    assert "Knowledge Repository" in title or "Reviewer" in title