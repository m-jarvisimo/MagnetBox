"""Shared runtime settings for MagnetBox."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DB_DIR = DATA_DIR / "db"
DB_PATH = DB_DIR / "magnetbox.sqlite3"
INBOX_DIR = DATA_DIR / "inbox"
PROCESSING_DIR = DATA_DIR / "processing"
COMPLETED_DIR = DATA_DIR / "completed"
FAILED_DIR = DATA_DIR / "failed"
LOG_DIR = PROJECT_ROOT / "logs"

SECRET_KEY = os.getenv("MAGNETBOX_SECRET_KEY", "change-me-in-production")
SESSION_COOKIE_NAME = os.getenv("MAGNETBOX_SESSION_COOKIE", "magnetbox_session")
MAX_MAGNET_LENGTH = int(os.getenv("MAGNETBOX_MAX_MAGNET_LENGTH", "4096"))

RUNTIME_DIRECTORIES = (
    DATA_DIR,
    DB_DIR,
    INBOX_DIR,
    PROCESSING_DIR,
    COMPLETED_DIR,
    FAILED_DIR,
    LOG_DIR,
)
