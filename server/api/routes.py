from __future__ import annotations

import asyncio
import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from server.config import ServerSettings
from server.core.inference import CloudInferenceEngine
from server.repositories.sessions import SessionRepository
from server.services.event_publisher import EventPublisher
from shared.contracts import (
    InferenceResponse,
    SessionCreate,
    SessionRecord,
    SessionSummary,
    TelemetryPacket,
)


router = APIRouter()


def _services(
    request: Request,
) -> tuple[
    ServerSettings,
    SessionRepository,
    CloudInferenceEngine,
    EventPublisher,
]:
    return (
        request.app.state.settings,
        request.app.state.session_repository,
        request.app.state.inference_engine,
        request.app.state.event_publisher,
    )


def _verify_api_key(settings: ServerSettings, supplied: str | None) -> None:
    if not settings.api_key:
        if settings.environment == "production":
            raise HTTPException(status_code=503, detail="Server API key is not configured")
        return
    if not supplied or not secrets.compare_digest(settings.api_key, supplied):
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> dict[str, str]:
    engine = getattr(request.app.state, "inference_engine", None)
    repository = getattr(request.app.state, "session_repository", None)
    if engine is None or repository is None:
        raise HTTPException(status_code=503, detail="Application is not ready")
    return {"status": "ready"}


@router.post("/v1/sessions", response_model=SessionRecord, status_code=201)
async def create_session(
    payload: SessionCreate,
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> SessionRecord:
    settings, repository, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    return await asyncio.to_thread(repository.create, payload)


@router.get("/v1/sessions/{session_id}")
async def get_session(
    session_id: str,
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings, repository, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    record = await asyncio.to_thread(repository.get, session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return record


@router.post("/v1/sessions/{session_id}/complete")
async def complete_session(
    session_id: str,
    summary: SessionSummary,
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings, repository, _, publisher = _services(request)
    _verify_api_key(settings, x_api_key)
    existing = await asyncio.to_thread(repository.get, session_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if existing.get("ended_at"):
        return existing
    record = await asyncio.to_thread(repository.complete, session_id, summary)
    if record is None:  # Defensive guard for concurrent deletion.
        raise HTTPException(status_code=404, detail="Session not found")
    await asyncio.to_thread(
        publisher.publish,
        "session.completed",
        {
            "session_id": session_id,
            "device_id": record.get("device_id"),
            "summary": summary.model_dump(mode="json"),
        },
    )
    return record


@router.post("/v1/inference", response_model=InferenceResponse)
async def run_inference(
    packet: TelemetryPacket,
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> InferenceResponse:
    settings, repository, engine, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    session = await asyncio.to_thread(repository.get, packet.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(session.get("device_id")) != packet.device_id:
        raise HTTPException(status_code=403, detail="Device does not own this session")
    response = await asyncio.to_thread(engine.predict, packet)
    await asyncio.to_thread(repository.touch, packet.session_id)
    return response


@router.websocket("/v1/ws/sessions/{session_id}")
async def session_telemetry(websocket: WebSocket, session_id: str) -> None:
    settings: ServerSettings = websocket.app.state.settings
    supplied_key = websocket.headers.get("x-api-key") or websocket.query_params.get("api_key")
    try:
        _verify_api_key(settings, supplied_key)
    except HTTPException:
        await websocket.close(code=4401, reason="Invalid API key")
        return

    device_id = websocket.query_params.get("device_id", "")
    repository: SessionRepository = websocket.app.state.session_repository
    session = await asyncio.to_thread(repository.get, session_id)
    if session is None:
        await websocket.close(code=4404, reason="Session not found")
        return
    if not device_id or str(session.get("device_id")) != device_id:
        await websocket.close(code=4403, reason="Device does not own this session")
        return

    engine: CloudInferenceEngine = websocket.app.state.inference_engine
    await websocket.accept()
    try:
        while True:
            raw_payload = await websocket.receive_json()
            try:
                packet = TelemetryPacket.model_validate(raw_payload)
            except ValidationError as exc:
                await websocket.send_json(
                    {
                        "type": "validation_error",
                        "errors": exc.errors(include_url=False),
                    }
                )
                continue
            if packet.session_id != session_id or packet.device_id != device_id:
                await websocket.send_json(
                    {"type": "protocol_error", "message": "Session or device mismatch"}
                )
                continue
            response = await asyncio.to_thread(engine.predict, packet)
            await asyncio.to_thread(repository.touch, session_id)
            await websocket.send_json(response.model_dump(mode="json"))
    except WebSocketDisconnect:
        return
