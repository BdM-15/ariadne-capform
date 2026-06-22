"""MinerU 3.3 FastAPI client — Phase 19 parse wire for quick capture."""

from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from thread.config import Settings

_PARSE_MAX_MARKDOWN_CHARS = 120_000


@dataclass(frozen=True)
class MineruParseResult:
    markdown: str
    parsed_rel: str
    task_id: str | None = None


def mineru_base_url(settings: Settings) -> str:
    raw = (settings.mineru_local_endpoint or "http://127.0.0.1:8888").strip()
    return raw.rstrip("/")


def _mineru_lang_list(settings: Settings) -> tuple[str, ...]:
    """MinerU 3.4 routes English through the ch OCR pack."""
    raw = (settings.mineru_language or "ch").strip().lower()
    if raw in {"en", "english"}:
        return ("ch",)
    return (raw,)


def probe_mineru_health(settings: Settings, *, timeout_sec: float = 3.0) -> bool:
    base = mineru_base_url(settings)
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            for path in ("/health", "/docs"):
                response = client.get(f"{base}{path}")
                if response.status_code == 200:
                    return True
    except (httpx.HTTPError, OSError):
        return False
    return False


def _extract_markdown_from_response(data: object, filename: str) -> str:
    if not isinstance(data, dict):
        return ""
    results = data.get("results")
    if not isinstance(results, dict):
        return ""

    if filename in results and isinstance(results[filename], dict):
        md = results[filename].get("md_content")
        if md:
            return str(md).strip()

    for payload in results.values():
        if isinstance(payload, dict) and payload.get("md_content"):
            return str(payload["md_content"]).strip()
    return ""


def _guess_mime(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def mineru_api_filename(ingest_id: str, original_filename: str) -> str:
    """ASCII-safe upload name for MinerU — spaces in originals break Windows output paths."""
    suffix = Path(original_filename).suffix.lower()
    if suffix not in {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".tif",
        ".tiff",
        ".webp",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".xls",
        ".xlsx",
        ".html",
        ".htm",
        ".epub",
        ".mobi",
        ".txt",
        ".md",
        ".markdown",
    }:
        suffix = ".pdf"
    token = re.sub(r"[^a-z0-9]", "", (ingest_id or "doc").lower())[:16] or "doc"
    return f"doc-{token}{suffix}"


def call_mineru_file_parse(
    settings: Settings,
    staged_path: Path,
    *,
    filename: str,
    response_key: str | None = None,
) -> str:
    """POST /file_parse to local MinerU FastAPI; return markdown body."""
    if not staged_path.is_file():
        raise FileNotFoundError(f"Staged document missing: {staged_path}")

    base = mineru_base_url(settings)
    timeout = float(settings.mineru_parse_timeout_seconds)
    file_bytes = staged_path.read_bytes()

    lang = _mineru_lang_list(settings)[0]
    form: dict[str, Any] = {
        "backend": settings.mineru_backend,
        "parse_method": settings.mineru_parse_method,
        "formula_enable": "true",
        "table_enable": "true",
        "return_md": "true",
        "return_middle_json": "false",
        "return_model_output": "false",
        "return_content_list": "false",
        "return_images": "false",
        "response_format_zip": "false",
        "lang_list": lang,
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{base}/file_parse",
            data=form,
            files={"files": (filename, file_bytes, _guess_mime(filename))},
        )

    if response.status_code >= 400:
        detail = response.text[:500]
        raise RuntimeError(f"MinerU HTTP {response.status_code}: {detail}")

    content_type = (response.headers.get("content-type") or "").lower()
    if "application/zip" in content_type:
        raise RuntimeError("MinerU returned ZIP — expected JSON markdown payload")

    data = response.json()
    lookup = response_key or filename
    markdown = _extract_markdown_from_response(data, lookup)
    if not markdown:
        raise RuntimeError("MinerU returned no markdown content")
    return markdown


def save_parsed_markdown(settings: Settings, ingest_id: str, markdown: str) -> str:
    """Persist full parse under .thread/ingest/parsed/{id}/output.md."""
    root = settings.resolve(settings.thread_state_dir)
    dest_dir = root / "ingest" / "parsed" / ingest_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "output.md"
    dest.write_text(markdown, encoding="utf-8")
    return dest.relative_to(root).as_posix()


def parse_staged_document(
    settings: Settings,
    *,
    ingest_id: str,
    staged_path: Path,
    filename: str,
) -> MineruParseResult:
    api_name = mineru_api_filename(ingest_id, filename)
    raw_md = call_mineru_file_parse(
        settings,
        staged_path,
        filename=api_name,
        response_key=api_name,
    )
    parsed_rel = save_parsed_markdown(settings, ingest_id, raw_md)
    clipped = raw_md
    if len(clipped) > _PARSE_MAX_MARKDOWN_CHARS:
        clipped = clipped[:_PARSE_MAX_MARKDOWN_CHARS] + "\n\n_[Truncated for vault candidate — full parse on disk]_\n"
    return MineruParseResult(markdown=clipped, parsed_rel=parsed_rel)


def endpoint_host_port(settings: Settings) -> tuple[str, int]:
    parsed = urlparse(mineru_base_url(settings))
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8888
    return host, port