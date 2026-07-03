"""Authentication helpers for MagnetBox."""

from __future__ import annotations

import bcrypt
from pathlib import Path

from app import settings
from app.db import connection


def _resolve_db_path(db_path: Path | str | None = None) -> Path | str:
    return db_path if db_path is not None else settings.DB_PATH


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password must not be empty")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def get_user_record(username: str, db_path: Path | str | None = None):
    with connection(_resolve_db_path(db_path)) as conn:
        return conn.execute(
            "SELECT username, password_hash, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()


def authenticate_user(username: str, password: str, db_path: Path | str | None = None) -> bool:
    row = get_user_record(username, db_path=db_path)
    if row is None or not row["is_active"]:
        return False
    return verify_password(password, row["password_hash"])
