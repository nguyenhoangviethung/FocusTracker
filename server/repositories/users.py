from __future__ import annotations

import threading
from typing import Any, Protocol

from server.config import ServerSettings
from shared.contracts import utc_now
from shared.identifiers import new_google_user_id, new_password_user_id


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
        self._google_index: dict[str, str] = {}
        self._lock = threading.Lock()

    def _find_user_by_username(self, username: str) -> dict[str, Any] | None:
        username_key = username.lower().strip()
        for user in self._users.values():
            if str(user.get("username") or "").lower().strip() != username_key:
                continue
            return dict(user)
        return None

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        with self._lock:
            return self._find_user_by_username(username)

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
            if self._find_user_by_username(username_key):
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
            return dict(record)

    def login_password_user(self, username: str) -> dict[str, Any] | None:
        with self._lock:
            user = self._find_user_by_username(username)
            if not user or str(user.get("auth_provider") or "") != "password":
                return None
            stored = self._users.get(str(user["user_id"]))
            if not stored:
                return None
            user = stored
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
            return dict(record)


class FirestoreUserRepository:
    def __init__(self, project_id: str, collection_name: str) -> None:
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-firestore is required for FOCUSFLOW_REPOSITORY=firestore"
            ) from exc

        self._firestore = firestore
        self._client = firestore.Client(project=project_id or None)
        self._users = self._client.collection(collection_name)

    def _users_by_username(self, username: str) -> list[dict[str, Any]]:
        username_key = username.lower().strip()
        query = self._users.where("username", "==", username_key)
        return [doc.to_dict() or {} for doc in query.get() if doc.exists]

    def _user_by_google_subject(self, subject: str) -> dict[str, Any] | None:
        query = self._users.where("google_subject", "==", subject.strip())
        for doc in query.get():
            if doc.exists:
                return doc.to_dict() or {}
        return None

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        for record in self._users_by_username(username):
            if str(record.get("auth_provider") or "") == "password":
                return record
        return None

    def get_by_google_subject(self, subject: str) -> dict[str, Any] | None:
        return self._user_by_google_subject(subject)

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
        username_query = self._users.where("username", "==", username_key)

        @self._firestore.transactional
        def _create(transaction):
            if username_query.get(transaction=transaction):
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
            return record

        return _create(self._client.transaction())

    def login_password_user(self, username: str) -> dict[str, Any] | None:
        username_key = username.lower().strip()
        query = self._users.where("username", "==", username_key)

        @self._firestore.transactional
        def _touch(transaction):
            snapshots = query.get(transaction=transaction)
            if not snapshots:
                return None
            chosen = None
            for doc in snapshots:
                payload = doc.to_dict() or {}
                if str(payload.get("auth_provider") or "") == "password":
                    chosen = (doc.reference, payload)
                    break
            if chosen is None:
                return None
            user_ref, user_payload = chosen
            now = _now_iso()
            transaction.update(user_ref, {"last_login_at": now})
            user_payload["last_login_at"] = now
            return user_payload

        return _touch(self._client.transaction())

    def upsert_google_user(
        self,
        subject: str,
        email: str | None,
        display_name: str | None,
        id_token_jti: str | None = None,
    ) -> dict[str, Any]:
        subject_key = str(subject).strip()
        now = _now_iso()
        username_value = email or subject_key
        user_query = self._users.where("google_subject", "==", subject_key)
        username_query = self._users.where("username", "==", username_value.lower().strip())

        @self._firestore.transactional
        def _upsert(transaction):
            existing_users = user_query.get(transaction=transaction)
            if existing_users:
                user_snapshot = existing_users[0]
                record = user_snapshot.to_dict() or {}
                record["email"] = email or record.get("email")
                record["display_name"] = display_name or record.get("display_name") or email or subject_key
                record["username"] = username_value
                record["last_login_at"] = now
                if id_token_jti:
                    record["last_google_jti"] = id_token_jti
                transaction.update(user_snapshot.reference, record)
                return record

            user_ref = self._users.document(new_google_user_id(email, subject_key))
            if username_query.get(transaction=transaction):
                username_value = subject_key
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
            return record

        return _upsert(self._client.transaction())


def create_user_repository(settings: ServerSettings) -> UserRepository:
    if settings.repository_backend == "firestore":
        return FirestoreUserRepository(
            project_id=settings.gcp_project_id,
            collection_name=settings.firestore_users_collection,
        )
    return InMemoryUserRepository()
