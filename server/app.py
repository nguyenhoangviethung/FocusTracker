from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.api.routes import router
from server.config import ServerSettings
from server.core.inference import CloudInferenceEngine
from server.repositories.sessions import create_session_repository
from server.services.event_publisher import create_event_publisher


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = ServerSettings.from_env()
    app.state.settings = settings
    app.state.session_repository = create_session_repository(settings)
    app.state.event_publisher = create_event_publisher(settings)
    app.state.inference_engine = CloudInferenceEngine()
    yield


def create_app() -> FastAPI:
    settings = ServerSettings.from_env()
    app = FastAPI(
        title="FocusFlow AI API",
        version="1.0.0",
        lifespan=lifespan,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-API-Key"],
        )
    app.include_router(router)
    return app


app = create_app()
