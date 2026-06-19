from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
from datetime import timedelta
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from server.api.routes import DashboardSnapshotCache, router
from server.config import ServerSettings
from server.core.inference import CloudInferenceEngine
from server.repositories.sessions import create_session_repository
from server.repositories.users import create_user_repository
from server.services.event_publisher import create_event_publisher
from shared.contracts import utc_now


logger = logging.getLogger(__name__)


async def _stale_session_cleanup_loop(app: FastAPI) -> None:
    settings: ServerSettings = app.state.settings
    repository = app.state.session_repository
    interval = max(30, int(settings.stale_session_cleanup_interval_seconds))
    timeout_seconds = max(60, int(settings.stale_session_timeout_seconds))
    while True:
        await asyncio.sleep(interval)
        try:
            cutoff = utc_now() - timedelta(seconds=timeout_seconds)
            expired_ids = repository.expire_stale(cutoff, limit=500)
            if expired_ids:
                logger.warning(
                    "Expired stale sessions count=%d timeout_seconds=%d",
                    len(expired_ids),
                    timeout_seconds,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Stale session cleanup failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = ServerSettings.from_env()
    app.state.settings = settings
    app.state.session_repository = create_session_repository(settings)
    app.state.user_repository = create_user_repository(settings)
    app.state.event_publisher = create_event_publisher(settings)
    app.state.inference_engine = CloudInferenceEngine()
    app.state.dashboard_cache = DashboardSnapshotCache()
    app.state.stale_session_cleanup_task = asyncio.create_task(
        _stale_session_cleanup_loop(app)
    )
    try:
        yield
    finally:
        app.state.stale_session_cleanup_task.cancel()
        try:
            await app.state.stale_session_cleanup_task
        except asyncio.CancelledError:
            pass


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
            allow_methods=["GET", "POST", "DELETE"],
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
