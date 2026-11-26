"""End-to-end subscription lifecycle tests through the signed-webhook handler.

A small in-memory fake stands in for Stripe: it holds the "current" subscription
objects that the handler re-fetches, and each test feeds webhook events in the
order (or disorder) Stripe might deliver them. No network calls are made.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import app.billing as billing
from app.main import app
from app.security import clear_access_hold, get_key_record, init_db, revoke_api_key

PRICES = {"starter": "price_starter_t", "professional": "price_pro_t", "business": "price_biz_t"}


class FakeStripe:
    def __init__(self):
        self.subscriptions: dict[str, dict] = {}
        self.charges: dict[str, dict] = {}
        self.sent_keys: list[tuple[str, str]] = []
        self._event_seq = 0
        self.clock = int(time.time()) - 10_000

    # --- state helpers -------------------------------------------------
    def set_subscription(self, sub_id, customer, status="active", plan="starter", **extra):
        self.subscriptions[sub_id] = {
            "id": sub_id, "customer": customer, "status": status, "metadata": {},
            "items": {"data": [{"price": {"id": PRICES[plan]}}]}, **extra,
        }

    def event(self, event_type, obj, created=None):
        self._event_seq += 1
        self.clock += 10
        return {"id": f"evt_{self._event_seq}", "type": event_type,
                "created": created if created is not None else self.clock,
                "data": {"object": obj}}

    # --- StripeClient surface used by app.billing ---------------------
    def client(self):
        def retrieve_sub(sub_id):
            if sub_id not in self.subscriptions:
                raise RuntimeError("No such subscription")
            return self.subscriptions[sub_id]
        return SimpleNamespace(
            v1=SimpleNamespace(
                subscriptions=SimpleNamespace(retrieve=retrieve_sub),
                charges=SimpleNamespace(retrieve=lambda cid: self.charges[cid]),
            ),
            construct_event=lambda payload, sig, secret: self.next_event,
        )


@pytest.fixture
def stripe_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "lifecycle.db"))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_lifecycle")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("RESEND_API_KEY", "re_test_placeholder")
    monkeypatch.setenv("FROM_EMAIL", "RAMVORA <no-reply@example.com>")
    monkeypatch.setenv("STRIPE_PRICE_STARTER", PRICES["starter"])
    monkeypatch.setenv("STRIPE_PRICE_PROFESSIONAL", PRICES["professional"])
    monkeypatch.setenv("STRIPE_PRICE_BUSINESS", PRICES["business"])
    init_db()
    fake = FakeStripe()
    monkeypatch.setattr(billing, "_configure", fake.client)
    monkeypatch.setattr(billing, "send_api_key_email", lambda email, key: fake.sent_keys.append((email, key)))
    fake.db = tmp_path / "lifecycle.db"
    return fake


def deliver(fake, monkeypatch, event):
    fake.next_event = event
    return billing.handle_webhook(b"{}", "sig")


def checkout(fake, monkeypatch, n=1, customer="cus_1", plan="starter", payment_status="paid"):
    sub_id = f"sub_{n}"
    fake.set_subscription(sub_id, customer, plan=plan)
    session = {"id": f"cs_{n}", "status": "complete", "mode": "subscription",
               "payment_status": payment_status, "metadata": {"plan": plan},
               "customer_details": {"email": f"buyer{n}@example.com"},
               "customer": customer, "subscription": sub_id}
    result = deliver(fake, monkeypatch, fake.event("checkout.session.completed", session))
    key = fake.sent_keys[-1][1] if result["outcome"] == "email_delivered" else None
    return key, sub_id, result


def sub_event(fake, monkeypatch, sub_id, event_type="customer.subscription.updated", created=None):
    return deliver(fake, monkeypatch, fake.event(event_type, dict(fake.subscriptions[sub_id]), created))


def api_status(key):
    with TestClient(app) as client:
        return client.get("/v1/usage", headers={"Authorization": f"Bearer {key}"}).status_code


# --- new subscription / payment ------------------------------------------------

def test_new_subscription_delivers_one_working_key(stripe_env, monkeypatch):
    key, _, result = checkout(stripe_env, monkeypatch)
    assert result["outcome"] == "email_delivered"
    assert len(stripe_env.sent_keys) == 1
    assert api_status(key) == 200
    assert get_key_record(key)["monthly_limit"] == 1000


def test_unpaid_checkout_gets_no_key(stripe_env, monkeypatch):
    key, _, result = checkout(stripe_env, monkeypatch, payment_status="unpaid")
    assert result["outcome"] == "payment_pending"
    assert key is None and stripe_env.sent_keys == []


def test_checkout_for_incomplete_subscription_retries_without_key(stripe_env, monkeypatch):
    stripe_env.set_subscription("sub_9", "cus_9", status="incomplete")
    session = {"id": "cs_9", "status": "complete", "mode": "subscription", "payment_status": "paid",
               "metadata": {"plan": "starter"}, "customer_details": {"email": "b@example.com"},
               "customer": "cus_9", "subscription": "sub_9"}
    with pytest.raises(RuntimeError):
        deliver(stripe_env, monkeypatch, stripe_env.event("checkout.session.completed", session))
    assert stripe_env.sent_keys == []


def test_successful_renewal_keeps_access(stripe_env, monkeypatch):
    key, sub, _ = checkout(stripe_env, monkeypatch)
    inv = {"id": "in_1", "customer": "cus_1", "subscription": sub}
    assert deliver(stripe_env, monkeypatch, stripe_env.event("invoice.paid", inv))["outcome"] == "applied"
    assert api_status(key) == 200


# --- failed payment / grace ---------------------------------------------------

def test_failed_payment_grace_then_expiry_then_recovery(stripe_env, monkeypatch):
    key, sub, _ = checkout(stripe_env, monkeypatch)
    stripe_env.subscriptions[sub]["status"] = "past_due"
    inv = {"id": "in_f", "customer": "cus_1", "subscription": sub}
    deliver(stripe_env, monkeypatch, stripe_env.event("invoice.payment_failed", inv))
    assert get_key_record(key)["subscription_status"] == "past_due"
    assert api_status(key) == 200  # within grace

    old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
    with sqlite3.connect(stripe_env.db) as conn:
        conn.execute("UPDATE api_keys SET past_due_since=?", (old,))
    assert api_status(key) == 402  # grace expired
    assert api_status(key) == 401  # access now off

    stripe_env.subscriptions[sub]["status"] = "active"
    deliver(stripe_env, monkeypatch, stripe_env.event("invoice.paid", inv))
    assert api_status(key) == 200  # payment recovery restores (not a revocation)


# --- cancellation / deletion / pause ------------------------------------------

def test_cancel_at_period_end_keeps_access_until_deleted(stripe_env, monkeypatch):
    key, sub, _ = checkout(stripe_env, monkeypatch)
    stripe_env.subscriptions[sub]["cancel_at_period_end"] = True
    sub_event(stripe_env, monkeypatch, sub)
    assert api_status(key) == 200
    stripe_env.subscriptions[sub]["status"] = "canceled"
    sub_event(stripe_env, monkeypatch, sub, "customer.subscription.deleted")
    assert get_key_record(key)["subscription_status"] == "canceled"
    assert api_status(key) == 401


def test_deleted_subscription_uses_event_when_stripe_lookup_fails(stripe_env, monkeypatch):
    key, sub, _ = checkout(stripe_env, monkeypatch)
    obj = dict(stripe_env.subscriptions.pop(sub), status="canceled")
    deliver(stripe_env, monkeypatch, stripe_env.event("customer.subscription.deleted", obj))
    assert api_status(key) == 401


@pytest.mark.parametrize("pause", [{"pause_collection": {"behavior": "void"}}, {"status": "paused"}])
def test_pause_and_resume(stripe_env, monkeypatch, pause):
    key, sub, _ = checkout(stripe_env, monkeypatch)
    stripe_env.subscriptions[sub].update(pause)
    sub_event(stripe_env, monkeypatch, sub, "customer.subscription.paused")
    assert get_key_record(key)["subscription_status"] == "paused"
    assert api_status(key) == 401
    stripe_env.subscriptions[sub].pop("pause_collection", None)
    stripe_env.subscriptions[sub]["status"] = "active"
    sub_event(stripe_env, monkeypatch, sub, "customer.subscription.resumed")
    assert api_status(key) == 200


# --- upgrade / downgrade ------------------------------------------------------

def test_upgrade_and_downgrade_follow_current_price(stripe_env, monkeypatch):
    key, sub, _ = checkout(stripe_env, monkeypatch)
    stripe_env.set_subscription(sub, "cus_1", plan="business")
    sub_event(stripe_env, monkeypatch, sub)
    assert (get_key_record(key)["plan"], get_key_record(key)["monthly_limit"]) == ("business", 20000)
    stripe_env.set_subscription(sub, "cus_1", plan="starter")
    sub_event(stripe_env, monkeypatch, sub)
    assert (get_key_record(key)["plan"], get_key_record(key)["monthly_limit"]) == ("starter", 1000)


# --- duplicates / ordering ----------------------------------------------------

def test_duplicate_and_out_of_order_subscription_events(stripe_env, monkeypatch):
    key, sub, _ = checkout(stripe_env, monkeypatch)
    stripe_env.subscriptions[sub]["status"] = "canceled"
    newer = stripe_env.event("customer.subscription.deleted", dict(stripe_env.subscriptions[sub]))
    assert deliver(stripe_env, monkeypatch, newer)["outcome"] == "applied"
    assert deliver(stripe_env, monkeypatch, newer)["outcome"] == "duplicate"
    # An older "active" snapshot arriving late must not resurrect access.
    older = stripe_env.event("customer.subscription.updated", dict(stripe_env.subscriptions[sub], status="active"),
                             created=newer["created"] - 100)
    assert deliver(stripe_env, monkeypatch, older)["outcome"] == "stale"
    assert api_status(key) == 401


def test_duplicate_checkout_event_sends_one_email(stripe_env, monkeypatch):
    stripe_env.set_subscription("sub_d", "cus_d")
    session = {"id": "cs_d", "status": "complete", "mode": "subscription", "payment_status": "paid",
               "metadata": {"plan": "starter"}, "customer_details": {"email": "d@example.com"},
               "customer": "cus_d", "subscription": "sub_d"}
    event = stripe_env.event("checkout.session.completed", session)
    deliver(stripe_env, monkeypatch, event)
    deliver(stripe_env, monkeypatch, event)
    async_event = stripe_env.event("checkout.session.async_payment_succeeded", session)
    deliver(stripe_env, monkeypatch, async_event)
    assert len(stripe_env.sent_keys) == 1


# --- refunds / disputes / holds -----------------------------------------------

def refund(fake, monkeypatch, amount_refunded, customer="cus_1", created=None):
    charge = {"id": "ch_1", "customer": customer, "amount": 1900, "amount_refunded": amount_refunded}
    return deliver(fake, monkeypatch, fake.event("charge.refunded", charge, created))


def dispute(fake, monkeypatch, event_type, status="needs_response", created=None):
    fake.charges["ch_1"] = {"id": "ch_1", "customer": "cus_1"}
    obj = {"id": "dp_1", "charge": "ch_1", "status": status}
    return deliver(fake, monkeypatch, fake.event(event_type, obj, created))


def test_full_and_partial_refund_place_holds(stripe_env, monkeypatch):
    key, _, _ = checkout(stripe_env, monkeypatch)
    assert refund(stripe_env, monkeypatch, 500)["outcome"] == "hold_applied"
    assert get_key_record(key)["access_hold_reason"] == "refund_review"
    assert api_status(key) == 403
    refund(stripe_env, monkeypatch, 1900)
    record = get_key_record(key)
    assert record["access_hold_reason"] == "refunded"
    assert record["subscription_status"] == "active"


def test_hold_survives_renewal_and_deletion_with_accurate_status(stripe_env, monkeypatch):
    key, sub, _ = checkout(stripe_env, monkeypatch)
    dispute(stripe_env, monkeypatch, "charge.dispute.created")
    deliver(stripe_env, monkeypatch, stripe_env.event("invoice.paid", {"id": "in", "subscription": sub}))
    assert api_status(key) == 403
    stripe_env.subscriptions[sub]["status"] = "canceled"
    sub_event(stripe_env, monkeypatch, sub, "customer.subscription.deleted")
    record = get_key_record(key)
    assert record["subscription_status"] == "canceled"
    assert record["access_hold_reason"] == "disputed"
    assert record["active"] == 0


def test_dispute_won_keeps_hold_and_lost_marks_it(stripe_env, monkeypatch):
    key, _, _ = checkout(stripe_env, monkeypatch)
    dispute(stripe_env, monkeypatch, "charge.dispute.created")
    assert dispute(stripe_env, monkeypatch, "charge.dispute.updated")["outcome"] == "recorded"
    assert dispute(stripe_env, monkeypatch, "charge.dispute.closed", status="won")["outcome"] == "recorded"
    assert get_key_record(key)["access_hold_reason"] == "disputed"  # never auto-lifted

    key2, _, _ = checkout(stripe_env, monkeypatch, n=2, customer="cus_2")
    stripe_env.charges["ch_2"] = {"id": "ch_2", "customer": "cus_2"}
    deliver(stripe_env, monkeypatch, stripe_env.event(
        "charge.dispute.closed", {"id": "dp_2", "charge": "ch_2", "status": "lost"}))
    assert get_key_record(key2)["access_hold_reason"] == "dispute_lost"


def test_hold_events_are_idempotent_and_respect_manual_review(stripe_env, monkeypatch):
    key, _, _ = checkout(stripe_env, monkeypatch)
    first = stripe_env.event("charge.refunded", {"id": "ch_1", "customer": "cus_1",
                                                  "amount": 1900, "amount_refunded": 1900})
    assert deliver(stripe_env, monkeypatch, first)["outcome"] == "hold_applied"
    delayed = stripe_env.event("charge.dispute.created", {"id": "dp", "charge": {"customer": "cus_1"}},
                               created=first["created"] + 1)

    assert clear_access_hold(get_key_record(key)["id"]) == 1
    assert api_status(key) == 200

    # Redelivery of the same event, or a delayed older event, cannot re-suspend.
    assert deliver(stripe_env, monkeypatch, first)["outcome"] == "duplicate"
    assert deliver(stripe_env, monkeypatch, delayed)["outcome"] == "ignored_after_review"
    assert api_status(key) == 200

    # A genuinely new dispute after the review does suspend again.
    new = stripe_env.event("charge.dispute.created", {"id": "dp2", "charge": {"customer": "cus_1"}},
                           created=int(time.time()) + 60)
    assert deliver(stripe_env, monkeypatch, new)["outcome"] == "hold_applied"
    assert api_status(key) == 403


def test_clearing_hold_does_not_grant_access_without_paid_subscription(stripe_env, monkeypatch):
    key, sub, _ = checkout(stripe_env, monkeypatch)
    refund(stripe_env, monkeypatch, 1900)
    stripe_env.subscriptions[sub]["status"] = "canceled"
    sub_event(stripe_env, monkeypatch, sub, "customer.subscription.deleted")
    clear_access_hold(get_key_record(key)["id"])
    assert get_key_record(key)["access_hold_reason"] is None
    assert api_status(key) == 401


def test_revoked_key_is_never_reactivated_by_stripe(stripe_env, monkeypatch):
    key, sub, _ = checkout(stripe_env, monkeypatch)
    revoke_api_key(get_key_record(key)["id"])
    deliver(stripe_env, monkeypatch, stripe_env.event("invoice.paid", {"id": "in", "subscription": sub}))
    sub_event(stripe_env, monkeypatch, sub)
    assert get_key_record(key)["active"] == 0
    assert api_status(key) == 401


# --- re-subscription ----------------------------------------------------------

def test_resubscribe_after_cancellation_gets_new_working_key(stripe_env, monkeypatch):
    old_key, sub, _ = checkout(stripe_env, monkeypatch)
    stripe_env.subscriptions[sub]["status"] = "canceled"
    sub_event(stripe_env, monkeypatch, sub, "customer.subscription.deleted")
    new_key, _, _ = checkout(stripe_env, monkeypatch, n=2, customer="cus_1")
    assert new_key != old_key
    assert api_status(old_key) == 401
    assert api_status(new_key) == 200


def test_resubscribe_while_held_inherits_hold(stripe_env, monkeypatch):
    checkout(stripe_env, monkeypatch)
    dispute(stripe_env, monkeypatch, "charge.dispute.created")
    new_key, _, result = checkout(stripe_env, monkeypatch, n=2, customer="cus_1")
    assert result["outcome"] == "email_delivered"
    assert get_key_record(new_key)["access_hold_reason"] == "disputed"
    assert api_status(new_key) == 403


# --- migration ----------------------------------------------------------------

def test_legacy_hold_status_is_migrated_to_hold_column(tmp_path, monkeypatch):
    db = tmp_path / "legacy.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE, monthly_limit INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free', stripe_customer_id TEXT,
            subscription_id TEXT, subscription_status TEXT NOT NULL DEFAULT 'active',
            past_due_since TEXT, current_period_start TEXT, current_period_end TEXT)""")
        conn.execute("""INSERT INTO api_keys(label,key_hash,monthly_limit,active,created_at,subscription_status)
                        VALUES ('a','h1',10,0,'2026-01-01','disputed'),('b','h2',10,1,'2026-01-01','active')""")
    monkeypatch.setenv("DATABASE_PATH", str(db))
    init_db()
    init_db()  # idempotent
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT label,access_hold_reason,active FROM api_keys ORDER BY id").fetchall()
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert rows == [("a", "disputed", 0), ("b", None, 1)]
    assert version >= 2


