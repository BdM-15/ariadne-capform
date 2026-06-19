"""Phase 15e — Ollama admin polish + diff accept (TDD vertical slices)."""

import json
import uuid
from pathlib import Path

import pytest

from thread.config import Settings
from thread.services.vault_candidate_polish import (
    CandidatePolishError,
    build_polish_diff,
    ingest_polish_candidate,
    polish_candidate_note,
    rules_polish_candidate,
)
from thread.services.vault_write import load_candidate_note, write_candidate_note


def _seed_vault(vault: Path) -> None:
    vault.mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n\n## Pages\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    (vault / "generated-projections" / "sandbox").mkdir(parents=True)


@pytest.mark.asyncio
async def test_polish_returns_diff_without_writing_candidate(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault, local_admin_model_enabled=True)
    created = write_candidate_note(
        settings,
        name="Rough Note",
        body="  messy body  \n\n",
        page_type="synthesis",
        citations="source:test",
        source="test",
    )
    before_text = (vault / created.path).read_text(encoding="utf-8")

    async def _fake_complete(_settings, **_kwargs):
        payload = {
            "name": "Rough Note",
            "page_type": "concept",
            "body": "> [!note] Polished\n\nClean body.",
            "related": ["capture-llm-wiki", "milestone_1"],
        }

        class _Result:
            text = json.dumps(payload)
            provider = type("P", (), {"value": "ollama"})()
            model = "test-model"

        return _Result()

    result = await polish_candidate_note(settings, created.path, completer=_fake_complete)
    after_text = (vault / created.path).read_text(encoding="utf-8")

    assert after_text == before_text
    assert result.provider == "ollama"
    assert result.after.page_type == "concept"
    assert "Clean body" in result.after.body
    assert "capture-llm-wiki" in result.after.related
    diff = build_polish_diff(result.before, result.after)
    assert any(line.field == "page_type" and line.changed for line in diff)


def test_rules_polish_adds_capture_llm_wiki_when_related_empty(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault, local_admin_model_enabled=False)
    created = write_candidate_note(
        settings,
        name="Sparse",
        body="Body only",
        page_type="synthesis",
        citations="source:test",
        source="test",
    )
    loaded = load_candidate_note(settings, created.path)
    polished = rules_polish_candidate(loaded)
    assert "capture-llm-wiki" in polished.related


@pytest.mark.asyncio
async def test_accept_polish_applies_candidate_save(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault, local_admin_model_enabled=False)
    created = write_candidate_note(
        settings,
        name="Accept Me",
        body="before",
        page_type="synthesis",
        citations="source:test",
        source="test",
    )
    loaded = load_candidate_note(settings, created.path)
    polished = rules_polish_candidate(loaded)

    from thread.services.vault_candidate_polish import apply_polished_candidate

    apply_polished_candidate(settings, created.path, polished)
    reloaded = load_candidate_note(settings, created.path)
    assert reloaded["body"] == polished.body
    assert "capture-llm-wiki" in reloaded["related"]


def test_vault_review_template_wires_polish_actions():
    from pathlib import Path

    text = Path("src/thread/ui/templates/partials/knowledge_vault_review.html").read_text(encoding="utf-8")
    assert "/partials/knowledge/candidate-polish" in text


@pytest.mark.asyncio
async def test_polish_falls_back_to_rules_when_ollama_disabled(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault, local_admin_model_enabled=False)
    created = write_candidate_note(
        settings,
        name="Fallback",
        body="raw text",
        page_type="synthesis",
        citations="source:test",
        source="test",
    )
    result = await polish_candidate_note(settings, created.path)
    assert result.provider == "rules"
    assert "capture-llm-wiki" in result.after.related


def test_rules_polish_fixes_common_typos():
    loaded = {
        "name": "Edge Konweldge",
        "page_type": "synthesis",
        "body": "heard during ameetting about capabilitiy",
        "related": [],
    }
    polished = rules_polish_candidate(loaded)
    assert "knowledge" in polished.name.lower()
    assert "a meeting" in polished.body
    assert "capability" in polished.body


@pytest.mark.asyncio
async def test_ingest_polish_fixes_body_with_ollama(tmp_path: Path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    settings = Settings(knowledge_vault_path=vault, local_admin_model_enabled=True)
    loaded = {
        "name": "Edge Capability Note",
        "page_type": "synthesis",
        "body": "heard during ameetting from Jason Gray about konweldge",
        "related": ["capture-llm-wiki"],
    }

    async def _fake_complete(_settings, **_kwargs):
        payload = {
            "name": "Edge Capability Note",
            "body": "Heard during a meeting from Jason Gray about knowledge.",
        }

        class _Result:
            text = json.dumps(payload)
            provider = type("P", (), {"value": "ollama"})()
            model = "qwen3:8b"

        return _Result()

    polished, provider = await ingest_polish_candidate(settings, loaded, completer=_fake_complete)
    assert provider == "ollama-ingest"
    assert "meeting" in polished.body
    assert polished.page_type == "synthesis"
    assert polished.related == ("capture-llm-wiki",)


@pytest.mark.asyncio
async def test_ingest_polish_falls_back_to_rules_on_timeout():
    import httpx

    settings = Settings(local_admin_model_enabled=True)
    loaded = {
        "name": "Edge Note",
        "page_type": "synthesis",
        "body": "add to company konweldge",
        "related": [],
    }

    async def _timeout(_settings, **_kwargs):
        raise httpx.ReadTimeout("")

    polished, provider = await ingest_polish_candidate(settings, loaded, completer=_timeout)
    assert provider == "rules"
    assert "knowledge" in polished.body