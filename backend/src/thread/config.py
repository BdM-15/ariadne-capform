"""Single source of truth for runtime configuration (Pydantic v2)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]

# Manifest env var names → canonical .env key (Phase 12k editor)
MCP_ENV_CANONICAL: dict[str, str] = {
    "SAM_API_KEY": "SAM_GOV_API_KEY",
    "DATA_GOV_API_KEY": "API_DATA_GOV_KEY",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = 9622
    frontend_port: int = 3000
    public_app_name: str = "Ariadne's Thread"
    next_public_api_url: str = "http://127.0.0.1:9622"
    autostart_frontend: bool = False  # deprecated — app.py ignores; use --legacy-frontend
    enable_startup_warmup: bool = True
    autostart_research_providers: bool = True

    thread_postgres_port: int = 55432
    database_url: str = "postgresql+asyncpg://thread:thread@127.0.0.1:55432/thread"
    database_pool_size: int = 10
    database_echo: bool = False

    intel_migration_source: Path = Path("../capture-insights/data/capture.duckdb")
    intel_bulk_prime_dir: Path = Path("../capture-insights/data/raw/10year_bulk/prime")
    intel_bulk_sub_dir: Path = Path("../capture-insights/data/raw/10year_bulk/sub")
    intel_auto_migrate_on_start: bool = True

    knowledge_vault_path: Path = Path("knowledge/thread")
    knowledge_seed_source: Path = Path("../capture-insights/data/knowledge")
    knowledge_bootstrap_on_start: bool = True
    vault_sandbox_mode: bool = Field(
        default=False,
        validation_alias=AliasChoices("THREAD_VAULT_SANDBOX", "vault_sandbox_mode"),
    )
    vault_allow_test_promote: bool = Field(
        default=False,
        validation_alias=AliasChoices("THREAD_ALLOW_TEST_PROMOTE", "vault_allow_test_promote"),
    )
    reference_docs_root: Path = Path("docs/reference")
    graph_edges_path: Path = Path("data/graph/edges.jsonl")

    xai_api_key: str | None = None
    xai_base_url: str = "https://api.x.ai/v1"
    default_llm_provider: str = "xai"
    reasoning_llm_model: str = "grok-4.3"
    llm_fallback_enabled: bool = True
    llm_model_temperature: float = 0.3
    llm_max_output_tokens: int = 8192
    llm_timeout_seconds: int = 120

    ollama_host: str = "http://localhost:11434"
    local_daily_model: str = "qwen3:8b"
    local_admin_model_enabled: bool = True
    ollama_temperature: float = 0.3

    embedding_binding: str = "openai"
    embedding_binding_host: str = "https://api.openai.com/v1"
    embedding_binding_api_key: str | None = None
    embedding_model: str = "text-embedding-3-large"
    embedding_dim: int = 3072

    searxng_base_url: str = "http://localhost:8080"
    crawl4ai_base_url: str = "http://localhost:11235"
    crawl4ai_api_token: str = "test_api_code"
    serpapi_api_key: str | None = None
    olostep_api_key: str | None = None
    firecrawl_api_key: str | None = None
    research_require_approval_for_paid: bool = True

    enable_live_mcps: bool = True
    sam_gov_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "sam_gov_api_key",
            "SAM_GOV_API_KEY",
            "sam_api_key",
            "SAM_API_KEY",
        ),
    )
    bls_api_key: str | None = None
    api_data_gov_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("api_data_gov_key", "data_gov_api_key"),
    )
    perdiem_api_key: str | None = None
    mcp_tool_timeout_seconds: int = 60

    skills_root: Path = Path("skills")
    skill_runs_path: Path = Path("data/runs")
    thread_state_dir: Path = Path(".thread")
    # Legacy skill param only — NOT a platform search default. Radar/Insights require explicit facets.
    default_naics: str = "561210"

    mineru_enabled: bool = True
    mineru_autostart: bool = Field(
        default=True,
        validation_alias=AliasChoices("mineru_autostart", "MINERU_AUTOSTART"),
    )
    mineru_docker_image: str | None = None
    mineru_venv_path: Path = Field(
        default=Path(".venv-mineru"),
        validation_alias=AliasChoices("mineru_venv_path", "MINERU_VENV_PATH"),
    )
    mineru_python: str = Field(
        default="",
        validation_alias=AliasChoices("mineru_python", "MINERU_PYTHON"),
    )
    mineru_local_endpoint: str = Field(
        default="http://127.0.0.1:8888",
        validation_alias=AliasChoices("mineru_local_endpoint", "MINERU_LOCAL_ENDPOINT"),
    )
    mineru_backend: str = Field(
        default="hybrid-auto-engine",
        validation_alias=AliasChoices("mineru_backend", "MINERU_LOCAL_BACKEND", "MINERU_BACKEND"),
    )
    mineru_parse_method: str = Field(
        default="auto",
        validation_alias=AliasChoices("mineru_parse_method", "MINERU_LOCAL_PARSE_METHOD", "PARSE_METHOD"),
    )
    mineru_language: str = Field(
        default="ch",
        validation_alias=AliasChoices("mineru_language", "MINERU_LANGUAGE"),
    )
    mineru_parse_timeout_seconds: int = Field(
        default=600,
        validation_alias=AliasChoices("mineru_parse_timeout_seconds", "MINERU_PARSE_TIMEOUT_SECONDS"),
    )
    mineru_startup_timeout_seconds: int = Field(
        default=300,
        validation_alias=AliasChoices("mineru_startup_timeout_seconds", "MINERU_STARTUP_TIMEOUT_SECONDS"),
    )
    mineru_spawn_fail_seconds: float = Field(
        default=5.0,
        validation_alias=AliasChoices("mineru_spawn_fail_seconds", "MINERU_SPAWN_FAIL_SECONDS"),
    )
    mineru_vlm_preload: bool = Field(
        default=False,
        validation_alias=AliasChoices("mineru_vlm_preload", "MINERU_VLM_PRELOAD"),
    )
    mineru_device_mode: str = Field(
        default="cuda",
        validation_alias=AliasChoices("mineru_device_mode", "MINERU_DEVICE_MODE"),
    )
    mineru_cuda_visible_devices: str = Field(
        default="0",
        validation_alias=AliasChoices("mineru_cuda_visible_devices", "CUDA_VISIBLE_DEVICES"),
    )
    mineru_hybrid_batch_ratio: int = Field(
        default=8,
        validation_alias=AliasChoices("mineru_hybrid_batch_ratio", "MINERU_HYBRID_BATCH_RATIO"),
    )

    langgraph_enabled: bool = False
    thread_langgraph_studio_auto_start: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "thread_langgraph_studio_auto_start",
            "theseus_langgraph_studio_auto_start",
        ),
    )
    langgraph_studio_host: str = "127.0.0.1"
    langgraph_studio_port: int = 9623

    langsmith_api_key: str | None = None
    langchain_api_key: str | None = None
    langsmith_tracing: bool = False
    langchain_tracing_v2: bool = False
    langsmith_project: str = "thread-capture-orchestration"
    langchain_project: str | None = None
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    @property
    def repo_root(self) -> Path:
        return ROOT

    @property
    def resolved_langchain_api_key(self) -> str | None:
        return self.langchain_api_key or self.langsmith_api_key

    @property
    def resolved_langchain_project(self) -> str:
        return self.langchain_project or self.langsmith_project

    @property
    def langgraph_studio_base_url(self) -> str:
        return f"http://{self.langgraph_studio_host}:{self.langgraph_studio_port}"

    def resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else ROOT / path

    def mcp_subprocess_env(self, env_required: list[str]) -> dict[str, str]:
        """Closed allowlist env vars injected into MCP subprocesses."""
        catalog: dict[str, str | None] = {
            "SAM_GOV_API_KEY": self.sam_gov_api_key,
            "SAM_API_KEY": self.sam_gov_api_key,
            "BLS_API_KEY": self.bls_api_key,
            "API_DATA_GOV_KEY": self.api_data_gov_key,
            "DATA_GOV_API_KEY": self.api_data_gov_key,
            "PERDIEM_API_KEY": self.perdiem_api_key or self.api_data_gov_key,
        }
        out = {key: value for key in env_required if (value := catalog.get(key))}
        if self.sam_gov_api_key:
            out.setdefault("SAM_API_KEY", self.sam_gov_api_key)
            out.setdefault("SAM_GOV_API_KEY", self.sam_gov_api_key)
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """Re-read .env after MCP key save (clears lru_cache)."""
    get_settings.cache_clear()
    return get_settings()


def apply_env_to_process(key: str, value: str) -> None:
    """Update os.environ so subprocess MCP spawns see new keys without restart."""
    canonical = MCP_ENV_CANONICAL.get(key, key)
    os.environ[canonical] = value
    if canonical == "SAM_GOV_API_KEY":
        os.environ.setdefault("SAM_API_KEY", value)
    if canonical == "API_DATA_GOV_KEY":
        os.environ.setdefault("DATA_GOV_API_KEY", value)