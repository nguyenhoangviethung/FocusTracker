from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from server.api.routes import router
from server.config import ServerSettings
from server.core.inference import CloudInferenceEngine
from server.repositories.sessions import create_session_repository
from server.repositories.users import create_user_repository
from server.services.event_publisher import create_event_publisher


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = ServerSettings.from_env()
    app.state.settings = settings
    app.state.session_repository = create_session_repository(settings)
    app.state.user_repository = create_user_repository(settings)
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

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.error(
            "Unhandled server error method=%s path=%s",
            request.method,
            request.url.path,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "path": request.url.path,
            },
        )

    app.include_router(router)
    return app


app = create_app()
