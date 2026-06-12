from __future__ import annotations

from dataclasses import dataclass
import json
import queue
import random
import ssl
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse, urlunparse
from urllib.request import Request, urlopen

from shared.contracts import SessionCreate, SessionSummary, TelemetryPacket


@dataclass(frozen=True)
class CloudClientConfig:
    base_url: str
    api_key: str
    device_id: str
    request_timeout_seconds: float = 15.0
    reconnect_max_seconds: float = 30.0

    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")


class FocusFlowCloudClient:
    """Blocking cloud transport intended to run in a background thread."""

    def __init__(self, config: CloudClientConfig) -> None:
        self.config = config

    def create_session(self, payload: SessionCreate) -> dict[str, Any]:
        return self._request_json("POST", "/v1/sessions", payload.model_dump(mode="json"))

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/v1/sessions/{quote(session_id, safe='')}")

    def complete_session(
        self,
        session_id: str,
        summary: SessionSummary,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"/v1/sessions/{quote(session_id, safe='')}/complete",
            summary.model_dump(mode="json"),
        )

    def run_telemetry_loop(
        self,
        session_id: str,
        packets: queue.Queue[TelemetryPacket],
        responses: queue.Queue[dict[str, Any]],
        stop_event: threading.Event,
    ) -> None:
        attempt = 0
        pending: TelemetryPacket | None = None
        while not stop_event.is_set():
            try:
                from websockets.sync.client import connect

                websocket_url = self._websocket_url(session_id)
                with connect(
                    websocket_url,
                    additional_headers={"X-API-Key": self.config.api_key},
                    open_timeout=self.config.request_timeout_seconds,
                    ssl=ssl.create_default_context()
                    if websocket_url.startswith("wss://")
                    else None,
                ) as websocket:
                    attempt = 0
                    self._put_latest(
                        responses,
                        {"type": "network_status", "status": "connected"},
                    )
                    while not stop_event.is_set():
                        if pending is None:
                            try:
                                pending = packets.get(timeout=0.5)
                            except queue.Empty:
                                continue
                        websocket.send(pending.model_dump_json())
                        raw_response = websocket.recv(timeout=self.config.request_timeout_seconds)
                        self._put_latest(responses, json.loads(raw_response))
                        pending = None
            except Exception as exc:
                attempt += 1
                delay = min(
                    self.config.reconnect_max_seconds,
                    (2 ** min(attempt, 5)) + random.uniform(0.0, 1.0),
                )
                self._put_latest(
                    responses,
                    {
                        "type": "network_status",
                        "status": "reconnecting",
                        "message": str(exc),
                        "retry_in_seconds": round(delay, 2),
                    },
                )
                stop_event.wait(delay)

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = None
        headers = {
            "Accept": "application/json",
            "X-API-Key": self.config.api_key,
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.config.normalized_base_url()}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.config.request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"FocusFlow API returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot reach FocusFlow API: {exc.reason}") from exc

    def _websocket_url(self, session_id: str) -> str:
        parsed = urlparse(self.config.normalized_base_url())
        scheme = "wss" if parsed.scheme == "https" else "ws"
        path = f"{parsed.path.rstrip('/')}/v1/ws/sessions/{quote(session_id, safe='')}"
        query = f"device_id={quote(self.config.device_id, safe='')}"
        return urlunparse((scheme, parsed.netloc, path, "", query, ""))

    @staticmethod
    def _put_latest(target: queue.Queue[dict[str, Any]], payload: dict[str, Any]) -> None:
        try:
            target.put_nowait(payload)
        except queue.Full:
            try:
                target.get_nowait()
            except queue.Empty:
                pass
            try:
                target.put_nowait(payload)
            except queue.Full:
                pass
