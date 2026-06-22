"""Phase 19 — MinerU FastAPI client."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from thread.config import Settings
from thread.services.mineru_client import (
    call_mineru_file_parse,
    mineru_api_filename,
    parse_staged_document,
    probe_mineru_health,
    save_parsed_markdown,
)


def test_probe_mineru_health_true_on_200():
    settings = Settings(mineru_local_endpoint="http://127.0.0.1:8888")
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("thread.services.mineru_client.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.return_value = mock_response
        assert probe_mineru_health(settings) is True


def test_mineru_api_filename_sanitizes_spaces():
    name = mineru_api_filename("fdba6993037d", "18 May Training Hotel Receipt.pdf")
    assert " " not in name
    assert name.endswith(".pdf")
    assert name.startswith("doc-")


def test_call_mineru_file_parse_extracts_md(tmp_path: Path):
    staged = tmp_path / "brief.pdf"
    staged.write_bytes(b"%PDF-1.4")
    settings = Settings(mineru_local_endpoint="http://127.0.0.1:8888")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {
        "results": {"brief.pdf": {"md_content": "# Parsed\n\nHello world."}},
    }

    with patch("thread.services.mineru_client.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.post.return_value = mock_response
        md = call_mineru_file_parse(settings, staged, filename="brief.pdf")

    assert "Hello world" in md


def test_parse_staged_document_saves_output(tmp_path: Path):
    staged = tmp_path / "inbox" / "abc123" / "brief.pdf"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"%PDF")
    settings = Settings(thread_state_dir=tmp_path / ".thread")

    with patch(
        "thread.services.mineru_client.call_mineru_file_parse",
        return_value="# Title\n\nBody text.",
    ):
        result = parse_staged_document(
            settings,
            ingest_id="abc123",
            staged_path=staged,
            filename="brief.pdf",
        )

    assert "Body text" in result.markdown
    assert result.parsed_rel == "ingest/parsed/abc123/output.md"
    saved = settings.resolve(settings.thread_state_dir) / result.parsed_rel
    assert saved.is_file()


def test_call_mineru_file_parse_raises_on_http_error(tmp_path: Path):
    staged = tmp_path / "x.pdf"
    staged.write_bytes(b"%PDF")
    settings = Settings()

    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.text = "busy"

    with patch("thread.services.mineru_client.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.post.return_value = mock_response
        try:
            call_mineru_file_parse(settings, staged, filename="x.pdf")
            assert False, "expected error"
        except RuntimeError as exc:
            assert "503" in str(exc)