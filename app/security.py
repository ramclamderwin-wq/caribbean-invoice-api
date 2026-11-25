from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_MONTHLY_LIMIT = int(os.getenv("DEFAULT_MONTHLY_LIMIT", "1000"))
SCHEMA_VERSION = 2
# Statuses that versions <= 0.3.0 wrote into subscription_status for holds.
LEGACY_HOLD_STATUSES = ("refunded", "refund_review", "disputed")
# Subscription statuses that grant API access (past_due only within grace).
ACCESS_GRANTING_STATUSES = ("active", "trialing", "past_due")
# SQL guard: a revoked key or one under an access hold never regains access
# from a Stripe event. Only an administrator clears a hold.
_ACCESS_BLOCKED_SQL = "(revoked_at IS NOT NULL OR access_hold_reason IS NOT NULL)"


class UsageLimitExceeded(Exception):
    def __init__(self, message: str, *, rate_limited: bool = False):
        super().__init__(message)
        self.rate_limited = rate_limited


def database_health_check() -> bool:
    """Confirm SQLite is reachable and can acquire a write reservation."""
    try:
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("SELECT 1").fetchone()
            conn.rollback()
        return True
    except sqlite3.Error:
        return False


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
            past_due_since TEXT, current_period_start TEXT, current_period_end TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT, api_key_id INTEGER NOT NULL,
            used_at TEXT NOT NULL, reservation_id TEXT,
            FOREIGN KEY(api_key_id) REFERENCES api_keys(id))""")
        usage_columns = {row["name"] for row in conn.execute("PRAGMA table_info(api_usage)").fetchall()}
        if "reservation_id" not in usage_columns:
            conn.execute("ALTER TABLE api_usage ADD COLUMN reservation_id TEXT")
        conn.execute("""CREATE TABLE IF NOT EXISTS api_request_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, api_key_id INTEGER NOT NULL,
            created_at TEXT NOT NULL, FOREIGN KEY(api_key_id) REFERENCES api_keys(id))""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_api_requests_key_time ON api_request_events(api_key_id,created_at)")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(api_keys)").fetchall()}
        for name, definition in {
            "plan": "TEXT NOT NULL DEFAULT 'free'",
            "stripe_customer_id": "TEXT",
            "subscription_id": "TEXT",
            "subscription_status": "TEXT NOT NULL DEFAULT 'active'",
            "past_due_since": "TEXT",
            "current_period_start": "TEXT",
            "current_period_end": "TEXT",
            # Access controls kept separate from Stripe's subscription status.
            "access_hold_reason": "TEXT",
            "access_hold_set_at": "TEXT",
            "hold_review_cutoff": "INTEGER",
            "revoked_at": "TEXT",
        }.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE api_keys ADD COLUMN {name} {definition}")
        # One-time, non-destructive data migration: earlier versions stored
        # refund/dispute holds in subscription_status. Copy them into the hold
        # column; the next Stripe subscription event restores the true status.
        legacy_holds = ",".join("?" for _ in LEGACY_HOLD_STATUSES)
        conn.execute(
            f"""UPDATE api_keys SET access_hold_reason=subscription_status,
                access_hold_set_at=COALESCE(access_hold_set_at,?), active=0
                WHERE access_hold_reason IS NULL AND subscription_status IN ({legacy_holds})""",
            (datetime.now(timezone.utc).isoformat(), *LEGACY_HOLD_STATUSES),
        )
        conn.execute("""CREATE TABLE IF NOT EXISTS checkout_claims (
            checkout_session_id TEXT PRIMARY KEY,
            api_key_id INTEGER NOT NULL UNIQUE,
            claimed_at TEXT NOT NULL,
            encrypted_api_key TEXT,
            browser_claimed_at TEXT,
            email_sent_at TEXT,
            email_delivery_claimed_at TEXT,
            delivery_email TEXT,
            FOREIGN KEY(api_key_id) REFERENCES api_keys(id))""")
        checkout_columns = {row["name"] for row in conn.execute("PRAGMA table_info(checkout_claims)").fetchall()}
        for name, definition in {
            "encrypted_api_key": "TEXT",
            "browser_claimed_at": "TEXT",
            "email_sent_at": "TEXT",
            "email_delivery_claimed_at": "TEXT",
            "delivery_email": "TEXT",
        }.items():
            if name not in checkout_columns:
                conn.execute(f"ALTER TABLE checkout_claims ADD COLUMN {name} {definition}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_key_date ON api_usage(api_key_id, used_at)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_subscription ON api_keys(subscription_id) WHERE subscription_id IS NOT NULL")
        conn.execute("""CREATE TABLE IF NOT EXISTS stripe_webhook_events (
            event_id TEXT PRIMARY KEY, event_created INTEGER NOT NULL,
            event_type TEXT NOT NULL, received_at TEXT NOT NULL)""")
        event_columns = {row["name"] for row in conn.execute("PRAGMA table_info(stripe_webhook_events)").fetchall()}
        for name in ("customer_id", "outcome"):
            if name not in event_columns:
                conn.execute(f"ALTER TABLE stripe_webhook_events ADD COLUMN {name} TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stripe_events_customer ON stripe_webhook_events(customer_id,event_created)")
        conn.execute("""CREATE TABLE IF NOT EXISTS admin_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
            actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT,
            detail TEXT, client_hash TEXT, success INTEGER NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_audit_time ON admin_audit_log(created_at)")
        conn.execute("""CREATE TABLE IF NOT EXISTS backup_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
            success INTEGER NOT NULL, detail TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS stripe_subscription_state (
            subscription_id TEXT PRIMARY KEY, last_event_created INTEGER NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS public_rate_limit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, subject_hash TEXT NOT NULL,
            action TEXT NOT NULL, created_at REAL NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS api_key_recovery_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL,
            customer_id TEXT NOT NULL, code_hash TEXT NOT NULL,
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, used_at TEXT,
            encrypted_api_key TEXT, delivered_at TEXT)""")
        recovery_columns = {row["name"] for row in conn.execute("PRAGMA table_info(api_key_recovery_codes)").fetchall()}
        for name in ("encrypted_api_key", "delivered_at"):
            if name not in recovery_columns:
                conn.execute(f"ALTER TABLE api_key_recovery_codes ADD COLUMN {name} TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_recovery_email ON api_key_recovery_codes(email,created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_public_rate_limits ON public_rate_limit_events(subject_hash,action,created_at)")
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


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
    subscription_id: str, monthly_limit: int, *,
    current_period_start: str | None = None, current_period_end: str | None = None,
) -> str:
    """Create once and keep the raw key encrypted so webhook retries can deliver it.

    The signed Stripe webhook is the only caller; the key is delivered by email.
    """
    fernet = _api_key_fernet()
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT encrypted_api_key FROM checkout_claims WHERE checkout_session_id=?",
            (session_id,),
        ).fetchone()
        if existing:
            encrypted = existing["encrypted_api_key"]
            if not encrypted:
                raise RuntimeError("The existing checkout key cannot be recovered securely. Contact support.")
            try:
                return fernet.decrypt(encrypted.encode("ascii")).decode("utf-8")
            except (InvalidToken, ValueError) as exc:
                raise RuntimeError("The checkout key could not be decrypted. Check API_KEY_ENCRYPTION_KEY.") from exc

        # A Stripe customer already under a billing hold (refund/dispute) keeps
        # that hold on any new subscription until an administrator reviews it.
        held = conn.execute(
            """SELECT access_hold_reason FROM api_keys WHERE stripe_customer_id=?
               AND access_hold_reason IS NOT NULL ORDER BY id DESC LIMIT 1""",
            (customer_id,),
        ).fetchone()
        hold_reason = held["access_hold_reason"] if held else None
        raw_key = ("iia_test_" if os.getenv("STRIPE_SECRET_KEY", "").startswith("sk_test_") else "iia_live_") + secrets.token_urlsafe(32)
        encrypted = fernet.encrypt(raw_key.encode("utf-8")).decode("ascii")
        cursor = conn.execute(
            """INSERT INTO api_keys(label,key_hash,monthly_limit,active,created_at,plan,
               stripe_customer_id,subscription_id,current_period_start,current_period_end,
               access_hold_reason,access_hold_set_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (email, hash_key(raw_key), monthly_limit, 0 if hold_reason else 1, now, plan,
             customer_id, subscription_id, current_period_start, current_period_end,
             hold_reason, now if hold_reason else None),
        )
        conn.execute(
            """INSERT INTO checkout_claims(
               checkout_session_id,api_key_id,claimed_at,encrypted_api_key,delivery_email)
               VALUES (?,?,?,?,?)""",
            (session_id, cursor.lastrowid, now, encrypted, email),
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


def claim_checkout_email_delivery(session_id: str, lease_seconds: int = 300) -> bool:
    """Atomically claim one email send; stale claims can be retried after a crash."""
    now = datetime.now(timezone.utc)
    now_text = now.isoformat()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT email_sent_at,email_delivery_claimed_at FROM checkout_claims WHERE checkout_session_id=?",
            (session_id,),
        ).fetchone()
        if not row or row["email_sent_at"]:
            return False
        claimed = row["email_delivery_claimed_at"]
        if claimed:
            try:
                if now - datetime.fromisoformat(claimed) < timedelta(seconds=lease_seconds):
                    return False
            except ValueError:
                pass
        conn.execute(
            "UPDATE checkout_claims SET email_delivery_claimed_at=? WHERE checkout_session_id=?",
            (now_text, session_id),
        )
        return True


def release_checkout_email_delivery(session_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE checkout_claims SET email_delivery_claimed_at=NULL WHERE checkout_session_id=? AND email_sent_at IS NULL",
            (session_id,),
        )


def mark_checkout_email_sent(session_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE checkout_claims SET email_sent_at=?,email_delivery_claimed_at=NULL WHERE checkout_session_id=?",
            (datetime.now(timezone.utc).isoformat(), session_id),
        )


def get_key_record(api_key: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """SELECT id,label,monthly_limit,active,plan,stripe_customer_id,subscription_id,
               subscription_status,past_due_since,access_hold_reason,revoked_at
               FROM api_keys WHERE key_hash=?""",
            (hash_key(api_key),)).fetchone()
    return dict(row) if row else None


def _usage_window(conn: sqlite3.Connection, key_id: int, now: datetime) -> tuple[str, str]:
    row = conn.execute(
        "SELECT current_period_start,current_period_end FROM api_keys WHERE id=?",
        (key_id,),
    ).fetchone()
    if row and row["current_period_start"] and row["current_period_end"]:
        return str(row["current_period_start"]), str(row["current_period_end"])
    # Legacy/free keys retain a calendar-month window until assigned a Stripe period.
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start.isoformat(), next_month.isoformat()


def key_usage(key_id: int, monthly_limit: int) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    with _connect() as conn:
        start, end = _usage_window(conn, key_id, now)
        row = conn.execute(
            "SELECT COUNT(*) AS used FROM api_usage WHERE api_key_id=? AND used_at>=? AND used_at<?",
            (key_id, start, end),
        ).fetchone()
    used = int(row["used"])
    return {"used": used, "monthly_limit": monthly_limit, "remaining": max(0, monthly_limit-used), "unit": "pages"}


def reserve_request_event(key_id: int, requests_per_minute: int) -> None:
    """Count every authenticated API attempt independently of billable page units."""
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(seconds=60)).isoformat()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        recent = conn.execute(
            "SELECT COUNT(*) AS n FROM api_request_events WHERE api_key_id=? AND created_at>=?",
            (key_id, cutoff),
        ).fetchone()["n"]
        if int(recent) >= requests_per_minute:
            raise UsageLimitExceeded("Per-minute API rate limit reached. Please retry shortly.", rate_limited=True)
        conn.execute(
            "INSERT INTO api_request_events(api_key_id,created_at) VALUES (?,?)",
            (key_id, now.isoformat()),
        )
        # Only the last minute matters for throttling; keep an hour, drop the rest
        # so this table does not grow forever.
        conn.execute(
            "DELETE FROM api_request_events WHERE api_key_id=? AND created_at<?",
            (key_id, (now - timedelta(hours=1)).isoformat()),
        )


