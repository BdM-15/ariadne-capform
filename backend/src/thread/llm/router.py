"""Route LLM tasks to Grok/xAI or Ollama per task class."""

from __future__ import annotations

from dataclasses import dataclass
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
    try:
        if resolved.provider is LlmProvider.XAI:
            text = await _xai_complete(http, resolved, messages, token_limit, temp)
        else:
            text = await _ollama_complete(http, resolved, messages, token_limit, temp)
    finally:
        if owns_client:
            await http.aclose()

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