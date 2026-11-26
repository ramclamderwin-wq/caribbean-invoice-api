"""Administrator API: authentication, lockout, IP allowlist, holds, audit trail."""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import create_api_key, get_key_record, set_subscription, suspend_customer_access

ADMIN_KEY = "admin-key-for-tests-0123456789abcdefghijkl"
HEADERS = {"X-Admin-Key": ADMIN_KEY, "X-Admin-Actor": "alice"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "admin.db"))
    monkeypatch.setenv("API_ADMIN_KEY", ADMIN_KEY)
    monkeypatch.delenv("ADMIN_ALLOWED_IPS", raising=False)
    with TestClient(app) as test_client:
        test_client.db = tmp_path / "admin.db"
        yield test_client


def _held_customer():
    key, meta = create_api_key("buyer@example.com", 100)
    set_subscription(meta["id"], "starter", "active", "cus_admin", "sub_admin", 100)
    suspend_customer_access("cus_admin", "disputed")
    return key, meta["id"]


def test_admin_routes_are_hidden_from_public_docs(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert not any(path.startswith("/v1/admin") for path in paths)


def test_admin_requires_long_configured_key(client, monkeypatch):
    monkeypatch.setenv("API_ADMIN_KEY", "short")
    assert client.get("/v1/admin/customers", headers={"X-Admin-Key": "short"}).status_code == 503


def test_wrong_key_is_rejected_audited_and_locked_out(client, monkeypatch):
    monkeypatch.setenv("ADMIN_AUTH_FAILURE_LIMIT", "3")
    for _ in range(3):
        assert client.get("/v1/admin/customers", headers={"X-Admin-Key": "x" * 40}).status_code == 401
    # Locked out even with the correct key, so guessing cannot continue.
    assert client.get("/v1/admin/customers", headers=HEADERS).status_code == 429
    with sqlite3.connect(client.db) as conn:
        failures = conn.execute("SELECT COUNT(*) FROM admin_audit_log WHERE success=0").fetchone()[0]
        logged = " ".join(str(r) for r in conn.execute("SELECT * FROM admin_audit_log").fetchall())
    assert failures == 4
    assert ADMIN_KEY not in logged and "x" * 40 not in logged


def test_ip_allowlist_hides_admin_surface(client, monkeypatch):
    monkeypatch.setenv("ADMIN_ALLOWED_IPS", "203.0.113.0/24")
    blocked = client.get("/v1/admin/customers", headers={**HEADERS, "X-Forwarded-For": "198.51.100.7"})
    assert blocked.status_code == 404
    allowed = client.get("/v1/admin/customers", headers={**HEADERS, "X-Forwarded-For": "203.0.113.9"})
    assert allowed.status_code == 200


def test_forged_forwarded_for_cannot_bypass_allowlist(client, monkeypatch):
    monkeypatch.setenv("ADMIN_ALLOWED_IPS", "203.0.113.0/24")
    # Attacker prepends an allowed IP; the proxy-appended (right-most) entry is theirs.
    forged = {**HEADERS, "X-Forwarded-For": "203.0.113.9, 198.51.100.7"}
    assert client.get("/v1/admin/customers", headers=forged).status_code == 404


def test_list_and_detail_never_expose_secrets(client):
    _held_customer()
    listing = client.get("/v1/admin/customers?hold_only=true", headers=HEADERS)
    assert listing.status_code == 200
    rows = listing.json()["customers"]
    assert len(rows) == 1 and rows[0]["access_hold_reason"] == "disputed"
    detail = client.get(f"/v1/admin/customers/{rows[0]['id']}", headers=HEADERS).json()
    text = str(listing.json()) + str(detail)
    assert "key_hash" not in text and "encrypted_api_key" not in text and "iia_" not in text
    assert detail["usage"]["unit"] == "pages"


def test_hold_and_clear_hold_flow_with_audit(client):
    key, key_id = _held_customer()
    api = {"Authorization": f"Bearer {key}"}
    assert client.get("/v1/usage", headers=api).status_code == 403

    no_actor = client.post(f"/v1/admin/customers/{key_id}/clear-hold",
                           headers={"X-Admin-Key": ADMIN_KEY}, json={"note": "reviewed"})
    assert no_actor.status_code == 400

    cleared = client.post(f"/v1/admin/customers/{key_id}/clear-hold", headers=HEADERS,
                          json={"note": "dispute withdrawn by customer"})
    assert cleared.status_code == 200 and cleared.json()["access_restored"] is True
    assert client.get("/v1/usage", headers=api).status_code == 200
    assert client.post(f"/v1/admin/customers/{key_id}/clear-hold", headers=HEADERS,
                       json={"note": "again"}).status_code == 409

    held = client.post(f"/v1/admin/customers/{key_id}/hold", headers=HEADERS, json={"note": "abuse report"})
    assert held.status_code == 200
    assert get_key_record(key)["access_hold_reason"] == "manual_review"
    assert client.get("/v1/usage", headers=api).status_code == 403

    history = client.get(f"/v1/admin/customers/{key_id}", headers=HEADERS).json()["admin_history"]
    actions = [entry["action"] for entry in history]
    assert "clear_hold" in actions and "place_hold" in actions
    assert all(entry["actor"] == "alice" for entry in history if entry["action"] in {"clear_hold", "place_hold"})


def test_billing_events_pending_emails_and_audit_log(client):
    key_id = create_api_key("pending@example.com", 10)[1]["id"]
    with sqlite3.connect(client.db) as conn:
        conn.execute("""INSERT INTO stripe_webhook_events(event_id,event_created,event_type,received_at,customer_id,outcome)
                        VALUES ('evt_a',1,'charge.refunded','2026-01-01','cus_x','hold_applied')""")
        conn.execute("""INSERT INTO checkout_claims(checkout_session_id,api_key_id,claimed_at,delivery_email)
                        VALUES ('cs_pending',?,'2020-01-01T00:00:00+00:00','pending@example.com')""", (key_id,))
    events = client.get("/v1/admin/billing-events?customer_id=cus_x", headers=HEADERS).json()["events"]
    assert events[0]["outcome"] == "hold_applied"
    pending = client.get("/v1/admin/email-deliveries/pending", headers=HEADERS).json()
    assert pending["checkout_key_emails"][0]["checkout_session_id"] == "cs_pending"
    log = client.get("/v1/admin/audit-log", headers=HEADERS).json()["entries"]
    assert {"list_billing_events", "list_pending_emails"} <= {entry["action"] for entry in log}


def test_public_rate_limit_ignores_forged_forwarded_for(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "rl.db"))
    monkeypatch.setenv("RECOVERY_REQUEST_RATE_LIMIT", "2")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    with TestClient(app) as test_client:
        codes = []
        for n in range(4):
            # Each request forges a different left-most address; the proxy-added
            # right-most address is the same real client.
            headers = {"X-Forwarded-For": f"10.0.0.{n}, 198.51.100.20"}
            response = test_client.post("/v1/billing/recovery/request",
                                        json={"email": f"user{n}@example.com"}, headers=headers)
            codes.append(response.status_code)
    assert codes[2:] == [429, 429]
