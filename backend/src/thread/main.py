from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from thread import __version__
from thread.api.intel_routes import router as intel_router
from thread.api.knowledge_routes import router as knowledge_router
from thread.api.research_routes import router as research_router
from thread.api.routes import router as api_router
from thread.api.skill_routes import router as skill_router
from thread.bootstrap.warmup import log_warmup_report, run_startup_warmup
from thread.config import get_settings
from thread.db.session import init_db
from thread.orchestration.tracing import apply_langsmith_env
from thread.ui.routes import router as ui_router

ROOT = Path(__file__).resolve().parents[3]
UI_STATIC = Path(__file__).resolve().parent / "ui" / "static"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@asynccontextmanager
async def lifespan(app: FastAPI):
    from tavern.pool import close_tavern_pool, create_tavern_pool

    settings = get_settings()
    apply_langsmith_env(settings)
    try:
        await init_db()
    except Exception as exc:
        print(f"[thread] Database init note: {exc}")

    app.state.tavern_pool = None
    try:
        app.state.tavern_pool = await create_tavern_pool(settings.database_url)
    except Exception as exc:
        print(f"[thread] Tavern pool note: {exc}")

    warmup_report = await run_startup_warmup(app, settings)
    log_warmup_report(warmup_report)
    app.state.warmup_report = warmup_report

    yield
    await close_tavern_pool(app.state.tavern_pool)
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
    app.include_router(research_router, prefix="/api")
    app.include_router(skill_router, prefix="/api")
    app.include_router(knowledge_router, prefix="/api")

    from tavern.router import router as tavern_router

    app.include_router(tavern_router, prefix="/tavern")
    return app


app = create_app()