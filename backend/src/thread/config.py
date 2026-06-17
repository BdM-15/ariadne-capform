"""Single source of truth for runtime configuration (Pydantic v2)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


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
    autostart_frontend: bool = False
    enable_startup_warmup: bool = True
    autostart_research_providers: bool = True

    thread_postgres_port: int = 55432
    database_url: str = "postgresql+asyncpg://thread:thread@127.0.0.1:55432/thread"
    database_pool_size: int = 10

    intel_migration_source: Path = Path("../capture-insights/data/capture.duckdb")
    intel_auto_migrate_on_start: bool = True

    knowledge_vault_path: Path = Path("knowledge/thread")
    knowledge_seed_source: Path = Path("../capture-insights/data/knowledge")
    knowledge_bootstrap_on_start: bool = True
    reference_docs_root: Path = Path("docs/reference")
    graph_edges_path: Path = Path("data/graph/edges.jsonl")

    xai_api_key: str | None = None
    xai_base_url: str = "https://api.x.ai/v1"
    default_llm_provider: str = "xai"
    reasoning_llm_model: str = "grok-4"
    llm_fallback_enabled: bool = True
    llm_model_temperature: float = 0.3
    llm_max_output_tokens: int = 8192
    llm_timeout_seconds: int = 120

    ollama_host: str = "http://localhost:11434"
    local_daily_model: str = "qwen3.5:9b"
    local_admin_model_enabled: bool = True
    ollama_temperature: float = 0.3

    embedding_binding: str = "openai"
    embedding_binding_host: str = "https://api.openai.com/v1"
    embedding_binding_api_key: str | None = None
    embedding_model: str = "text-embedding-3-large"
    embedding_dim: int = 3072

    searxng_base_url: str = "http://localhost:8080"
    crawl4ai_base_url: str = "http://localhost:11235"
    serpapi_api_key: str | None = None
    olostep_api_key: str | None = None
    firecrawl_api_key: str | None = None
    research_require_approval_for_paid: bool = True

    enable_live_mcps: bool = True
    sam_gov_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("sam_gov_api_key", "sam_api_key"),
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
    default_naics: str = "561210"

    mineru_enabled: bool = False
    mineru_docker_image: str | None = None

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
        return {key: value for key in env_required if (value := catalog.get(key))}


@lru_cache
def get_settings() -> Settings:
    return Settings()