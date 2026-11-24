from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_MONTHLY_LIMIT = int(os.getenv("DEFAULT_MONTHLY_LIMIT", "1000"))


class UsageLimitExceeded(Exception):
    def __init__(self, message: str, *, rate_limited: bool = False):
        super().__init__(message)
        self.rate_limited = rate_limited


def _db_path() -> str:
    return os.getenv("DATABASE_PATH", "data/invoice_api.db")


def _connect() -> sqlite3.Connection:
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE, monthly_limit INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free', stripe_customer_id TEXT,
            subscription_id TEXT, subscription_status TEXT NOT NULL DEFAULT 'active',
            past_due_since TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT, api_key_id INTEGER NOT NULL,
            used_at TEXT NOT NULL, FOREIGN KEY(api_key_id) REFERENCES api_keys(id))""")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(api_keys)").fetchall()}
        for name, definition in {
            "plan": "TEXT NOT NULL DEFAULT 'free'",
            "stripe_customer_id": "TEXT",
            "subscription_id": "TEXT",
            "subscription_status": "TEXT NOT NULL DEFAULT 'active'",
            "past_due_since": "TEXT",
        }.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE api_keys ADD COLUMN {name} {definition}")
        conn.execute("""CREATE TABLE IF NOT EXISTS checkout_claims (
            checkout_session_id TEXT PRIMARY KEY,
            api_key_id INTEGER NOT NULL UNIQUE,
            claimed_at TEXT NOT NULL,
            encrypted_api_key TEXT,
            browser_claimed_at TEXT,
            email_sent_at TEXT,
            delivery_email TEXT,
            FOREIGN KEY(api_key_id) REFERENCES api_keys(id))""")
        checkout_columns = {row["name"] for row in conn.execute("PRAGMA table_info(checkout_claims)").fetchall()}
        for name, definition in {
            "encrypted_api_key": "TEXT",
            "browser_claimed_at": "TEXT",
            "email_sent_at": "TEXT",
            "delivery_email": "TEXT",
        }.items():
            if name not in checkout_columns:
                conn.execute(f"ALTER TABLE checkout_claims ADD COLUMN {name} {definition}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_key_date ON api_usage(api_key_id, used_at)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_subscription ON api_keys(subscription_id) WHERE subscription_id IS NOT NULL")
        conn.execute("""CREATE TABLE IF NOT EXISTS stripe_webhook_events (
            event_id TEXT PRIMARY KEY, event_created INTEGER NOT NULL,
            event_type TEXT NOT NULL, received_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS stripe_subscription_state (
            subscription_id TEXT PRIMARY KEY, last_event_created INTEGER NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS public_rate_limit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, subject_hash TEXT NOT NULL,
            action TEXT NOT NULL, created_at REAL NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS api_key_recovery_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL,
            customer_id TEXT NOT NULL, code_hash TEXT NOT NULL,
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, used_at TEXT)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_recovery_email ON api_key_recovery_codes(email,created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_public_rate_limits ON public_rate_limit_events(subject_hash,action,created_at)")


def hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def create_api_key(label: str, monthly_limit: int | None = None) -> tuple[str, dict[str, Any]]:
    raw_key = ("iia_test_" if os.getenv("STRIPE_SECRET_KEY", "").startswith("sk_test_") else "iia_live_") + secrets.token_urlsafe(32)
    limit = monthly_limit or DEFAULT_MONTHLY_LIMIT
    if limit < 1:
        raise ValueError("monthly_limit must be positive")
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO api_keys(label, key_hash, monthly_limit, created_at) VALUES (?, ?, ?, ?)",
            (label, hash_key(raw_key), limit, created_at))
        key_id = cursor.lastrowid
    return raw_key, {"id": key_id, "label": label, "monthly_limit": limit, "created_at": created_at}


def _api_key_fernet() -> Fernet:
    secret = os.getenv("API_KEY_ENCRYPTION_KEY")
    if not secret:
        raise RuntimeError("API_KEY_ENCRYPTION_KEY must be configured before issuing customer API keys.")
    try:
        return Fernet(secret.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("API_KEY_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def provision_checkout_key(
    session_id: str, email: str, plan: str, customer_id: str,
    subscription_id: str, monthly_limit: int, *, claim: bool = False,
) -> str:
    """Create once and keep the raw key encrypted so webhook retries can deliver it."""
    fernet = _api_key_fernet()
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            """SELECT encrypted_api_key,browser_claimed_at FROM checkout_claims
               WHERE checkout_session_id=?""",
            (session_id,),
        ).fetchone()
        if existing:
            if claim and existing["browser_claimed_at"] is not None:
                raise ValueError("This checkout session's API key has already been claimed in the browser. Check the delivery email.")
            encrypted = existing["encrypted_api_key"]
            if not encrypted:
                raise RuntimeError("The existing checkout key cannot be recovered securely. Contact support.")
            try:
                raw_key = fernet.decrypt(encrypted.encode("ascii")).decode("utf-8")
            except (InvalidToken, ValueError) as exc:
                raise RuntimeError("The checkout key could not be decrypted. Check API_KEY_ENCRYPTION_KEY.") from exc
            if claim:
                conn.execute(
                    "UPDATE checkout_claims SET browser_claimed_at=? WHERE checkout_session_id=?",
                    (now, session_id),
                )
            return raw_key

        raw_key = ("iia_test_" if os.getenv("STRIPE_SECRET_KEY", "").startswith("sk_test_") else "iia_live_") + secrets.token_urlsafe(32)
        encrypted = fernet.encrypt(raw_key.encode("utf-8")).decode("ascii")
        cursor = conn.execute(
            """INSERT INTO api_keys(label,key_hash,monthly_limit,active,created_at,plan,
               stripe_customer_id,subscription_id) VALUES (?,?,?,?,?,?,?,?)""",
            (email, hash_key(raw_key), monthly_limit, 1, now, plan, customer_id, subscription_id),
        )
        conn.execute(
            """INSERT INTO checkout_claims(
               checkout_session_id,api_key_id,claimed_at,encrypted_api_key,
               browser_claimed_at,delivery_email) VALUES (?,?,?,?,?,?)""",
            (session_id, cursor.lastrowid, now, encrypted, now if claim else None, email),
        )
    return raw_key


def checkout_key_delivery(session_id: str) -> dict[str, Any] | None:
    fernet = _api_key_fernet()
    with _connect() as conn:
        row = conn.execute(
            """SELECT encrypted_api_key,delivery_email,email_sent_at
               FROM checkout_claims WHERE checkout_session_id=?""",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    encrypted = row["encrypted_api_key"]
    if not encrypted:
        raise RuntimeError("The checkout API key is not available for delivery.")
    try:
        raw_key = fernet.decrypt(encrypted.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise RuntimeError("The checkout key could not be decrypted. Check API_KEY_ENCRYPTION_KEY.") from exc
    return {
        "email": row["delivery_email"],
        "api_key": raw_key,
        "email_sent_at": row["email_sent_at"],
    }


def mark_checkout_email_sent(session_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE checkout_claims SET email_sent_at=? WHERE checkout_session_id=?",
            (datetime.now(timezone.utc).isoformat(), session_id),
        )


def get_key_record(api_key: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id,label,monthly_limit,active,plan,stripe_customer_id,subscription_id,subscription_status,past_due_since FROM api_keys WHERE key_hash=?",
            (hash_key(api_key),)).fetchone()
    return dict(row) if row else None


def key_usage(key_id: int, monthly_limit: int) -> dict[str, int]:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS used FROM api_usage WHERE api_key_id=? AND substr(used_at,1,7)=?",
                           (key_id, month)).fetchone()
    used = int(row["used"])
    return {"used": used, "monthly_limit": monthly_limit, "remaining": max(0, monthly_limit-used)}


def reserve_usage(key_id: int, monthly_limit: int, requests_per_minute: int) -> None:
    """Atomically meter an attempt before expensive work, preventing quota races."""
    now = datetime.now(timezone.utc)
    now_text = now.isoformat()
    month = now.strftime("%Y-%m")
    cutoff = (now - timedelta(seconds=60)).isoformat()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        used = conn.execute(
            "SELECT COUNT(*) AS n FROM api_usage WHERE api_key_id=? AND substr(used_at,1,7)=?",
            (key_id, month)).fetchone()["n"]
        if int(used) >= monthly_limit:
            raise UsageLimitExceeded("Monthly API usage limit reached.")
        recent = conn.execute(
            "SELECT COUNT(*) AS n FROM api_usage WHERE api_key_id=? AND used_at>=?",
            (key_id, cutoff)).fetchone()["n"]
        if int(recent) >= requests_per_minute:
            raise UsageLimitExceeded("Per-minute API rate limit reached. Please retry shortly.", rate_limited=True)
        conn.execute("INSERT INTO api_usage(api_key_id,used_at) VALUES (?,?)", (key_id, now_text))


def record_usage(key_id: int) -> None:
    # Backward-compatible helper for administrative/test use. API requests
    # should use reserve_usage so quota checks and increments are atomic.
    with _connect() as conn:
        conn.execute("INSERT INTO api_usage(api_key_id,used_at) VALUES (?,?)",
                     (key_id, datetime.now(timezone.utc).isoformat()))


def reserve_public_rate_limit(subject: str, action: str, limit: int, window_seconds: int) -> None:
    """Coarse IP-based throttle for unauthenticated billing endpoints."""
    import time
    subject_hash = hashlib.sha256(subject.encode("utf-8")).hexdigest()
    now = time.time()
    cutoff = now - window_seconds
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM public_rate_limit_events WHERE created_at<?", (now - 86400,))
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM public_rate_limit_events WHERE subject_hash=? AND action=? AND created_at>=?",
            (subject_hash, action, cutoff),
        ).fetchone()["n"]
        if int(count) >= limit:
            raise UsageLimitExceeded("Too many requests. Please wait and try again.", rate_limited=True)
        conn.execute(
            "INSERT INTO public_rate_limit_events(subject_hash,action,created_at) VALUES (?,?,?)",
            (subject_hash, action, now),
        )


def requests_in_last_minute(key_id: int) -> int:
    cutoff = (datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat()
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS used FROM api_usage WHERE api_key_id=? AND used_at>=?",
                           (key_id, cutoff)).fetchone()
    return int(row["used"])


def _subscription_access_state(status: str) -> tuple[int, str | None]:
    now = datetime.now(timezone.utc).isoformat()
    if status in {"active", "trialing"}:
        return 1, None
    if status == "past_due":
        return 1, now
    return 0, None


def get_key_record_by_customer_id(customer_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """SELECT id,label,monthly_limit,active,plan,stripe_customer_id,
               subscription_id,subscription_status,past_due_since
               FROM api_keys WHERE stripe_customer_id=? ORDER BY id DESC LIMIT 1""",
            (customer_id,),
        ).fetchone()
    return dict(row) if row else None


def _recovery_code_hash(code: str) -> str:
    secret = os.getenv("API_KEY_ENCRYPTION_KEY")
    if not secret:
        raise RuntimeError("API_KEY_ENCRYPTION_KEY must be configured for account recovery.")
    return hmac.new(secret.encode("utf-8"), code.encode("utf-8"), hashlib.sha256).hexdigest()


def create_recovery_code(email: str, customer_id: str, code: str) -> None:
    now = datetime.now(timezone.utc)
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE api_key_recovery_codes SET used_at=? WHERE email=? AND used_at IS NULL",
            (now.isoformat(), email.lower()),
        )
        conn.execute(
            """INSERT INTO api_key_recovery_codes(
               email,customer_id,code_hash,created_at,expires_at)
               VALUES (?,?,?,?,?)""",
            (
                email.lower(), customer_id, _recovery_code_hash(code),
                now.isoformat(), (now + timedelta(minutes=10)).isoformat(),
            ),
        )


