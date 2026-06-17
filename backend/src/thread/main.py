from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from thread import __version__
from thread.api.routes import router
from thread.config import get_settings
from thread.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"[thread] Starting {settings.public_app_name} v{__version__}")
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
    app.include_router(router, prefix="/api")
    return app


app = create_app()