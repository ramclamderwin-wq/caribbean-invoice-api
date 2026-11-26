"""Administrator API: customer review, access holds, billing events, audit.

Security model
- Every route requires ``X-Admin-Key`` equal to ``API_ADMIN_KEY`` (at least 32
  characters; compared in constant time).
- Optional ``ADMIN_ALLOWED_IPS`` (comma-separated IPs/CIDRs): requests from any
  other address get 404, so the admin surface is invisible. Strongly
  recommended in production.
- Repeated authentication failures from one client lock that client out for an
  hour (``ADMIN_AUTH_FAILURE_LIMIT``, default 10), checked *before* the key is
  compared. All admin requests are also rate limited (``ADMIN_RATE_LIMIT``).
- Every request, successful or not, is written to ``admin_audit_log`` with the
  ``X-Admin-Actor`` name, action, target and a hashed client identifier. The
  admin key and customer API keys are never logged or returned.
- Routes are excluded from the public OpenAPI schema (/docs).
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import os
import re
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.net import client_fingerprint, client_ip
from app.security import (
    UsageLimitExceeded, admin_query, clear_access_hold, count_public_rate_limit,
    create_api_key, key_usage, place_access_hold, record_admin_audit, reserve_public_rate_limit,
)

MIN_ADMIN_KEY_LENGTH = 32
_ACTOR_RE = re.compile(r"^[A-Za-z0-9 ._@-]{2,64}$")
router = APIRouter(prefix="/v1/admin", include_in_schema=False)

# Columns safe to show administrators: never key_hash or encrypted keys.
_CUSTOMER_COLUMNS = """id,label,plan,monthly_limit,active,created_at,stripe_customer_id,
    subscription_id,subscription_status,past_due_since,current_period_start,
    current_period_end,access_hold_reason,access_hold_set_at,hold_review_cutoff,revoked_at"""


class AdminContext(BaseModel):
    actor: str
    client: str


def _allowed_networks() -> list[ipaddress._BaseNetwork]:
    raw = os.getenv("ADMIN_ALLOWED_IPS", "").strip()
    networks = []
    for item in filter(None, (part.strip() for part in raw.split(","))):
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            continue
    return networks


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def require_admin(
    request: Request,
    x_admin_key: str | None = Header(default=None),
    x_admin_actor: str | None = Header(default=None),
) -> AdminContext:
    ip = client_ip(request)
    fingerprint = client_fingerprint(request)
    action = f"{request.method} {request.url.path}"
    actor = x_admin_actor if x_admin_actor and _ACTOR_RE.match(x_admin_actor) else "unnamed"

    networks = _allowed_networks()
    if networks:
        try:
            address = ipaddress.ip_address(ip)
            allowed = any(address in net for net in networks)
        except ValueError:
            allowed = False
        if not allowed:
            record_admin_audit(actor, action, None, "blocked: address not in ADMIN_ALLOWED_IPS", fingerprint, False)
            raise HTTPException(status_code=404, detail="Not Found")

    secret = os.getenv("API_ADMIN_KEY", "")
    if len(secret) < MIN_ADMIN_KEY_LENGTH:
        raise HTTPException(status_code=503, detail="API key administration is not configured.")

    failure_limit = _int_env("ADMIN_AUTH_FAILURE_LIMIT", 10)
    if count_public_rate_limit(ip, "admin_auth_failure", 3600) >= failure_limit:
        record_admin_audit(actor, action, None, "blocked: too many failed attempts", fingerprint, False)
        raise HTTPException(status_code=429, detail="Too many failed administrator attempts. Try again later.")

    if not x_admin_key or not hmac.compare_digest(x_admin_key.encode("utf-8"), secret.encode("utf-8")):
        try:
            reserve_public_rate_limit(ip, "admin_auth_failure", failure_limit + 1, 3600)
        except UsageLimitExceeded:
            pass
        record_admin_audit(actor, action, None, "authentication failed", fingerprint, False)
        raise HTTPException(status_code=401, detail="Administrator authorization failed.")

    try:
        reserve_public_rate_limit(ip, "admin_request", _int_env("ADMIN_RATE_LIMIT", 300), 3600)
    except UsageLimitExceeded as exc:
        record_admin_audit(actor, action, None, "rate limited", fingerprint, False)
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return AdminContext(actor=actor, client=fingerprint)


def require_named_admin(ctx: AdminContext = Depends(require_admin)) -> AdminContext:
    """State-changing actions must say who performed them."""
    if ctx.actor == "unnamed":
        raise HTTPException(status_code=400, detail="Set the X-Admin-Actor header to your name for changes.")
    return ctx


def _audit(ctx: AdminContext, action: str, target: Any = None, **detail: Any) -> None:
    record_admin_audit(
        ctx.actor, action, None if target is None else str(target),
        json.dumps(detail, default=str, sort_keys=True) if detail else None, ctx.client, True,
    )


def _customer(key_id: int) -> dict[str, Any]:
    rows = admin_query(f"SELECT {_CUSTOMER_COLUMNS} FROM api_keys WHERE id=?", (key_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Customer key not found.")
    return rows[0]


# --- request models -------------------------------------------------------------

class CreateKeyRequest(BaseModel):
    label: str = Field(min_length=2, max_length=100)
    monthly_limit: int = Field(default=1000, ge=1, le=1_000_000)


class HoldRequest(BaseModel):
    note: str = Field(min_length=3, max_length=500, description="Why access is being suspended.")


class ClearHoldRequest(BaseModel):
    note: str = Field(min_length=3, max_length=500, description="Outcome of the manual review.")


# --- routes ---------------------------------------------------------------------

@router.post("/api-keys")
def admin_create_api_key(body: CreateKeyRequest, request: Request,
                         ctx: AdminContext = Depends(require_named_admin)) -> dict[str, Any]:
    try:
        reserve_public_rate_limit(client_ip(request), "admin_create_key",
                                  _int_env("ADMIN_CREATE_KEY_RATE_LIMIT", 10), 3600)
    except UsageLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    raw_key, metadata = create_api_key(body.label, body.monthly_limit)
    _audit(ctx, "create_api_key", metadata["id"], monthly_limit=body.monthly_limit)
    return {"api_key": raw_key, "warning": "Copy this key now. It cannot be retrieved later.", "customer": metadata}


@router.get("/customers")
def list_customers(
    ctx: AdminContext = Depends(require_admin),
    hold_only: bool = False,
    subscription_status: str | None = Query(default=None, max_length=32),
    search: str | None = Query(default=None, max_length=254, description="Email/label or Stripe customer ID."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    clauses, params = [], []
    if hold_only:
        clauses.append("access_hold_reason IS NOT NULL")
    if subscription_status:
        clauses.append("subscription_status=?")
        params.append(subscription_status)
    if search:
        clauses.append("(label LIKE ? OR stripe_customer_id=?)")
        params.extend([f"%{search}%", search])
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = admin_query(
        f"SELECT {_CUSTOMER_COLUMNS} FROM api_keys {where} ORDER BY id DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    )
    _audit(ctx, "list_customers", None, hold_only=hold_only, status=subscription_status, count=len(rows))
    return {"customers": rows, "limit": limit, "offset": offset}


@router.get("/customers/{key_id}")
def customer_detail(key_id: int, ctx: AdminContext = Depends(require_admin)) -> dict[str, Any]:
    customer = _customer(key_id)
    usage = key_usage(key_id, int(customer["monthly_limit"]))
    events = []
    if customer["stripe_customer_id"]:
        events = admin_query(
            """SELECT event_id,event_type,event_created,received_at,outcome FROM stripe_webhook_events
               WHERE customer_id=? ORDER BY event_created DESC LIMIT 50""",
            (customer["stripe_customer_id"],),
        )
    deliveries = admin_query(
        """SELECT checkout_session_id,claimed_at,email_sent_at,email_delivery_claimed_at
           FROM checkout_claims WHERE api_key_id=?""",
        (key_id,),
    )
    audit = admin_query(
        """SELECT created_at,actor,action,detail,success FROM admin_audit_log
           WHERE target=? ORDER BY id DESC LIMIT 50""",
        (str(key_id),),
    )
    _audit(ctx, "view_customer", key_id)
    return {"customer": customer, "usage": usage, "billing_events": events,
            "checkout_deliveries": deliveries, "admin_history": audit}


@router.post("/customers/{key_id}/hold")
def hold_customer(key_id: int, body: HoldRequest, ctx: AdminContext = Depends(require_named_admin)) -> dict[str, Any]:
    _customer(key_id)
    changed = place_access_hold(key_id, "manual_review")
    _audit(ctx, "place_hold", key_id, note=body.note, keys_affected=changed)
    return {"status": "held", "keys_affected": changed, "customer": _customer(key_id)}


@router.post("/customers/{key_id}/clear-hold")
def clear_customer_hold(key_id: int, body: ClearHoldRequest, ctx: AdminContext = Depends(require_named_admin)) -> dict[str, Any]:
    before = _customer(key_id)
    if not before["access_hold_reason"]:
        raise HTTPException(status_code=409, detail="This customer has no access hold.")
    changed = clear_access_hold(key_id)
    after = _customer(key_id)
    _audit(ctx, "clear_hold", key_id, note=body.note, previous_reason=before["access_hold_reason"],
           keys_affected=changed, access_restored=bool(after["active"]))
    return {
        "status": "hold_cleared", "keys_affected": changed, "customer": after,
        "access_restored": bool(after["active"]),
        "note": None if after["active"] else
        "Hold cleared, but the Stripe subscription does not currently grant access (or the key was revoked).",
    }


@router.get("/billing-events")
def billing_events(
    ctx: AdminContext = Depends(require_admin),
    customer_id: str | None = Query(default=None, max_length=64),
    event_type: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    clauses, params = [], []
    if customer_id:
        clauses.append("customer_id=?")
        params.append(customer_id)
    if event_type:
        clauses.append("event_type=?")
        params.append(event_type)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = admin_query(
        f"""SELECT event_id,event_type,event_created,received_at,customer_id,outcome
            FROM stripe_webhook_events {where} ORDER BY event_created DESC LIMIT ?""",
        (*params, limit),
    )
    _audit(ctx, "list_billing_events", customer_id, count=len(rows))
    return {"events": rows}


@router.get("/email-deliveries/pending")
def pending_email_deliveries(
    ctx: AdminContext = Depends(require_admin),
    older_than_minutes: int = Query(default=15, ge=0, le=60 * 24 * 30),
) -> dict[str, Any]:
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)).isoformat()
    checkout = admin_query(
        """SELECT c.checkout_session_id,c.api_key_id,c.delivery_email,c.claimed_at,
                  c.email_delivery_claimed_at
           FROM checkout_claims c WHERE c.email_sent_at IS NULL AND c.claimed_at<=?
           ORDER BY c.claimed_at""",
        (cutoff,),
    )
    recovery = admin_query(
        """SELECT id,email,customer_id,created_at,used_at FROM api_key_recovery_codes
           WHERE encrypted_api_key IS NOT NULL AND delivered_at IS NULL AND created_at<=?
           ORDER BY created_at""",
        (cutoff,),
    )
    _audit(ctx, "list_pending_emails", None, checkout=len(checkout), recovery=len(recovery))
    return {"checkout_key_emails": checkout, "recovery_key_emails": recovery,
            "hint": "Stripe retries checkout webhooks automatically; persistent entries mean email delivery is failing."}


@router.get("/audit-log")
def audit_log(
    ctx: AdminContext = Depends(require_admin),
    limit: int = Query(default=100, ge=1, le=500),
    failures_only: bool = False,
) -> dict[str, Any]:
    where = "WHERE success=0" if failures_only else ""
    rows = admin_query(
        f"""SELECT id,created_at,actor,action,target,detail,client_hash,success
            FROM admin_audit_log {where} ORDER BY id DESC LIMIT ?""",
        (limit,),
    )
    _audit(ctx, "view_audit_log", None, count=len(rows))
    return {"entries": rows}


@router.get("/backups")
def backup_status(ctx: AdminContext = Depends(require_admin), limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
    runs = admin_query(
        "SELECT created_at,success,detail FROM backup_runs ORDER BY id DESC LIMIT ?", (limit,)
    )
    for run in runs:
        try:
            run["detail"] = json.loads(run["detail"] or "{}")
        except ValueError:
            pass
    _audit(ctx, "view_backups", None, count=len(runs))
    return {
        "scheduled": os.getenv("BACKUP_ENABLED", "").lower() in {"1", "true", "yes"},
        "interval_hours": os.getenv("BACKUP_INTERVAL_HOURS", "24"),
        "offsite_configured": bool(os.getenv("BACKUP_S3_BUCKET")),
        "encryption_configured": bool(os.getenv("BACKUP_ENCRYPTION_KEY")),
        "runs": runs,
    }


@router.post("/backups/run")
def run_backup_now(ctx: AdminContext = Depends(require_named_admin)) -> dict[str, Any]:
    from app import backup
    try:
        result = backup.run_backup()
    except Exception as exc:
        backup.record_failure(exc)
        _audit(ctx, "run_backup", None, success=False, error=type(exc).__name__)
        detail = str(exc) if isinstance(exc, backup.BackupError) else "Backup failed; see server logs."
        raise HTTPException(status_code=503, detail=detail) from exc
    _audit(ctx, "run_backup", None, file=result.path.name, uploaded=bool(result.uploaded_to))
    return {"status": "ok", "backup": result.as_dict()}
