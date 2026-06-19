"""Saved Clew trace bookmarks."""

import pytest
from fastapi.testclient import TestClient

from thread.clew.saved_traces import (
    clew_trace_href,
    delete_clew_trace,
    load_clew_traces,
    new_clew_trace_from_form,
    save_clew_trace,
)
from thread.config import Settings
from thread.main import create_app


@pytest.fixture(autouse=True)
async def _dispose_engine():
    yield
    from thread.db import session as db_session_module

    if db_session_module.engine is not None:
        await db_session_module.engine.dispose()


def test_save_and_load_trace(settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    trace = new_clew_trace_from_form(
        settings,
        name="Amentum flow",
        recipient="Amentum",
        mode="money_flow",
        last_summary="Top 12 money paths",
    )
    assert trace is not None
    save_clew_trace(settings, trace)
    loaded = load_clew_traces(settings)
    assert len(loaded) == 1
    assert loaded[0].recipient == "Amentum"
    assert loaded[0].mode == "money_flow"
    assert "run=1" in clew_trace_href(loaded[0])


def test_delete_trace(settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "thread_state_dir", tmp_path / ".thread")
    trace = new_clew_trace_from_form(settings, name="Gone", agency="Army")
    assert trace is not None
    save_clew_trace(settings, trace)
    assert delete_clew_trace(settings, trace.id) is True
    assert load_clew_traces(settings) == ()


def test_clew_page_renders_saved_traces_section():
    client = TestClient(create_app())
    res = client.get("/clew")
    assert res.status_code == 200
    assert "clew-saved-traces-panel" in res.text
    assert "Save current trace" in res.text
    assert "Saved traces" in res.text


def test_clew_save_trace_endpoint(settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setenv("THREAD_STATE_DIR", str(tmp_path / ".thread"))
    client = TestClient(create_app())
    res = client.post(
        "/clew/save",
        data={
            "name": "Amentum teaming",
            "recipient": "Amentum",
            "mode": "teaming",
        },
    )
    assert res.status_code == 200
    assert "Saved trace" in res.text
    assert "Amentum teaming" in res.text