#!/usr/bin/env python3
"""Initialize MagnetBox runtime directories and SQLite schema."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.auth import hash_password
from app.settings import DB_PATH, RUNTIME_DIRECTORIES

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL UNIQUE,
    magnet_uri TEXT NOT NULL,
    submitted_by TEXT,
    status TEXT NOT NULL,
    status_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    claimed_at TEXT,
    completed_at TEXT,
    output_path TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at
    ON jobs (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_job_events_job_id_created_at
    ON job_events (job_id, created_at DESC);
"""


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_runtime_directories() -> None:
    for directory in RUNTIME_DIRECTORIES:
        directory.mkdir(parents=True, exist_ok=True)


def seed_initial_admin_user(conn: sqlite3.Connection) -> bool:
    username = os.getenv("MAGNETBOX_ADMIN_USERNAME")
    password_hash = os.getenv("MAGNETBOX_ADMIN_PASSWORD_HASH")
    password = os.getenv("MAGNETBOX_ADMIN_PASSWORD")

    if password and not password_hash:
        password_hash = hash_password(password)

    if not username and not password_hash and not password:
        return False

    if not username or not password_hash:
        raise RuntimeError(
            "Set MAGNETBOX_ADMIN_USERNAME with MAGNETBOX_ADMIN_PASSWORD_HASH or MAGNETBOX_ADMIN_PASSWORD"
        )

    existing = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
    if existing is not None:
        return False

    conn.execute(
        """
        INSERT INTO users (username, password_hash, is_active, created_at, updated_at)
        VALUES (?, ?, 1, ?, ?)
        """,
        (username, password_hash, utc_now(), utc_now()),
    )
    return True


def initialize_database() -> None:
    ensure_runtime_directories()
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA_SQL)
        seed_initial_admin_user(conn)
        conn.commit()


def main() -> int:
    initialize_database()
    print(f"initialized database at {DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