def reserve_usage(
    key_id: int,
    monthly_limit: int,
    requests_per_minute: int,
    units: int = 1,
    *,
    count_request: bool = True,
) -> str:
    """Reserve billable page units atomically; returns a token that can be released on failure."""
    if units < 1:
        raise ValueError("Usage units must be at least one.")
    if count_request:
        reserve_request_event(key_id, requests_per_minute)
    now = datetime.now(timezone.utc)
    now_text = now.isoformat()
    reservation_id = uuid.uuid4().hex
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        start, end = _usage_window(conn, key_id, now)
        used = int(conn.execute(
            "SELECT COUNT(*) AS n FROM api_usage WHERE api_key_id=? AND used_at>=? AND used_at<?",
            (key_id, start, end),
        ).fetchone()["n"])
        if used + units > monthly_limit:
            raise UsageLimitExceeded("Monthly page usage limit reached.")
        conn.executemany(
            "INSERT INTO api_usage(api_key_id,used_at,reservation_id) VALUES (?,?,?)",
            [(key_id, now_text, reservation_id) for _ in range(units)],
        )
    return reservation_id


def release_usage_reservation(key_id: int, reservation_id: str) -> int:
    """Release page quota after a failed upload while retaining its request-rate event."""
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM api_usage WHERE api_key_id=? AND reservation_id=?",
            (key_id, reservation_id),
        )
        return int(cursor.rowcount)


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
        row = conn.execute("SELECT COUNT(*) AS used FROM api_request_events WHERE api_key_id=? AND created_at>=?",
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
               subscription_id,subscription_status,past_due_since,access_hold_reason,revoked_at
               FROM api_keys WHERE stripe_customer_id=? ORDER BY id DESC LIMIT 1""",
            (customer_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_customer_local_data(key_id: int) -> int:
    """Delete local application records for a customer, preserving Stripe's own records."""
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        owner = conn.execute(
            "SELECT stripe_customer_id,label FROM api_keys WHERE id=?",
            (key_id,),
        ).fetchone()
        if not owner:
            return 0
        customer_id = owner["stripe_customer_id"]
        if customer_id:
            rows = conn.execute("SELECT id FROM api_keys WHERE stripe_customer_id=?", (customer_id,)).fetchall()
            key_ids = [int(row["id"]) for row in rows]
            conn.execute("DELETE FROM api_key_recovery_codes WHERE customer_id=?", (customer_id,))
        else:
            key_ids = [key_id]
        if not key_ids:
            return 0
        placeholders = ",".join("?" for _ in key_ids)
        conn.execute(f"DELETE FROM api_usage WHERE api_key_id IN ({placeholders})", key_ids)
        conn.execute(f"DELETE FROM api_request_events WHERE api_key_id IN ({placeholders})", key_ids)
        conn.execute(f"DELETE FROM checkout_claims WHERE api_key_id IN ({placeholders})", key_ids)
        cursor = conn.execute(f"DELETE FROM api_keys WHERE id IN ({placeholders})", key_ids)
        return int(cursor.rowcount)


def suspend_customer_access(customer_id: str, reason: str) -> int:
    """Place an access hold on every key for a Stripe customer.

    The Stripe subscription status is left untouched so it stays accurate.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """UPDATE api_keys SET active=0,access_hold_reason=?,
               access_hold_set_at=COALESCE(access_hold_set_at,?)
               WHERE stripe_customer_id=?""",
            (reason, now, customer_id),
        )
        return int(cursor.rowcount)


def apply_customer_hold_event(
    event_id: str, event_created: int, event_type: str,
    customer_id: str, reason: str | None,
) -> str:
    """Atomically deduplicate a refund/dispute event and apply its hold.

    - A redelivered event (same ID) never acts twice.
    - An event created at or before an administrator's last hold review for
      this customer is recorded but cannot re-suspend the account.
    - ``reason=None`` records the event without changing access (for example
      a dispute won by the merchant: an existing hold is kept for review).
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM stripe_webhook_events WHERE event_id=?", (event_id,)).fetchone():
            return "duplicate"
        cutoff = conn.execute(
            "SELECT MAX(hold_review_cutoff) AS c FROM api_keys WHERE stripe_customer_id=?",
            (customer_id,),
        ).fetchone()["c"]
        if reason is None:
            outcome = "recorded"
        elif cutoff is not None and int(event_created) <= int(cutoff):
            outcome = "ignored_after_review"
        else:
            changed = conn.execute(
                """UPDATE api_keys SET active=0,access_hold_reason=?,
                   access_hold_set_at=COALESCE(access_hold_set_at,?)
                   WHERE stripe_customer_id=?""",
                (reason, now, customer_id),
            ).rowcount
            outcome = "hold_applied" if changed else "no_matching_customer"
        conn.execute(
            """INSERT INTO stripe_webhook_events(event_id,event_created,event_type,received_at,customer_id,outcome)
               VALUES (?,?,?,?,?,?)""",
            (event_id, int(event_created), event_type, now, customer_id, outcome),
        )
    return outcome


def place_access_hold(key_id: int, reason: str) -> int:
    """Administrator hold on a key (and every key of the same Stripe customer)."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT stripe_customer_id FROM api_keys WHERE id=?", (key_id,)).fetchone()
        if not row:
            return 0
        where, args = (("stripe_customer_id=?", (row["stripe_customer_id"],))
                       if row["stripe_customer_id"] else ("id=?", (key_id,)))
        cursor = conn.execute(
            f"""UPDATE api_keys SET active=0,access_hold_reason=?,
                access_hold_set_at=COALESCE(access_hold_set_at,?) WHERE {where}""",
            (reason, now, *args),
        )
        return int(cursor.rowcount)


def clear_access_hold(key_id: int) -> int:
    """Lift a hold after manual review (customer-wide for Stripe customers).

    Access is restored only if Stripe's subscription status still grants it
    and the key was not revoked. Stripe events created before this moment can
    no longer re-apply a refund/dispute hold.
    """
    import time
    granting = ",".join("?" for _ in ACCESS_GRANTING_STATUSES)
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT stripe_customer_id FROM api_keys WHERE id=?", (key_id,)).fetchone()
        if not row:
            return 0
        where, args = (("stripe_customer_id=?", (row["stripe_customer_id"],))
                       if row["stripe_customer_id"] else ("id=?", (key_id,)))
        cursor = conn.execute(
            f"""UPDATE api_keys SET access_hold_reason=NULL,access_hold_set_at=NULL,
                hold_review_cutoff=?,
                active=CASE WHEN revoked_at IS NULL AND subscription_status IN ({granting}) THEN 1 ELSE 0 END
                WHERE {where} AND access_hold_reason IS NOT NULL""",
            (int(time.time()), *ACCESS_GRANTING_STATUSES, *args),
        )
        return int(cursor.rowcount)


def expire_past_due_access(key_id: int) -> None:
    """End access after the payment grace period; a later paid invoice restores it."""
    with _connect() as conn:
        conn.execute("UPDATE api_keys SET active=0 WHERE id=?", (key_id,))


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
        # A newly requested code supersedes any undelivered encrypted replacement.
        conn.execute(
            "UPDATE api_key_recovery_codes SET encrypted_api_key=NULL WHERE email=? AND delivered_at IS NULL",
            (email.lower(),),
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


def prepare_recovery_key(email: str, code: str, customer_id: str, key_id: int) -> str | None:
    """Atomically rotate once and retain an encrypted, retryable delivery until email succeeds."""
    now = datetime.now(timezone.utc)
    supplied_hash = _recovery_code_hash(code)
    fernet = _api_key_fernet()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT id,customer_id,code_hash,expires_at,attempts,used_at,
                      encrypted_api_key,delivered_at
               FROM api_key_recovery_codes WHERE email=? ORDER BY id DESC LIMIT 1""",
            (email.lower(),),
        ).fetchone()
        if not row or str(row["customer_id"]) != customer_id or int(row["attempts"]) >= 5:
            return None
        if not hmac.compare_digest(row["code_hash"], supplied_hash):
            if not row["used_at"]:
                conn.execute("UPDATE api_key_recovery_codes SET attempts=attempts+1 WHERE id=?", (row["id"],))
            return None
        # A retry after a mail outage reuses the exact same key without another rotation.
        if row["used_at"]:
            if not row["encrypted_api_key"] or row["delivered_at"]:
                return None
            try:
                return fernet.decrypt(row["encrypted_api_key"].encode("ascii")).decode("utf-8")
            except (InvalidToken, ValueError) as exc:
                raise RuntimeError("The pending recovery key could not be decrypted. Check API_KEY_ENCRYPTION_KEY.") from exc
        if datetime.fromisoformat(row["expires_at"]) < now:
            conn.execute("UPDATE api_key_recovery_codes SET used_at=? WHERE id=?", (now.isoformat(), row["id"]))
            return None
        if not hmac.compare_digest(row["code_hash"], supplied_hash):
            conn.execute("UPDATE api_key_recovery_codes SET attempts=attempts+1 WHERE id=?", (row["id"],))
            return None
        raw_key = ("iia_test_" if os.getenv("STRIPE_SECRET_KEY", "").startswith("sk_test_") else "iia_live_") + secrets.token_urlsafe(32)
        encrypted = fernet.encrypt(raw_key.encode("utf-8")).decode("ascii")
        cursor = conn.execute(
            "UPDATE api_keys SET key_hash=? WHERE id=? AND active=1",
            (hash_key(raw_key), key_id),
        )
        if cursor.rowcount != 1:
            return None
        conn.execute(
            "UPDATE api_key_recovery_codes SET used_at=?,encrypted_api_key=? WHERE id=?",
            (now.isoformat(), encrypted, row["id"]),
        )
        return raw_key


