from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from server.config import ServerSettings


logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    def publish(self, event_type: str, payload: dict[str, Any]) -> str: ...


class LoggingEventPublisher:
    def publish(self, event_type: str, payload: dict[str, Any]) -> str:
        logger.info("domain_event type=%s payload=%s", event_type, payload)
        return "logged"


class PubSubEventPublisher:
    def __init__(self, project_id: str, topic_name: str) -> None:
        try:
            from google.cloud import pubsub_v1
        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-pubsub is required when FOCUSFLOW_EVENT_BACKEND=pubsub"
            ) from exc

        self._publisher = pubsub_v1.PublisherClient()
        self._topic_path = self._publisher.topic_path(project_id, topic_name)

    def publish(self, event_type: str, payload: dict[str, Any]) -> str:
        body = json.dumps(
            {"event_type": event_type, "payload": payload},
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        future = self._publisher.publish(
            self._topic_path,
            body,
            event_type=event_type,
        )
        return str(future.result(timeout=10))


def create_event_publisher(settings: ServerSettings) -> EventPublisher:
    if settings.event_backend == "pubsub":
        return PubSubEventPublisher(
            project_id=settings.gcp_project_id,
            topic_name=settings.pubsub_session_events_topic,
        )
    return LoggingEventPublisher()
