"""MagnetBox worker loop.

Consumes queued job JSON files from the inbox, updates the SQLite job row,
and archives the payload into completed/failed directories.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from pathlib import Path

from app import settings
from app.db import connection
from worker import job_store

PROCESSING_DELAY_SECONDS = float(os.getenv("MAGNETBOX_WORKER_DELAY_SECONDS", "0"))


def _ensure_job_record(job_id: str, payload: dict[str, object]) -> None:
    submitted_by = payload.get("submitted_by") if isinstance(payload.get("submitted_by"), str) else None
    created_at = payload.get("created_at") if isinstance(payload.get("created_at"), str) else job_store.utc_now()
    magnet_uri = payload.get("magnet_uri") if isinstance(payload.get("magnet_uri"), str) else ""
    with connection(settings.DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO jobs (job_id, magnet_uri, submitted_by, status, created_at, updated_at)
            VALUES (?, ?, ?, 'queued', ?, ?)
            """,
            (job_id, magnet_uri, submitted_by, created_at, created_at),
        )


def _update_job(job_id: str, *, status: str, message: str | None = None, claimed_at: str | None = None, completed_at: str | None = None, output_path: str | None = None, error_message: str | None = None) -> None:
    with connection(settings.DB_PATH) as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?,
                status_message = ?,
                claimed_at = COALESCE(?, claimed_at),
                completed_at = COALESCE(?, completed_at),
                output_path = COALESCE(?, output_path),
                error_message = ?,
                updated_at = ?
            WHERE job_id = ?
            """,
            (
                status,
                message,
                claimed_at,
                completed_at,
                output_path,
                error_message,
                job_store.utc_now(),
                job_id,
            ),
        )
        conn.execute(
            """
            INSERT INTO job_events (job_id, event_type, message, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (job_id, "status_change", message or status, job_store.utc_now()),
        )


def _process_payload(job_file: Path, payload: dict[str, object]) -> bool:
    job_id = payload.get("job_id")
    magnet_uri = payload.get("magnet_uri")
    if not isinstance(job_id, str) or not job_id:
        job_store.archive_job_file(job_file, success=False)
        return False
    _ensure_job_record(job_id, payload)
    if not isinstance(magnet_uri, str) or not magnet_uri.startswith("magnet:?"):
        _update_job(job_id, status="failed", message="Invalid or missing magnet URI.", error_message="Invalid or missing magnet URI.")
        job_store.archive_job_file(job_file, success=False)
        return False

    claimed_at = job_store.utc_now()
    _update_job(job_id, status="processing", message="Job claimed by worker.", claimed_at=claimed_at)

    if PROCESSING_DELAY_SECONDS > 0:
        time.sleep(PROCESSING_DELAY_SECONDS)

    completed_path = job_store.archive_job_file(job_file, success=True)
    completed_at = job_store.utc_now()
    _update_job(
        job_id,
        status="completed",
        message="Job processed successfully.",
        completed_at=completed_at,
        output_path=str(completed_path),
        error_message=None,
    )
    return True


def process_pending_jobs_once() -> int:
    settings.INBOX_DIR.mkdir(parents=True, exist_ok=True)
    processed = 0
    for job_file in sorted(settings.INBOX_DIR.glob("*.json")):
        claimed_file = job_store.claim_job_file(job_file)
        try:
            payload = json.loads(claimed_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            job_store.archive_job_file(claimed_file, success=False)
            continue
        if isinstance(payload, dict) and _process_payload(claimed_file, payload):
            processed += 1
        else:
            if claimed_file.exists():
                job_store.archive_job_file(claimed_file, success=False)
    return processed


def run_worker_loop(interval_seconds: float = 5.0, stop_event: threading.Event | None = None) -> None:
    while True:
        processed = process_pending_jobs_once()
        if processed:
            print(f"processed {processed} job(s)")
        if stop_event is not None and stop_event.is_set():
            return
        if interval_seconds > 0:
            time.sleep(interval_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MagnetBox worker.")
    parser.add_argument("--daemon", action="store_true", help="Keep polling for queued jobs instead of exiting after one pass.")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds to sleep between daemon polls.")
    args = parser.parse_args(argv)

    if args.daemon:
        try:
            run_worker_loop(interval_seconds=args.interval)
        except KeyboardInterrupt:
            print("worker stopped")
        return 0

    processed = process_pending_jobs_once()
    print(f"processed {processed} job(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
