from __future__ import annotations

import argparse
import json
from pathlib import Path

from demo.schemas import UserManifest, UserManifestEntry, utc_now_iso
from shared.identifiers import new_google_user_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed demo users into Firestore.")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--collection", default="focusflow_users")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("demo/results/user-manifest.json"))
    return parser


def build_seed_entries(count: int) -> list[UserManifestEntry]:
    created_at = utc_now_iso()
    entries: list[UserManifestEntry] = []
    for index in range(1, count + 1):
        email = f"demo-user-{index:03d}@example.edu"
        subject = f"demo-subject-{index:03d}"
        display_name = f"Demo User {index:03d}"
        user_id = new_google_user_id(email, subject)
        entries.append(
            UserManifestEntry(
                index=index,
                user_id=user_id,
                email=email,
                display_name=display_name,
                auth_provider="google",
                google_subject=subject,
                created_at=created_at,
            )
        )
    return entries


def seed_firestore_users(
    *,
    project_id: str,
    collection_name: str,
    entries: list[UserManifestEntry],
) -> None:
    try:
        from google.cloud import firestore
    except ImportError as exc:
        raise SystemExit(
            "google-cloud-firestore is required to seed demo users. Install server requirements first."
        ) from exc

    client = firestore.Client(project=project_id or None)
    collection = client.collection(collection_name)
    batch = client.batch()
    writes = 0
    for entry in entries:
        record = {
            "user_id": entry.user_id,
            "auth_provider": entry.auth_provider,
            "username": entry.email,
            "email": entry.email,
            "display_name": entry.display_name,
            "google_subject": entry.google_subject,
            "created_at": entry.created_at,
            "last_login_at": entry.created_at,
        }
        batch.set(collection.document(entry.user_id), record)
        writes += 1
        if writes % 400 == 0:
            batch.commit()
            batch = client.batch()
    if writes % 400:
        batch.commit()


def main() -> None:
    args = build_parser().parse_args()
    if not args.count or args.count < 1:
        raise SystemExit("--count must be at least 1")

    entries = build_seed_entries(args.count)
    if args.project_id.strip():
        seed_firestore_users(
            project_id=args.project_id.strip(),
            collection_name=args.collection.strip() or "focusflow_users",
            entries=entries,
        )

    manifest = UserManifest(
        created_at=utc_now_iso(),
        collection=args.collection.strip() or "focusflow_users",
        limit=args.count,
        entries=entries,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"seeded={len(entries)} output={args.output}")


if __name__ == "__main__":
    main()
