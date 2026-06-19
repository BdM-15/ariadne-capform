"""Route LLM tasks to Grok/xAI or Ollama per task class."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import httpx

from thread.config import Settings


class LlmTaskKind(StrEnum):
    REASONING = "reasoning"
    ADMIN = "admin"


class LlmProvider(StrEnum):
    XAI = "xai"
    OLLAMA = "ollama"


class LlmRouterError(Exception):
    """Base LLM routing error."""


class LlmUnavailableError(LlmRouterError):
    """No provider configured for the requested task."""


@dataclass(frozen=True)
class ResolvedProvider:
    provider: LlmProvider
    model: str
    base_url: str
    api_key: str | None
    temperature: float


@dataclass(frozen=True)
class CompletionResult:
    text: str
    provider: LlmProvider
    model: str


def resolve_provider(settings: Settings, task_kind: LlmTaskKind) -> ResolvedProvider:
    """Pick provider + model for task. Reasoning -> xAI; admin -> Ollama; fallback when allowed."""
    if task_kind is LlmTaskKind.REASONING:
        if settings.xai_api_key:
            return ResolvedProvider(
                provider=LlmProvider.XAI,
                model=settings.reasoning_llm_model,
                base_url=settings.xai_base_url.rstrip("/"),
                api_key=settings.xai_api_key,
                temperature=settings.llm_model_temperature,
            )
        if settings.llm_fallback_enabled:
            return _ollama_provider(settings)
        raise LlmUnavailableError("Reasoning requires XAI_API_KEY or LLM_FALLBACK_ENABLED")

    if settings.local_admin_model_enabled:
        return _ollama_provider(settings, admin=True)
    if settings.xai_api_key:
        return ResolvedProvider(
            provider=LlmProvider.XAI,
            model=settings.reasoning_llm_model,
            base_url=settings.xai_base_url.rstrip("/"),
            api_key=settings.xai_api_key,
            temperature=settings.ollama_temperature,
        )
    raise LlmUnavailableError("Admin tasks require Ollama or XAI_API_KEY")


def _ollama_provider(settings: Settings, *, admin: bool = False) -> ResolvedProvider:
    return ResolvedProvider(
        provider=LlmProvider.OLLAMA,
        model=settings.local_daily_model,
        base_url=settings.ollama_host.rstrip("/"),
        api_key=None,
        temperature=settings.ollama_temperature if admin else settings.llm_model_temperature,
    )


async def probe_ollama(settings: Settings, *, timeout_sec: float = 3.0) -> bool:
    """True when Ollama responds on configured host."""
    if not settings.local_admin_model_enabled:
        return False
    url = f"{settings.ollama_host.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            response = await client.get(url)
            return response.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


def _normalize_ollama_tag(name: str) -> str:
    """Strip digest suffix Ollama sometimes appends to tag names."""
    return name.split("@", 1)[0]


async def list_ollama_models(settings: Settings, *, timeout_sec: float = 5.0) -> list[str]:
    url = f"{settings.ollama_host.rstrip('/')}/api/tags"
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        response = await client.get(url)
        if response.status_code != 200:
            return []
        models = response.json().get("models") or []
        return [_normalize_ollama_tag(str(m.get("name", ""))) for m in models if m.get("name")]


async def ollama_model_available(settings: Settings, model: str, *, timeout_sec: float = 5.0) -> bool:
    """True when the configured tag is present in Ollama's local catalog."""
    if not model:
        return False
    try:
        names = await list_ollama_models(settings, timeout_sec=timeout_sec)
    except (httpx.HTTPError, OSError):
        return False
    wanted = _normalize_ollama_tag(model)
    return any(name == wanted or name.startswith(f"{wanted}-") for name in names)


