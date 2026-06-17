from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from thread import __version__
from thread.api.intel_routes import router as intel_router
from thread.api.routes import router as api_router
from thread.config import get_settings
from thread.db.session import init_db
from thread.orchestration.tracing import apply_langsmith_env
from thread.ui.routes import router as ui_router

UI_STATIC = Path(__file__).resolve().parent / "ui" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    apply_langsmith_env(settings)
    print(f"[thread] Starting {settings.public_app_name} v{__version__}")
    if settings.langgraph_enabled:
        print(
            f"[orchestration] LangGraph enabled — studio "
            f"{settings.langgraph_studio_base_url} (runtime wiring in progress)"
        )
    elif settings.resolved_langchain_api_key:
        print(
            f"[orchestration] LangSmith tracing ready "
            f"(project={settings.resolved_langchain_project}, runtime deferred)"
        )
    try:
        await init_db()
        print("[thread] Database tables ready")
    except Exception as exc:
        print(f"[thread] Database init note: {exc}")
    if settings.enable_startup_warmup:
        if settings.xai_api_key:
            print(f"[warmup] Grok reasoning provider configured ({settings.reasoning_llm_model})")
        else:
            print("[warmup] XAI_API_KEY not set — configure for cloud-primary reasoning")
    yield
    print("[thread] Shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.public_app_name, version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://127.0.0.1:{settings.frontend_port}",
            f"http://localhost:{settings.frontend_port}",
            f"http://127.0.0.1:{settings.port}",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/static", StaticFiles(directory=str(UI_STATIC)), name="static")
    app.include_router(ui_router)
    app.include_router(api_router, prefix="/api")
    app.include_router(intel_router, prefix="/api")
    return app


app = create_app()