def mark_recovery_email_sent(email: str, code: str) -> None:
    with _connect() as conn:
        conn.execute(
            """UPDATE api_key_recovery_codes SET delivered_at=?
               WHERE email=? AND code_hash=? AND encrypted_api_key IS NOT NULL AND delivered_at IS NULL""",
            (datetime.now(timezone.utc).isoformat(), email.lower(), _recovery_code_hash(code)),
        )


def set_subscription(key_id: int, plan: str, status: str, customer_id: str | None,
                     subscription_id: str, monthly_limit: int,
                     current_period_start: str | None = None,
                     current_period_end: str | None = None) -> None:
    active, past_due_since = _subscription_access_state(status)
    with _connect() as conn:
        conn.execute(f"""UPDATE api_keys SET plan=?,
                     active=CASE WHEN {_ACCESS_BLOCKED_SQL} THEN 0 ELSE ? END,
                     monthly_limit=?,stripe_customer_id=?,
                     subscription_id=?,subscription_status=?,
                     past_due_since=CASE WHEN ?='past_due' THEN COALESCE(past_due_since,?) ELSE NULL END,
                     current_period_start=COALESCE(?,current_period_start),
                     current_period_end=COALESCE(?,current_period_end)
                     WHERE id=?""",
                     (plan, active, monthly_limit, customer_id, subscription_id, status,
                      status, past_due_since, current_period_start, current_period_end, key_id))