def test_dispute_arriving_before_checkout_still_holds_the_new_key(stripe_env, monkeypatch):
    """Regression (staging, 2026-11-26): Stripe delivered charge.dispute.created before
    checkout.session.completed, so the hold had no key to attach to and was lost."""
    assert dispute(stripe_env, monkeypatch, "charge.dispute.created")["outcome"] == "pending_hold:disputed"
    key, _, result = checkout(stripe_env, monkeypatch)
    assert result["outcome"] == "email_delivered"
    record = get_key_record(key)
    assert record["access_hold_reason"] == "disputed" and record["active"] == 0
    assert api_status(key) == 403


def test_refund_arriving_before_checkout_still_holds_the_new_key(stripe_env, monkeypatch):
    assert refund(stripe_env, monkeypatch, 1900)["outcome"] == "pending_hold:refunded"
    key, _, _ = checkout(stripe_env, monkeypatch)
    assert get_key_record(key)["access_hold_reason"] == "refunded"


def test_pending_hold_is_applied_once(stripe_env, monkeypatch):
    """After an admin clears the hold, a later re-subscription must not resurrect it."""
    dispute(stripe_env, monkeypatch, "charge.dispute.created")
    key, _, _ = checkout(stripe_env, monkeypatch)
    from app.security import clear_access_hold
    clear_access_hold(get_key_record(key)["id"])
    key2, _, _ = checkout(stripe_env, monkeypatch, n=2)
    assert get_key_record(key2)["access_hold_reason"] is None
