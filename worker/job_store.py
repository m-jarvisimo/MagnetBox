"""Shared job-store helpers for MagnetBox."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import settings
from app.db import connection


def _resolve_db_path(db_path: Path | str | None = None) -> Path | str:
    return db_path if db_path is not None else settings.DB_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_job_id() -> str:
    return uuid.uuid4().hex


def create_job_record(job_id: str, magnet_uri: str, submitted_by: str | None = None, db_path: Path | str | None = None) -> None:
    with connection(_resolve_db_path(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO jobs (job_id, magnet_uri, submitted_by, status, created_at, updated_at)
            VALUES (?, ?, ?, 'queued', ?, ?)
            """,
            (job_id, magnet_uri, submitted_by, utc_now(), utc_now()),
        )


def get_job_record(job_id: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    with connection(_resolve_db_path(db_path)) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def update_job_status(job_id: str, status: str, message: str | None = None, db_path: Path | str | None = None) -> None:
    with connection(_resolve_db_path(db_path)) as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, status_message = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (status, message, utc_now(), job_id),
        )
        conn.execute(
            """
            INSERT INTO job_events (job_id, event_type, message, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (job_id, "status_change", message or status, utc_now()),
        )


def record_event(job_id: str, event_type: str, message: str | None = None, db_path: Path | str | None = None) -> None:
    with connection(_resolve_db_path(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO job_events (job_id, event_type, message, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (job_id, event_type, message, utc_now()),
        )


def write_job_file(job_id: str, payload: dict[str, Any]) -> Path:
    settings.INBOX_DIR.mkdir(parents=True, exist_ok=True)
    inbox_path = settings.INBOX_DIR / f"{job_id}.json"
    tmp_path = inbox_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(inbox_path)
    return inbox_path


def claim_job_file(job_file: Path) -> Path:
    settings.PROCESSING_DIR.mkdir(parents=True, exist_ok=True)
    target = settings.PROCESSING_DIR / job_file.name
    shutil.move(str(job_file), target)
    return target


def archive_job_file(job_file: Path, success: bool) -> Path:
    destination_dir = settings.COMPLETED_DIR if success else settings.FAILED_DIR
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / job_file.name
    shutil.move(str(job_file), destination)
    return destination
