"""Phase 15g — global capture FAB: dump-only, platform infers + polishes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from thread.config import Settings
from thread.main import create_app
from thread.services.capture_fab import (
    CaptureFabError,
    build_capture_citations,
    build_capture_context,
    infer_title_from_dump,
    ingest_quick_capture,
    parse_opp_id,
    prepare_quick_capture,
)
from thread.services.mineru_stub import extract_document_for_capture


def test_build_capture_context_labels_pursuit():
    ctx = build_capture_context(
        opp_id="00000000-0000-0000-0000-000000000099",
        opp_name="Army Cyber IDIQ",
    )
    assert "Pursuit" in ctx.context_label
    assert ctx.opp_name == "Army Cyber IDIQ"


def test_infer_title_from_first_line():
    assert infer_title_from_dump("## Army CIO reorg\n\nDetails here") == "Army CIO reorg"
    assert infer_title_from_dump("", fallback="Fallback Title") == "Fallback Title"


def test_prepare_quick_capture_infers_type_and_context_footer():
    ctx = build_capture_context(entity="entities/agencies/army-cio.md", entity_title="Army CIO")
    draft = prepare_quick_capture("They moved the cyber shop under CIO.", context=ctx)
    assert draft.page_type == "agency"
    assert "Army CIO" in draft.name or "cyber" in draft.name.lower()
    assert "entities/agencies/army-cio.md" in draft.body
    assert "army-cio" in draft.related


def test_prepare_quick_capture_requires_content():
    ctx = build_capture_context()
    with pytest.raises(CaptureFabError, match="Dump a thought or drop a document"):
        prepare_quick_capture("", context=ctx)


def test_prepare_quick_capture_with_inline_md(tmp_path: Path):
    settings = Settings(thread_state_dir=tmp_path / ".thread")
    ctx = build_capture_context()
    doc = extract_document_for_capture(settings, "note.md", b"# Hello\nBody")
    draft = prepare_quick_capture("", context=ctx, document=doc)
    assert "Hello" in draft.body


def test_build_capture_citations_joins_context():
    cites = build_capture_citations(
        opp_id="00000000-0000-0000-0000-000000000001",
        award_key="AWD1",
        entity="entities/agencies/foo.md",
    )
    assert "source:fabric" in cites
    assert "opp:00000000" in cites
    assert "award_key:AWD1" in cites


def test_parse_opp_id():
    uid = "550e8400-e29b-41d4-a716-446655440000"
    assert str(parse_opp_id(uid)) == uid
    assert parse_opp_id("not-a-uuid") is None


@pytest.mark.asyncio
async def test_ingest_quick_capture_survives_ollama_title_timeout(db_session, settings, tmp_path, monkeypatch):
    import httpx
    from unittest.mock import AsyncMock, patch

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "generated-projections" / "sandbox").mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)
    monkeypatch.setattr(settings, "local_admin_model_enabled", True)

    dump = (
        "i heard about a new potential edge computing capability during ameetting "
        "from a person named Jason Gray. need more information to add to company capability konweldge"
    )
    with patch("thread.services.capture_title.complete", new_callable=AsyncMock, side_effect=httpx.ReadTimeout("")):
        result = await ingest_quick_capture(settings, db_session, raw_dump=dump, context=build_capture_context())
    assert result.inferred_title
    assert result.write.path.startswith("generated-projections/")


@pytest.mark.asyncio
async def test_ingest_quick_capture_writes_and_polishes(db_session, settings, tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "generated-projections" / "sandbox").mkdir(parents=True)
    (vault / "index.md").write_text("# Index\n", encoding="utf-8")
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    monkeypatch.setattr(settings, "knowledge_vault_path", vault)
    monkeypatch.setattr(settings, "local_admin_model_enabled", False)

    ctx = build_capture_context(opp_name="Test Opp", opp_id="00000000-0000-0000-0000-000000000001")
    result = await ingest_quick_capture(
        settings,
        db_session,
        raw_dump="Random thought about cyber spend trends",
        context=ctx,
    )
    assert result.write.path.startswith("generated-projections/")
    assert result.polish_provider == "rules"
    assert result.inferred_title


def test_base_shell_includes_capture_fab():
    client = TestClient(create_app())
    res = client.get("/")
    assert res.status_code == 200
    assert "capture-fab-btn" in res.text
    assert "thread_capture_fab.js" in res.text


def test_capture_fab_drawer_dump_only_form():
    client = TestClient(create_app())
    res = client.get(
        "/partials/capture/fab",
        params={
            "opp_id": "00000000-0000-0000-0000-000000000099",
            "opp_name": "Test Pursuit",
        },
    )
    assert res.status_code == 200
    assert "Dump &amp; go" in res.text or "Dump & go" in res.text
    assert 'name="dump"' in res.text
    assert 'name="name"' not in res.text
    assert "Platform take it from here" in res.text


def test_capture_fab_template_files():
    root = Path("src/thread/ui/templates/partials")
    drawer = (root / "capture_fab_drawer.html").read_text(encoding="utf-8")
    assert 'id="capture-fab-form"' in drawer
    assert "capture-fab-working" in drawer
    assert 'name="attachment"' in drawer
    assert ".pdf" in drawer
    assert "MinerU" in drawer