async def warm_ollama_model(settings: Settings, *, timeout_sec: float | None = None) -> bool:
    """Load model weights into VRAM with a minimal chat completion."""
    timeout = timeout_sec if timeout_sec is not None else float(settings.llm_timeout_seconds)
    url = f"{settings.ollama_host.rstrip('/')}/api/chat"
    payload: dict[str, Any] = {
        "model": settings.local_daily_model,
        "messages": [{"role": "user", "content": "ok"}],
        "stream": False,
        "options": {"num_predict": 1, "temperature": 0},
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload)
        if response.status_code >= 400:
            raise LlmRouterError(f"Ollama warm error {response.status_code}: {response.text[:300]}")
        return response.status_code == 200


def _append_llm_trace(
    settings: Settings,
    *,
    task_kind: LlmTaskKind,
    resolved: ResolvedProvider,
    messages: list[dict[str, str]],
    text: str,
    elapsed_ms: float,
) -> None:
    try:
        trace_dir = settings.resolve(settings.thread_state_dir / "llm_traces")
        trace_dir.mkdir(parents=True, exist_ok=True)
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        path = trace_dir / f"{day}.jsonl"
        row = {
            "ts": datetime.now(UTC).isoformat(),
            "task": task_kind.value,
            "provider": resolved.provider.value,
            "model": resolved.model,
            "elapsed_ms": round(elapsed_ms, 1),
            "message_count": len(messages),
            "prompt_chars": sum(len(m.get("content", "")) for m in messages),
            "output_chars": len(text),
            "output_preview": text[:500],
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


async def complete(
    settings: Settings,
    *,
    task_kind: LlmTaskKind,
    messages: list[dict[str, str]],
    max_tokens: int | None = None,
    temperature: float | None = None,
    client: httpx.AsyncClient | None = None,
) -> CompletionResult:
    """Run chat completion via resolved provider. Outputs stay candidate until review gate."""
    resolved = resolve_provider(settings, task_kind)
    token_limit = max_tokens or settings.llm_max_output_tokens
    temp = temperature if temperature is not None else resolved.temperature

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=settings.llm_timeout_seconds)
    started = time.perf_counter()
    try:
        if resolved.provider is LlmProvider.XAI:
            text = await _xai_complete(http, resolved, messages, token_limit, temp)
        else:
            text = await _ollama_complete(http, resolved, messages, token_limit, temp)
    except httpx.HTTPError as exc:
        label = type(exc).__name__
        detail = str(exc).strip() or "request timed out or connection failed"
        raise LlmRouterError(f"{label}: {detail}") from exc
    except OSError as exc:
        raise LlmRouterError(f"Network error: {exc}") from exc
    finally:
        if owns_client:
            await http.aclose()

    elapsed_ms = (time.perf_counter() - started) * 1000
    _append_llm_trace(
        settings,
        task_kind=task_kind,
        resolved=resolved,
        messages=messages,
        text=text,
        elapsed_ms=elapsed_ms,
    )

    return CompletionResult(text=text, provider=resolved.provider, model=resolved.model)


async def _xai_complete(
    client: httpx.AsyncClient,
    resolved: ResolvedProvider,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
) -> str:
    payload: dict[str, Any] = {
        "model": resolved.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {"Authorization": f"Bearer {resolved.api_key}", "Content-Type": "application/json"}
    response = await client.post(f"{resolved.base_url}/chat/completions", json=payload, headers=headers)
    if response.status_code >= 400:
        raise LlmRouterError(f"xAI error {response.status_code}: {response.text[:500]}")
    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmRouterError(f"Unexpected xAI response shape: {data!r}") from exc


async def _ollama_complete(
    client: httpx.AsyncClient,
    resolved: ResolvedProvider,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
) -> str:
    payload: dict[str, Any] = {
        "model": resolved.model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    response = await client.post(f"{resolved.base_url}/api/chat", json=payload)
    if response.status_code >= 400:
        raise LlmRouterError(f"Ollama error {response.status_code}: {response.text[:500]}")
    data = response.json()
    try:
        return data["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise LlmRouterError(f"Unexpected Ollama response shape: {data!r}") from exc