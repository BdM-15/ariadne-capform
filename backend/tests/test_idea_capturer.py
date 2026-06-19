"""Phase 15h — idea_capturer skill + vault_maintainer gate."""

import pytest

from thread.config import Settings
from thread.services.idea_capturer import (
    IdeaCaptureError,
    structure_fleeting_body,
    vault_maintainer_gate,
)
from thread.services.idea_capturer import capture_idea_to_vault
from thread.skills.runner import run_skill


def test_structure_fleeting_body_sections():
    body = structure_fleeting_body(idea_text="Edge compute note", context="Jason meeting", tags=("intel",))
    assert "## Idea" in body
    assert "## Context" in body
    assert "## Tags" in body
    assert "capture" in body.lower() or "Tier 1" in body


def test_vault_maintainer_gate_requires_hub():
    ok_loaded = {
        "name": "Test",
        "page_type": "synthesis",
        "body": "content",
        "related": ["capture-llm-wiki"],
        "citations": "source:idea_capturer",
    }
    gate = vault_maintainer_gate(ok_loaded)
    assert gate.ok

    bad = dict(ok_loaded, related=[])
    gate_bad = vault_maintainer_gate(bad)
    assert not gate_bad.ok
    assert any("capture-llm-wiki" in issue for issue in gate_bad.issues)


@pytest.mark.asyncio
async def test_capture_idea_to_vault_writes_and_queues(db_session, settings, tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "generated-projections" / "sandbox").mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)
    monkeypatch.setattr(settings, "local_admin_model_enabled", False)

    result = await capture_idea_to_vault(
        settings,
        db_session,
        dump="Random fleeting thought about checklist workflows",
        tags="workflow, admin",
    )
    await db_session.commit()
    assert result.candidate_path.startswith("generated-projections/")
    assert result.review_id is not None
    assert result.gate.ok
    assert "Fleeting" in result.title or "Random" in result.title or "Checklist" in result.title


@pytest.mark.asyncio
async def test_capture_idea_empty_dump_raises(db_session, settings):
    with pytest.raises(IdeaCaptureError, match="Dump required"):
        await capture_idea_to_vault(settings, db_session, dump="")


@pytest.mark.asyncio
async def test_run_skill_idea_capturer(db_session, settings, tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "generated-projections" / "sandbox").mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)
    monkeypatch.setattr(settings, "local_admin_model_enabled", False)

    result = await run_skill(
        settings,
        db_session,
        "idea_capturer",
        {"dump": "Capture this playbook idea before I forget"},
    )
    await db_session.commit()
    assert result.skill_id == "idea_capturer"
    assert result.output.get("candidate_path")
    assert result.review_id


def test_discover_idea_capturer_skill():
    from thread.skills.registry import discover_skills

    settings = Settings()
    skills = discover_skills(settings.resolve(settings.skills_root))
    assert "idea_capturer" in skills