def set_subscription_by_id(subscription_id: str, status: str,
                            plan: str | None = None, monthly_limit: int | None = None) -> None:
    active, past_due_since = _subscription_access_state(status)
    with _connect() as conn:
        conn.execute(f"""UPDATE api_keys SET
                     active=CASE WHEN {_ACCESS_BLOCKED_SQL} THEN 0 ELSE ? END,
                     subscription_status=?,
                     past_due_since=CASE WHEN ?='past_due' THEN COALESCE(past_due_since,?) ELSE NULL END,
                     plan=COALESCE(?,plan),monthly_limit=COALESCE(?,monthly_limit)
                     WHERE subscription_id=?""",
                     (active, status, status, past_due_since, plan, monthly_limit, subscription_id))


def apply_stripe_subscription_event(
    event_id: str, event_created: int, event_type: str, subscription_id: str,
    status: str, plan: str | None = None, customer_id: str | None = None,
    monthly_limit: int | None = None,
    current_period_start: str | None = None,
    current_period_end: str | None = None,
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
                """INSERT INTO stripe_webhook_events(event_id,event_created,event_type,received_at,customer_id,outcome)
                   VALUES (?,?,?,?,?,?)""",
                (event_id, int(event_created), event_type, now, customer_id, "stale"),
            )
            return "stale"
        # subscription_status always mirrors Stripe. Holds and revocations are
        # separate columns that no subscription event can clear.
        conn.execute(f"""UPDATE api_keys SET
                     active=CASE WHEN {_ACCESS_BLOCKED_SQL} THEN 0 ELSE ? END,
                     subscription_status=?,
                     past_due_since=CASE WHEN ?='past_due' THEN COALESCE(past_due_since,?) ELSE NULL END,
                     plan=COALESCE(?,plan),monthly_limit=COALESCE(?,monthly_limit),
                     stripe_customer_id=COALESCE(?,stripe_customer_id),
                     current_period_start=COALESCE(?,current_period_start),
                     current_period_end=COALESCE(?,current_period_end)
                     WHERE subscription_id=?""",
                     (active, status, status, past_due_since, plan, monthly_limit, customer_id,
                      current_period_start, current_period_end, subscription_id))
        conn.execute("""INSERT INTO stripe_subscription_state(subscription_id,last_event_created)
                     VALUES (?,?) ON CONFLICT(subscription_id) DO UPDATE SET
                     last_event_created=MAX(last_event_created,excluded.last_event_created)""",
                     (subscription_id, int(event_created)))
        conn.execute(
            """INSERT INTO stripe_webhook_events(event_id,event_created,event_type,received_at,customer_id,outcome)
               VALUES (?,?,?,?,?,?)""",
            (event_id, int(event_created), event_type, now, customer_id, "applied:" + status),
        )
    return "applied"


