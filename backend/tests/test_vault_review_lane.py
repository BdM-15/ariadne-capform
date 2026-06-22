"""Knowledge vault review lane — separate from Pulse intel inbox."""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from thread.config import Settings
from thread.main import create_app
from thread.services.intel_inbox import build_intel_inbox_widget
from thread.services.review_gate import create_review_record
from thread.services.vault_review_queue import build_stale_vault_review_widget, build_vault_review_widget
from thread.services.vault_write import write_candidate_note, queue_vault_candidate_review
from thread.ui.review_display import build_global_review_queue
from thread.services import opportunities as opp_svc
from thread.domain.schemas import OpportunityCreate


@pytest.fixture(autouse=True)
async def _dispose_app_engine_after_vault_review_test():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


@pytest.mark.asyncio
async def test_intel_inbox_excludes_vault_and_skill_creator(db_session, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)

    opp = await opp_svc.create_opportunity(
        db_session,
        OpportunityCreate(name=f"Inbox Filter {uuid.uuid4().hex[:6]}"),
    )
    await opp_svc.update_packet_field(
        db_session,
        opp.id,
        "opportunity_name",
        "Packet stays in inbox",
        as_candidate=True,
    )
    write_candidate_note(
        settings,
        name="Vault stays off inbox",
        body="sandbox body",
        page_type="concept",
        citations="source:test",
        source="test",
    )
    await queue_vault_candidate_review(db_session, candidate_path="generated-projections/sandbox/x.md")
    await create_review_record(
        db_session,
        entity_type="skill_run",
        entity_id=f"{uuid.uuid4()}:skill-creator",
    )
    await db_session.commit()

    widget = await build_intel_inbox_widget(db_session, settings)
    assert widget.count == 1
    assert widget.items[0].source_lane == "packet"
    assert all(i.entity_type != "vault_candidate" for i in widget.items)


@pytest.mark.asyncio
async def test_global_review_queue_excludes_vault_candidates(db_session, settings, tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)
    await create_review_record(
        db_session,
        entity_type="vault_candidate",
        entity_id="generated-projections/sandbox/test.md",
    )
    await create_review_record(
        db_session,
        entity_type="skill_run",
        entity_id=f"{uuid.uuid4()}:skill-creator",
    )
    await db_session.commit()

    items = await build_global_review_queue(db_session, settings)
    assert all(i.entity_type != "vault_candidate" for i in items)
    assert any(i.entity_type == "skill_run" for i in items)


@pytest.mark.asyncio
async def test_vault_review_widget_lists_candidates(db_session, settings, tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "generated-projections" / "sandbox").mkdir(parents=True)
    candidate = vault / "generated-projections" / "sandbox" / "note-2026-06-18.md"
    candidate.write_text(
        "---\nname: Test Note\ntype: concept\nid: test-note\ncitations: source:test\n---\n# Test Note\n\nBody here.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)
    await create_review_record(
        db_session,
        entity_type="vault_candidate",
        entity_id="generated-projections/sandbox/note-2026-06-18.md",
    )
    await db_session.commit()

    widget = await build_vault_review_widget(db_session, settings)
    match = [i for i in widget.test_items if i.title == "Test Note"]
    assert len(match) == 1
    assert "Body here" in match[0].body_preview
    assert match[0].is_test is True


def test_knowledge_page_has_capture_studio_mount():
    client = TestClient(create_app())
    res = client.get("/knowledge")
    assert res.status_code == 200
    assert "knowledge-capture-studio-mount" in res.text
    assert "Vault Inbox" in res.text or "Loading Vault Inbox" in res.text
    ops_idx = res.text.index("knowledge-vault-ops-mount")
    studio_idx = res.text.index("knowledge-capture-studio-mount")
    browse_idx = res.text.index("vault-browser-layout")
    assert ops_idx < browse_idx < studio_idx


@pytest.mark.asyncio
async def test_stale_vault_review_widget_filters_by_age(db_session, settings, tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "generated-projections" / "sandbox").mkdir(parents=True)
    stale_path = vault / "generated-projections" / "sandbox" / "stale-note.md"
    fresh_path = vault / "generated-projections" / "sandbox" / "fresh-note.md"
    for path, name in (
        (stale_path, "Stale Note"),
        (fresh_path, "Fresh Note"),
    ):
        path.write_text(
            f"---\nname: {name}\ntype: concept\nid: {path.stem}\ncitations: source:test\n---\n# {name}\n\nBody.\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)

    stale_record = await create_review_record(
        db_session,
        entity_type="vault_candidate",
        entity_id="generated-projections/sandbox/stale-note.md",
    )
    fresh_record = await create_review_record(
        db_session,
        entity_type="vault_candidate",
        entity_id="generated-projections/sandbox/fresh-note.md",
    )
    old_ts = datetime.now(timezone.utc) - timedelta(hours=80)
    stale_record.created_at = old_ts
    await db_session.commit()

    widget = await build_stale_vault_review_widget(db_session, settings, stale_hours=72)
    titles = {i.title for i in widget.preview}
    assert widget.count >= 1
    assert "Stale Note" in titles
    assert "Fresh Note" not in titles
    assert widget.stale_hours == 72
    assert widget.needs_attention is True


def test_knowledge_capture_studio_partial():
    client = TestClient(create_app())
    res = client.get("/partials/knowledge/capture-studio")
    assert res.status_code == 200
    assert "knowledge-vault-inbox" in res.text
    assert "knowledge-vault-review" in res.text
    assert "capture-studio-doctrine" in res.text or "Incubator" in res.text


def test_knowledge_capture_studio_template_one_click_approve():
    from pathlib import Path

    text = Path("src/thread/ui/templates/partials/knowledge_vault_review.html").read_text(encoding="utf-8")
    assert 'name="promote_target"' in text
    assert "Advanced" in text
    assert "vault-inbox-snippet" in text
    assert "Publish with override" in text