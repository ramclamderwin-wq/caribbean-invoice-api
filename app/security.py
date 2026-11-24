from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_MONTHLY_LIMIT = int(os.getenv("DEFAULT_MONTHLY_LIMIT", "1000"))


def _db_path() -> str:
    return os.getenv("DATABASE_PATH", "data/invoice_api.db")


def _connect() -> sqlite3.Connection:
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                monthly_limit INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key_id INTEGER NOT NULL,
                used_at TEXT NOT NULL,
                FOREIGN KEY(api_key_id) REFERENCES api_keys(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_key_date ON api_usage(api_key_id, used_at)")


def hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def create_api_key(label: str, monthly_limit: int | None = None) -> tuple[str, dict[str, Any]]:
    raw_key = "iia_live_" + secrets.token_urlsafe(32)
    limit = monthly_limit or DEFAULT_MONTHLY_LIMIT
    if limit < 1:
        raise ValueError("monthly_limit must be positive")
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO api_keys(label, key_hash, monthly_limit, created_at) VALUES (?, ?, ?, ?)",
            (label, hash_key(raw_key), limit, created_at),
        )
        key_id = cursor.lastrowid
    return raw_key, {"id": key_id, "label": label, "monthly_limit": limit, "created_at": created_at}


def get_key_record(api_key: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, label, monthly_limit, active FROM api_keys WHERE key_hash = ?",
            (hash_key(api_key),),
        ).fetchone()
    return dict(row) if row else None


def get_usage(key_id: int) -> dict[str, int]:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS used FROM api_usage WHERE api_key_id = ? AND substr(used_at, 1, 7) = ?",
            (key_id, month),
        ).fetchone()
    used = int(row["used"])
    return {"used": used, "monthly_limit": 0, "remaining": 0}


def record_usage(key_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO api_usage(api_key_id, used_at) VALUES (?, ?)",
            (key_id, datetime.now(timezone.utc).isoformat()),
        )


def key_usage(key_id: int, monthly_limit: int) -> dict[str, int]:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS used FROM api_usage WHERE api_key_id = ? AND substr(used_at, 1, 7) = ?",
            (key_id, month),
        ).fetchone()
    used = int(row["used"])
    return {"used": used, "monthly_limit": monthly_limit, "remaining": max(0, monthly_limit - used)}

def requests_in_last_minute(key_id: int) -> int:
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS used FROM api_usage WHERE api_key_id = ? AND used_at >= ?",
            (key_id, cutoff),
        ).fetchone()
    return int(row["used"])