def record_stripe_event(event_id: str, event_created: int, event_type: str,
                        customer_id: str | None = None, outcome: str = "recorded") -> str:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        try:
            conn.execute(
                """INSERT INTO stripe_webhook_events(event_id,event_created,event_type,received_at,customer_id,outcome)
                   VALUES (?,?,?,?,?,?)""",
                (event_id, int(event_created), event_type, now, customer_id, outcome),
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
    """Permanently disable this key. Stripe events can never re-enable it."""
    with _connect() as conn:
        conn.execute(
            "UPDATE api_keys SET active=0,revoked_at=COALESCE(revoked_at,?) WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), key_id),
        )


def count_public_rate_limit(subject: str, action: str, window_seconds: int) -> int:
    """Read-only count used to lock out repeated failures before checking secrets."""
    import time
    subject_hash = hashlib.sha256(subject.encode("utf-8")).hexdigest()
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM public_rate_limit_events WHERE subject_hash=? AND action=? AND created_at>=?",
            (subject_hash, action, time.time() - window_seconds),
        ).fetchone()
    return int(row["n"])


def record_admin_audit(actor: str, action: str, target: str | None, detail: str | None,
                       client_hash: str, success: bool) -> None:
    """Append-only administrator audit trail. Never pass secrets or raw API keys."""
    with _connect() as conn:
        conn.execute(
            """INSERT INTO admin_audit_log(created_at,actor,action,target,detail,client_hash,success)
               VALUES (?,?,?,?,?,?,?)""",
            (datetime.now(timezone.utc).isoformat(), actor[:64], action[:64],
             (target or "")[:128] or None, (detail or "")[:1000] or None, client_hash, 1 if success else 0),
        )


def admin_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Read-only helper for the admin module (callers pass static SQL only)."""
    with _connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
