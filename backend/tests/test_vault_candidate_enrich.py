"""Phase 15f — Clew/research enrich append to candidate (TDD)."""

import json
import uuid
from pathlib import Path

import pytest

from thread.config import Settings
from thread.services.vault_candidate_enrich import (
    CandidateEnrichError,
    append_candidate_enrichment,
    build_clew_enrichment,
    build_research_enrichment,
    infer_auto_enrich,
)
from thread.services.vault_write import load_candidate_note, write_candidate_note


def _seed_vault(vault: Path) -> None:
    vault.mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n\n## Pages\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    (vault / "generated-projections" / "sandbox").mkdir(parents=True)


def test_research_enrichment_builds_from_saved_run(tmp_path: Path):
    settings = Settings(thread_state_dir=tmp_path / ".thread")
    run_id = str(uuid.uuid4())
    runs = settings.resolve(settings.thread_state_dir) / "research"
    runs.mkdir(parents=True)
    (runs / f"{run_id}.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "query": "Army cyber spend",
                "findings": [{"title": "Hit A", "summary": "Summary A", "provenance": []}],
                "interpretation": "Synthesis line.",
            }
        ),
        encoding="utf-8",
    )
    title, body, ref = build_research_enrichment(settings, run_id=run_id)
    assert "Army cyber" in title
    assert "Hit A" in body
    assert "Synthesis" in body
    assert run_id in ref


def test_clew_enrichment_stub_includes_facets():
    title, body, ref = build_clew_enrichment(mode="spend_trend", agency="Department of the Army")
    assert "spend_trend" in title
    assert "Army" in body
    assert "clew:" in ref


def test_append_enrichment_stays_candidate_trust(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault)
    created = write_candidate_note(
        settings,
        name="Enrich Target",
        body="Base content.",
        citations="source:test",
        source="test",
    )
    append_candidate_enrichment(
        settings,
        created.path,
        title="Research — test",
        body="- Finding one",
        source="research",
        provenance_ref="research:abc",
    )
    loaded = load_candidate_note(settings, created.path)
    assert "Finding one" in loaded["body"]
    assert "Enrichment candidate" in (vault / created.path).read_text(encoding="utf-8")
    assert "trust: candidate" in (vault / created.path).read_text(encoding="utf-8")


def test_infer_auto_enrich_picks_source_by_page_type():
    clew = infer_auto_enrich(page_type="concept", title="Army CIO")
    assert clew.source == "clew"
    research = infer_auto_enrich(page_type="agency", title="Department of the Army")
    assert research.source == "research"
    assert "Army" in research.research_query


def test_vault_review_template_wires_one_click_enrich():
    from pathlib import Path

    text = Path("src/thread/ui/templates/partials/knowledge_vault_review.html").read_text(encoding="utf-8")
    assert "/partials/knowledge/candidate-enrich" in text
    assert "Add context" in text
    assert "capture-studio-advanced-toolbar" in text


def test_research_enrichment_requires_run_or_query(tmp_path: Path):
    settings = Settings(thread_state_dir=tmp_path / ".thread")
    with pytest.raises(CandidateEnrichError):
        build_research_enrichment(settings, run_id=None, query=None)