def consume_recovery_code(email: str, code: str) -> str | None:
    now = datetime.now(timezone.utc)
    supplied_hash = _recovery_code_hash(code)
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT id,customer_id,code_hash,expires_at,attempts,used_at
               FROM api_key_recovery_codes WHERE email=? ORDER BY id DESC LIMIT 1""",
            (email.lower(),),
        ).fetchone()
        if not row or row["used_at"] or int(row["attempts"]) >= 5:
            return None
        if datetime.fromisoformat(row["expires_at"]) < now:
            conn.execute("UPDATE api_key_recovery_codes SET used_at=? WHERE id=?", (now.isoformat(), row["id"]))
            return None
        if not hmac.compare_digest(row["code_hash"], supplied_hash):
            conn.execute("UPDATE api_key_recovery_codes SET attempts=attempts+1 WHERE id=?", (row["id"],))
            return None
        conn.execute("UPDATE api_key_recovery_codes SET used_at=? WHERE id=?", (now.isoformat(), row["id"]))
        return str(row["customer_id"])


def set_subscription(key_id: int, plan: str, status: str, customer_id: str | None,
                     subscription_id: str, monthly_limit: int) -> None:
    active, past_due_since = _subscription_access_state(status)
    with _connect() as conn:
        conn.execute("""UPDATE api_keys SET plan=?,active=?,monthly_limit=?,stripe_customer_id=?,
                     subscription_id=?,subscription_status=?,
                     past_due_since=CASE WHEN ?='past_due' THEN COALESCE(past_due_since,?) ELSE NULL END
                     WHERE id=?""",
                     (plan, active, monthly_limit, customer_id, subscription_id, status,
                      status, past_due_since, key_id))


def set_subscription_by_id(subscription_id: str, status: str,
                            plan: str | None = None, monthly_limit: int | None = None) -> None:
    active, past_due_since = _subscription_access_state(status)
    with _connect() as conn:
        conn.execute("""UPDATE api_keys SET active=?,subscription_status=?,
                     past_due_since=CASE WHEN ?='past_due' THEN COALESCE(past_due_since,?) ELSE NULL END,
                     plan=COALESCE(?,plan),monthly_limit=COALESCE(?,monthly_limit)
                     WHERE subscription_id=?""",
                     (active, status, status, past_due_since, plan, monthly_limit, subscription_id))


def apply_stripe_subscription_event(
    event_id: str, event_created: int, event_type: str, subscription_id: str,
    status: str, plan: str | None = None, customer_id: str | None = None,
    monthly_limit: int | None = None,
) -> str:
    """Atomically deduplicate webhook events and ignore older subscription events."""
    active, past_due_since = _subscription_access_state(status)
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM stripe_webhook_events WHERE event_id=?", (event_id,)).fetchone():
            return "duplicate"
        last = conn.execute(
            "SELECT last_event_created FROM stripe_subscription_state WHERE subscription_id=?",
            (subscription_id,),
        ).fetchone()
        if last and int(event_created) < int(last["last_event_created"]):
            conn.execute(
                "INSERT INTO stripe_webhook_events(event_id,event_created,event_type,received_at) VALUES (?,?,?,?)",
                (event_id, int(event_created), event_type, now),
            )
            return "stale"
        conn.execute("""UPDATE api_keys SET active=?,subscription_status=?,
                     past_due_since=CASE WHEN ?='past_due' THEN COALESCE(past_due_since,?) ELSE NULL END,
                     plan=COALESCE(?,plan),monthly_limit=COALESCE(?,monthly_limit),
                     stripe_customer_id=COALESCE(?,stripe_customer_id)
                     WHERE subscription_id=?""",
                     (active, status, status, past_due_since, plan, monthly_limit, customer_id, subscription_id))
        conn.execute("""INSERT INTO stripe_subscription_state(subscription_id,last_event_created)
                     VALUES (?,?) ON CONFLICT(subscription_id) DO UPDATE SET
                     last_event_created=MAX(last_event_created,excluded.last_event_created)""",
                     (subscription_id, int(event_created)))
        conn.execute(
            "INSERT INTO stripe_webhook_events(event_id,event_created,event_type,received_at) VALUES (?,?,?,?)",
            (event_id, int(event_created), event_type, now),
        )
    return "applied"


def record_stripe_event(event_id: str, event_created: int, event_type: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        try:
            conn.execute(
                "INSERT INTO stripe_webhook_events(event_id,event_created,event_type,received_at) VALUES (?,?,?,?)",
                (event_id, int(event_created), event_type, now),
            )
        except sqlite3.IntegrityError:
            return "duplicate"
    return "recorded"


def rotate_api_key(key_id: int) -> str:
    """Rotate a key in place so quota history and subscription linkage are preserved."""
    raw_key = ("iia_test_" if os.getenv("STRIPE_SECRET_KEY", "").startswith("sk_test_") else "iia_live_") + secrets.token_urlsafe(32)
    with _connect() as conn:
        cursor = conn.execute("UPDATE api_keys SET key_hash=? WHERE id=? AND active=1", (hash_key(raw_key), key_id))
        if cursor.rowcount != 1:
            raise ValueError("API key is inactive or no longer exists.")
    return raw_key


def revoke_api_key(key_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE api_keys SET active=0 WHERE id=?", (key_id,))
