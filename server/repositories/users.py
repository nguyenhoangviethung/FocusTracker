from __future__ import annotations

import threading
from typing import Any, Protocol

from server.config import ServerSettings
from shared.contracts import utc_now
from shared.identifiers import (
    google_subject_document_id,
    new_google_user_id,
    new_password_user_id,
    username_document_id,
)


def _now_iso() -> str:
    return utc_now().isoformat()


class UserRepository(Protocol):
    def get_by_username(self, username: str) -> dict[str, Any] | None: ...

    def get_by_google_subject(self, subject: str) -> dict[str, Any] | None: ...

    def get(self, user_id: str) -> dict[str, Any] | None: ...

    def create_password_user(
        self,
        username: str,
        password_hash: str,
        password_salt: str,
        display_name: str | None,
    ) -> dict[str, Any]: ...

    def login_password_user(self, username: str) -> dict[str, Any] | None: ...

    def upsert_google_user(
        self,
        subject: str,
        email: str | None,
        display_name: str | None,
        id_token_jti: str | None = None,
    ) -> dict[str, Any]: ...


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._users: dict[str, dict[str, Any]] = {}
        self._username_index: dict[str, str] = {}
        self._google_index: dict[str, str] = {}
        self._lock = threading.Lock()

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        with self._lock:
            user_id = self._username_index.get(username.lower())
            return dict(self._users[user_id]) if user_id and user_id in self._users else None

    def get_by_google_subject(self, subject: str) -> dict[str, Any] | None:
        with self._lock:
            user_id = self._google_index.get(subject)
            return dict(self._users[user_id]) if user_id and user_id in self._users else None

    def get(self, user_id: str) -> dict[str, Any] | None:
        with self._lock:
            user = self._users.get(user_id)
            return dict(user) if user else None

    def create_password_user(
        self,
        username: str,
        password_hash: str,
        password_salt: str,
        display_name: str | None,
    ) -> dict[str, Any]:
        username_key = username.lower().strip()
        with self._lock:
            if username_key in self._username_index:
                raise ValueError("username already exists")
            user_id = new_password_user_id(username_key)
            now = _now_iso()
            record = {
                "user_id": user_id,
                "auth_provider": "password",
                "username": username_key,
                "display_name": display_name or username_key,
                "email": None,
                "password_hash": password_hash,
                "password_salt": password_salt,
                "password_iterations": 390000,
                "created_at": now,
                "last_login_at": now,
            }
            self._users[user_id] = record
            self._username_index[username_key] = user_id
            return dict(record)

    def login_password_user(self, username: str) -> dict[str, Any] | None:
        with self._lock:
            user_id = self._username_index.get(username.lower().strip())
            if not user_id:
                return None
            user = self._users.get(user_id)
            if not user:
                return None
            user["last_login_at"] = _now_iso()
            return dict(user)

    def upsert_google_user(
        self,
        subject: str,
        email: str | None,
        display_name: str | None,
        id_token_jti: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            user_id = self._google_index.get(subject)
            now = _now_iso()
            username_value = email or subject
            if user_id and user_id in self._users:
                user = self._users[user_id]
                user["email"] = email or user.get("email")
                user["display_name"] = display_name or user.get("display_name") or email or subject
                user["username"] = username_value
                user["last_login_at"] = now
                if id_token_jti:
                    user["last_google_jti"] = id_token_jti
                self._username_index[username_value.lower()] = user_id
                return dict(user)

            user_id = new_google_user_id(email, subject)
            record = {
                "user_id": user_id,
                "auth_provider": "google",
                "username": username_value,
                "display_name": display_name or email or subject,
                "email": email,
                "google_subject": subject,
                "created_at": now,
                "last_login_at": now,
            }
            if id_token_jti:
                record["last_google_jti"] = id_token_jti
            self._users[user_id] = record
            self._google_index[subject] = user_id
            self._username_index[username_value.lower()] = user_id
            return dict(record)


class FirestoreUserRepository:
    def __init__(self, project_id: str, collection_name: str, username_index_collection: str, google_index_collection: str) -> None:
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-firestore is required for FOCUSFLOW_REPOSITORY=firestore"
            ) from exc

        self._firestore = firestore
        self._client = firestore.Client(project=project_id or None)
        self._users = self._client.collection(collection_name)
        self._username_index = self._client.collection(username_index_collection)
        self._google_index = self._client.collection(google_index_collection)

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        username_key = username.lower().strip()
        index_snapshot = self._username_index.document(
            username_document_id(username_key)
        ).get()
        if not index_snapshot.exists:
            index_snapshot = self._username_index.document(username_key).get()
        if not index_snapshot.exists:
            return None
        user_id = (index_snapshot.to_dict() or {}).get("user_id")
        return self.get(str(user_id)) if user_id else None

    def get_by_google_subject(self, subject: str) -> dict[str, Any] | None:
        subject_key = subject.strip()
        index_snapshot = self._google_index.document(
            google_subject_document_id(subject_key)
        ).get()
        if not index_snapshot.exists:
            index_snapshot = self._google_index.document(subject_key).get()
        if not index_snapshot.exists:
            return None
        user_id = (index_snapshot.to_dict() or {}).get("user_id")
        return self.get(str(user_id)) if user_id else None

    def get(self, user_id: str) -> dict[str, Any] | None:
        snapshot = self._users.document(user_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def create_password_user(
        self,
        username: str,
        password_hash: str,
        password_salt: str,
        display_name: str | None,
    ) -> dict[str, Any]:
        username_key = username.lower().strip()
        user_ref = self._users.document(new_password_user_id(username_key))
        username_ref = self._username_index.document(
            username_document_id(username_key)
        )
        legacy_username_ref = self._username_index.document(username_key)

        @self._firestore.transactional
        def _create(transaction):
            if (
                username_ref.get(transaction=transaction).exists
                or legacy_username_ref.get(transaction=transaction).exists
            ):
                raise ValueError("username already exists")
            now = _now_iso()
            record = {
                "user_id": user_ref.id,
                "auth_provider": "password",
                "username": username_key,
                "display_name": display_name or username_key,
                "email": None,
                "password_hash": password_hash,
                "password_salt": password_salt,
                "password_iterations": 390000,
                "created_at": now,
                "last_login_at": now,
            }
            transaction.set(user_ref, record)
            transaction.set(username_ref, {"user_id": user_ref.id, "username": username_key, "created_at": now})
            return record

        return _create(self._client.transaction())

    def login_password_user(self, username: str) -> dict[str, Any] | None:
        username_key = username.lower().strip()
        username_ref = self._username_index.document(
            username_document_id(username_key)
        )
        snapshot = username_ref.get()
        if not snapshot.exists:
            snapshot = self._username_index.document(username_key).get()
        if not snapshot.exists:
            return None
        user_id = (snapshot.to_dict() or {}).get("user_id")
        if not user_id:
            return None
        user_ref = self._users.document(str(user_id))

        @self._firestore.transactional
        def _touch(transaction):
            user_snapshot = user_ref.get(transaction=transaction)
            if not user_snapshot.exists:
                return None
            now = _now_iso()
            transaction.update(user_ref, {"last_login_at": now})
            record = user_snapshot.to_dict() or {}
            record["last_login_at"] = now
            return record

        return _touch(self._client.transaction())

    def upsert_google_user(
        self,
        subject: str,
        email: str | None,
        display_name: str | None,
        id_token_jti: str | None = None,
    ) -> dict[str, Any]:
        subject_key = str(subject).strip()
        google_ref = self._google_index.document(
            google_subject_document_id(subject_key)
        )
        legacy_google_ref = self._google_index.document(subject_key)
        now = _now_iso()
        username_value = email or subject_key
        username_ref = self._username_index.document(
            username_document_id(username_value)
        )
        legacy_username_ref = self._username_index.document(username_value.lower().strip())

        @self._firestore.transactional
        def _upsert(transaction):
            index_snapshot = google_ref.get(transaction=transaction)
            if not index_snapshot.exists:
                index_snapshot = legacy_google_ref.get(transaction=transaction)
            if index_snapshot.exists:
                user_id = (index_snapshot.to_dict() or {}).get("user_id")
                if not user_id:
                    return None
                user_ref = self._users.document(str(user_id))
                user_snapshot = user_ref.get(transaction=transaction)
                if not user_snapshot.exists:
                    return None
                record = user_snapshot.to_dict() or {}
                record["email"] = email or record.get("email")
                record["display_name"] = display_name or record.get("display_name") or email or subject_key
                record["username"] = username_value
                record["last_login_at"] = now
                if id_token_jti:
                    record["last_google_jti"] = id_token_jti
                transaction.update(user_ref, record)
                transaction.set(
                    username_ref,
                    {"user_id": user_id, "username": username_value, "created_at": record.get("created_at", now)},
                )
                transaction.set(
                    legacy_username_ref,
                    {"user_id": user_id, "username": username_value, "created_at": record.get("created_at", now)},
                )
                return record

            user_ref = self._users.document(new_google_user_id(email, subject_key))
            record = {
                "user_id": user_ref.id,
                "auth_provider": "google",
                "username": username_value,
                "display_name": display_name or email or subject_key,
                "email": email,
                "google_subject": subject_key,
                "created_at": now,
                "last_login_at": now,
            }
            if id_token_jti:
                record["last_google_jti"] = id_token_jti
            transaction.set(user_ref, record)
            transaction.set(google_ref, {"user_id": user_ref.id, "subject": subject_key, "created_at": now})
            transaction.set(username_ref, {"user_id": user_ref.id, "username": username_value, "created_at": now})
            transaction.set(legacy_username_ref, {"user_id": user_ref.id, "username": username_value, "created_at": now})
            return record

        return _upsert(self._client.transaction())


def create_user_repository(settings: ServerSettings) -> UserRepository:
    if settings.repository_backend == "firestore":
        return FirestoreUserRepository(
            project_id=settings.gcp_project_id,
            collection_name=settings.firestore_users_collection,
            username_index_collection=settings.firestore_usernames_collection,
            google_index_collection=settings.firestore_google_identities_collection,
        )
    return InMemoryUserRepository()
