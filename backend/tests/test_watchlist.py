"""Watchlist — explicit potential on Pulse."""

import pytest

from thread.config import Settings
from thread.services.vault_research import ensure_watchlist_research_stubs
from thread.services.watchlist import (
    add_watchlist_item,
    load_watchlist,
    new_recompete_watch_item,
    new_sam_watch_item,
    remove_watchlist_item,
)


def test_add_and_dedupe_recompete(settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    item = new_recompete_watch_item(
        award_key="KEY-1",
        title="Acme Corp",
        agency="Army",
        months_to_end=4,
    )
    add_watchlist_item(settings, item)
    again = new_recompete_watch_item(award_key="KEY-1", title="Duplicate", agency="Army")
    result = add_watchlist_item(settings, again)
    assert result.id == item.id
    assert len(load_watchlist(settings)) == 1


def test_add_sam_notice(settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    item = new_sam_watch_item(notice_id="NOTICE-ABC", title="Cyber RFI", agency="DISA")
    add_watchlist_item(settings, item)
    loaded = load_watchlist(settings)
    assert len(loaded) == 1
    assert loaded[0].kind == "sam_notice"
    assert loaded[0].notice_id == "NOTICE-ABC"


def test_remove_watchlist_item(settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    item = new_recompete_watch_item(award_key="K2", title="Beta", agency="Navy")
    add_watchlist_item(settings, item)
    assert remove_watchlist_item(settings, item.id) is True
    assert load_watchlist(settings) == ()


def test_vault_research_stub_creates_entity_notes(settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "knowledge_vault_path", tmp_path / "vault")
    result = ensure_watchlist_research_stubs(
        settings,
        title="Acme Federal",
        agency="Department of Army",
        award_key="AWARD-1",
    )
    assert result.agency_path is not None
    assert result.competitor_path is not None
    assert len(result.created) >= 1
    agency_file = tmp_path / "vault" / result.agency_path
    assert agency_file.is_file()
    assert "candidate" in agency_file.read_text(encoding="utf-8")