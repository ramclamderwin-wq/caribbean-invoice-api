import pytest
from fastapi.testclient import TestClient

from app.billing import create_checkout_session, claim_checkout_key
from app.security import create_api_key, get_key_record, init_db, set_subscription
from app.main import app


def test_checkout_requires_server_side_stripe_configuration(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Stripe billing is not configured"):
        create_checkout_session("starter", "buyer@example.com")


def test_public_checkout_does_not_require_an_api_key(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    monkeypatch.setenv("STRIPE_PRICE_STARTER", "price_test_starter")
    monkeypatch.setenv("CHECKOUT_SUCCESS_URL", "https://example.com/dashboard")
    monkeypatch.setenv("CHECKOUT_CANCEL_URL", "https://example.com/dashboard")
    from cryptography.fernet import Fernet
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("RESEND_API_KEY", "re_test_placeholder")
    monkeypatch.setenv("FROM_EMAIL", "Invoice API <no-reply@example.com>")
    import app.billing as billing
    class FakeSession:
        url = "https://checkout.stripe.com/test-session"
    monkeypatch.setattr(billing.stripe.checkout.Session, "create", lambda **kwargs: FakeSession())
    with TestClient(app) as client:
        response = client.post("/v1/billing/checkout", json={"plan":"starter","email":"buyer@example.com"})
    assert response.status_code == 200
    assert response.json()["checkout_url"].startswith("https://checkout.stripe.com/")


def test_checkout_key_is_created_once_and_linked_to_subscription(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "claim.db"))
    init_db()
    import app.billing as billing
    monkeypatch.setenv("STRIPE_SECRET_KEY","sk_test_example")
    from cryptography.fernet import Fernet
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(billing.stripe.checkout.Session,"retrieve",lambda session_id: {
        "status":"complete","mode":"subscription","payment_status":"paid",
        "metadata":{"plan":"professional","signup_email":"buyer@example.com"},
        "customer":"cus_test_1","subscription":"sub_test_1"})
    monkeypatch.setattr(billing.stripe.Subscription,"retrieve",lambda sub_id: {"status":"active"})
    key=claim_checkout_key("cs_test_1")
    record=get_key_record(key)
    assert record["active"] == 1
    assert record["plan"] == "professional"
    assert record["monthly_limit"] == 5000
    assert record["stripe_customer_id"] == "cus_test_1"
    assert record["subscription_id"] == "sub_test_1"
    with pytest.raises(ValueError,match="already been claimed"):
        claim_checkout_key("cs_test_1")


def test_subscription_activates_api_key_and_sets_plan_quota(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "billing.db"))
    init_db()
    raw_key, _ = create_api_key("billing customer", 1000)
    record = get_key_record(raw_key)
    set_subscription(record["id"],"professional","active","cus_test_123","sub_test_123",5000)
    updated = get_key_record(raw_key)
    assert updated["active"] == 1 and updated["plan"] == "professional"
    assert updated["monthly_limit"] == 5000
    assert updated["stripe_customer_id"] == "cus_test_123"
    assert updated["subscription_id"] == "sub_test_123"


def test_past_due_subscription_enters_grace_period(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "billing.db"))
    init_db()
    raw_key, _ = create_api_key("billing customer", 1000)
    record = get_key_record(raw_key)
    set_subscription(record["id"],"starter","past_due","cus_test_456","sub_test_456",1000)
    updated = get_key_record(raw_key)
    assert updated["active"] == 1
    assert updated["subscription_status"] == "past_due"
    assert updated["past_due_since"] is not None



def test_webhook_updates_plan_from_current_stripe_price_and_deduplicates(tmp_path, monkeypatch):
    from app.billing import handle_webhook
    from app.security import get_key_record

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "webhook.db"))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STRIPE_PRICE_BUSINESS", "price_business_current")
    init_db()
    raw_key, _ = create_api_key("webhook customer", 1000)
    record = get_key_record(raw_key)
    set_subscription(record["id"], "starter", "active", "cus_test_123", "sub_webhook_1", 1000)

    event = {
        "id": "evt_plan_change_1",
        "created": 200,
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_webhook_1", "customer": "cus_test_123", "status": "active"}},
    }
    import app.billing as billing
    monkeypatch.setattr(billing.stripe.Webhook, "construct_event", lambda *args: event)
    monkeypatch.setattr(billing.stripe.Subscription, "retrieve", lambda _id: {
        "id": "sub_webhook_1",
        "customer": "cus_test_123",
        "status": "active",
        "metadata": {"plan": "starter"},
        "items": {"data": [{"price": {"id": "price_business_current"}}]},
    })

    first = handle_webhook(b"{}", "valid-signature")
    duplicate = handle_webhook(b"{}", "valid-signature")
    updated = get_key_record(raw_key)

    assert first["outcome"] == "applied"
    assert duplicate["outcome"] == "duplicate"
    assert updated["plan"] == "business"
    assert updated["monthly_limit"] == 20000


def test_failed_payment_webhook_keeps_access_during_grace_period(tmp_path, monkeypatch):
    from app.billing import handle_webhook
    from app.security import get_key_record

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "past-due.db"))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    init_db()
    raw_key, _ = create_api_key("past due customer", 1000)
    record = get_key_record(raw_key)
    set_subscription(record["id"], "starter", "active", "cus_test_456", "sub_past_due", 1000)

    event = {
        "id": "evt_payment_failed_1",
        "created": 300,
        "type": "invoice.payment_failed",
        "data": {"object": {"subscription": "sub_past_due"}},
    }
    import app.billing as billing
    monkeypatch.setattr(billing.stripe.Webhook, "construct_event", lambda *args: event)
    monkeypatch.setattr(billing.stripe.Subscription, "retrieve", lambda _id: {
        "id": "sub_past_due", "customer": "cus_test_456", "status": "past_due",
        "metadata": {"plan": "starter"}, "items": {"data": []},
    })

    result = handle_webhook(b"{}", "valid-signature")
    updated = get_key_record(raw_key)
    assert result["outcome"] == "applied"
    assert updated["active"] == 1
    assert updated["subscription_status"] == "past_due"
    assert updated["past_due_since"] is not None



def test_claim_endpoint_uses_post_and_no_store_headers(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "claim-endpoint.db"))
    import app.main as main
    monkeypatch.setattr(main, "claim_checkout_key", lambda _session_id: "iia_test_example")
    with TestClient(app) as client:
        response = client.post("/v1/billing/claim", json={"session_id": "cs_test_session_123"})
        assert response.status_code == 200
        assert response.json()["api_key"] == "iia_test_example"
        assert response.headers["cache-control"].startswith("no-store")
        assert client.get("/v1/billing/claim?session_id=cs_test_session_123").status_code == 405


def test_api_key_rotation_endpoint_returns_new_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "key-rotation-endpoint.db"))
    init_db()
    raw_key, _ = create_api_key("rotation endpoint", 10)
    with TestClient(app) as client:
        response = client.post(
            "/v1/keys/rotate",
            headers={"Authorization": f"Bearer {raw_key}"},
        )
    assert response.status_code == 200
    new_key = response.json()["api_key"]
    assert new_key != raw_key
    assert get_key_record(raw_key) is None
    assert get_key_record(new_key) is not None



def test_checkout_completed_webhook_emails_same_encrypted_key_once(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from app.billing import handle_webhook
    from app.security import checkout_key_delivery

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "checkout-webhook.db"))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("RESEND_API_KEY", "re_test_placeholder")
    monkeypatch.setenv("FROM_EMAIL", "Invoice API <no-reply@example.com>")
    init_db()

    event = {
        "id": "evt_checkout_completed_1",
        "created": 400,
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_checkout_email_1",
            "status": "complete",
            "mode": "subscription",
            "payment_status": "paid",
            "metadata": {"plan": "starter", "signup_email": "buyer@example.com"},
            "customer_details": {"email": "buyer@example.com"},
            "customer": "cus_email_1",
            "subscription": "sub_email_1",
        }},
    }
    import app.billing as billing
    delivered = []
    monkeypatch.setattr(billing.stripe.Webhook, "construct_event", lambda *args: event)
    monkeypatch.setattr(billing.stripe.Subscription, "retrieve", lambda _id: {
        "id": "sub_email_1", "customer": "cus_email_1", "status": "active",
        "metadata": {"plan": "starter"}, "items": {"data": []},
    })
    monkeypatch.setattr(billing.stripe.checkout.Session, "retrieve", lambda _id: {
        "id": "cs_checkout_email_1", "status": "complete", "mode": "subscription",
        "payment_status": "paid", "metadata": {"plan": "starter", "signup_email": "buyer@example.com"},
        "customer_details": {"email": "buyer@example.com"}, "customer": "cus_email_1",
        "subscription": "sub_email_1",
    })
    monkeypatch.setattr(billing, "send_api_key_email", lambda email, key: delivered.append((email, key)))

    first = handle_webhook(b"{}", "valid-signature")
    duplicate = handle_webhook(b"{}", "valid-signature")
    delivery = checkout_key_delivery("cs_checkout_email_1")

    assert first["outcome"] == "email_delivered"
    assert duplicate["outcome"] == "email_delivered"
    assert len(delivered) == 1
    assert delivered[0][0] == "buyer@example.com"
    assert delivered[0][1] == delivery["api_key"]
    assert delivery["email_sent_at"] is not None
    browser_key = claim_checkout_key("cs_checkout_email_1")
    assert browser_key == delivery["api_key"]
    with pytest.raises(ValueError, match="already been claimed"):
        claim_checkout_key("cs_checkout_email_1")



def test_lost_key_recovery_uses_email_code_and_rotates_key(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    import app.billing as billing

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "recovery.db"))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("RESEND_API_KEY", "re_test_placeholder")
    monkeypatch.setenv("FROM_EMAIL", "Invoice API <no-reply@example.com>")
    init_db()
    old_key, _ = create_api_key("buyer@example.com", 1000)
    record = get_key_record(old_key)
    set_subscription(record["id"], "starter", "active", "cus_recovery_1", "sub_recovery_1", 1000)

    codes = []
    delivered_keys = []
    monkeypatch.setattr(billing.stripe.Customer, "list", lambda **kwargs: {
        "data": [{"id": "cus_recovery_1"}],
    })
    monkeypatch.setattr(billing.stripe.Subscription, "retrieve", lambda _id: {"status": "active"})
    monkeypatch.setattr(billing, "send_recovery_code_email", lambda email, code: codes.append((email, code)))
    monkeypatch.setattr(billing, "send_api_key_email", lambda email, key: delivered_keys.append((email, key)))

    with TestClient(app) as client:
        requested = client.post("/v1/billing/recovery/request", json={"email": "buyer@example.com"})
        assert requested.status_code == 200
        assert "If an eligible subscription exists" in requested.json()["message"]
        assert len(codes) == 1

        confirmed = client.post(
            "/v1/billing/recovery/confirm",
            json={"email": "buyer@example.com", "code": codes[0][1]},
        )
        reused = client.post(
            "/v1/billing/recovery/confirm",
            json={"email": "buyer@example.com", "code": codes[0][1]},
        )

    assert confirmed.status_code == 200
    assert reused.status_code == 400
    assert get_key_record(old_key) is None
    assert len(delivered_keys) == 1
    assert get_key_record(delivered_keys[0][1]) is not None


def test_checkout_is_disabled_without_encrypted_key_and_email_delivery(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    monkeypatch.setenv("STRIPE_PRICE_STARTER", "price_test_starter")
    monkeypatch.setenv("CHECKOUT_SUCCESS_URL", "https://example.com/dashboard")
    monkeypatch.setenv("CHECKOUT_CANCEL_URL", "https://example.com/dashboard")
    monkeypatch.delenv("API_KEY_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("FROM_EMAIL", raising=False)
    with pytest.raises(RuntimeError, match="Secure API-key encryption and email delivery"):
        create_checkout_session("starter", "buyer@example.com")



def test_checkout_webhook_retries_email_with_same_key(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from app.billing import handle_webhook
    from app.security import checkout_key_delivery
    import app.billing as billing

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "checkout-retry.db"))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("RESEND_API_KEY", "re_test_placeholder")
    monkeypatch.setenv("FROM_EMAIL", "Invoice API <no-reply@example.com>")
    init_db()
    event = {
        "id": "evt_checkout_retry_1", "created": 500,
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_checkout_retry_1", "status": "complete", "mode": "subscription",
            "payment_status": "paid", "metadata": {"plan": "starter"},
            "customer_details": {"email": "buyer@example.com"},
            "customer": "cus_retry_1", "subscription": "sub_retry_1",
        }},
    }
    monkeypatch.setattr(billing.stripe.Webhook, "construct_event", lambda *args: event)
    monkeypatch.setattr(billing.stripe.Subscription, "retrieve", lambda _id: {
        "id": "sub_retry_1", "customer": "cus_retry_1", "status": "active",
        "metadata": {"plan": "starter"}, "items": {"data": []},
    })
    calls = []
    def fail_first_delivery(email, key):
        calls.append(key)
        if len(calls) == 1:
            raise RuntimeError("temporary email outage")
    monkeypatch.setattr(billing, "send_api_key_email", fail_first_delivery)

    with pytest.raises(RuntimeError, match="temporary email outage"):
        handle_webhook(b"{}", "valid-signature")
    success = handle_webhook(b"{}", "valid-signature")
    delivery = checkout_key_delivery("cs_checkout_retry_1")

    assert success["outcome"] == "email_delivered"
    assert len(calls) == 2
    assert calls[0] == calls[1] == delivery["api_key"]
    assert delivery["email_sent_at"] is not None


def test_subscription_plan_checks_all_items_and_rejects_multiple_configured_plans(monkeypatch):
    from app.billing import _subscription_plan

    monkeypatch.setenv("STRIPE_PRICE_STARTER", "price_starter")
    monkeypatch.setenv("STRIPE_PRICE_PROFESSIONAL", "price_professional")
    monkeypatch.setenv("STRIPE_PRICE_BUSINESS", "price_business")
    assert _subscription_plan({
        "metadata": {"plan": "starter"},
        "items": {"data": [
            {"price": {"id": "price_addon"}},
            {"price": {"id": "price_professional"}},
        ]},
    }) == "professional"
    assert _subscription_plan({
        "items": {"data": [
            {"price": {"id": "price_starter"}},
            {"price": {"id": "price_professional"}},
        ]},
    }) is None


def test_recovery_email_failure_can_retry_same_key_without_second_rotation(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    import app.billing as billing

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "recovery-retry.db"))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("RESEND_API_KEY", "re_test_placeholder")
    monkeypatch.setenv("FROM_EMAIL", "Invoice API <no-reply@example.com>")
    init_db()
    old_key, _ = create_api_key("buyer@example.com", 1000)
    record = get_key_record(old_key)
    set_subscription(record["id"], "starter", "active", "cus_recovery_retry", "sub_recovery_retry", 1000)

    codes = []
    delivered = []
    monkeypatch.setattr(billing.stripe.Customer, "list", lambda **kwargs: {
        "data": [{"id": "cus_recovery_retry"}],
    })
    monkeypatch.setattr(billing.stripe.Subscription, "retrieve", lambda _id: {"status": "active"})
    monkeypatch.setattr(billing, "send_recovery_code_email", lambda email, code: codes.append(code))

    def fail_once(email, key):
        delivered.append(key)
        if len(delivered) == 1:
            raise RuntimeError("temporary email outage")
    monkeypatch.setattr(billing, "send_api_key_email", fail_once)

    billing.request_api_key_recovery("buyer@example.com")
    code = codes[0]
    with pytest.raises(RuntimeError, match="temporary email outage"):
        billing.confirm_api_key_recovery("buyer@example.com", code)
    pending_key = delivered[0]
    assert get_key_record(old_key) is None
    assert get_key_record(pending_key) is not None

    billing.confirm_api_key_recovery("buyer@example.com", code)
    assert delivered == [pending_key, pending_key]
    with pytest.raises(ValueError, match="invalid, expired, or already used"):
        billing.confirm_api_key_recovery("buyer@example.com", "not-the-code")


def test_usage_is_counted_in_the_customer_stripe_billing_period(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.security import _connect, key_usage, reserve_usage

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "period-usage.db"))
    init_db()
    key, _ = create_api_key("period customer", 10)
    record = get_key_record(key)
    now = datetime.now(timezone.utc)
    period_start = (now - timedelta(days=1)).isoformat()
    period_end = (now + timedelta(days=29)).isoformat()
    set_subscription(
        record["id"], "starter", "active", "cus_period", "sub_period", 10,
        current_period_start=period_start, current_period_end=period_end,
    )
    with _connect() as conn:
        conn.execute(
            "INSERT INTO api_usage(api_key_id,used_at) VALUES (?,?)",
            (record["id"], (now - timedelta(days=2)).isoformat()),
        )
        conn.execute(
            "INSERT INTO api_usage(api_key_id,used_at) VALUES (?,?)",
            (record["id"], (now - timedelta(hours=1)).isoformat()),
        )
    assert key_usage(record["id"], 10)["used"] == 1
    reserve_usage(record["id"], 10, 100)
    assert key_usage(record["id"], 10)["used"] == 2


def test_refund_webhook_suspends_customer_access(tmp_path, monkeypatch):
    from app.billing import handle_webhook
    import app.billing as billing

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "refund.db"))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    init_db()
    key, _ = create_api_key("refund customer", 100)
    record = get_key_record(key)
    set_subscription(record["id"], "starter", "active", "cus_refund", "sub_refund", 100)
    event = {
        "id": "evt_refund_1", "created": 900, "type": "charge.refunded",
        "data": {"object": {"id": "ch_refund", "customer": "cus_refund",
                            "amount": 1900, "amount_refunded": 1900}},
    }
    monkeypatch.setattr(billing.stripe.Webhook, "construct_event", lambda *args: event)
    result = handle_webhook(b"{}", "valid-signature")
    assert result["outcome"] == "recorded"
    updated = get_key_record(key)
    assert updated["active"] == 0
    assert updated["subscription_status"] == "refunded"


def test_dispute_webhook_suspends_customer_access(tmp_path, monkeypatch):
    from app.billing import handle_webhook
    import app.billing as billing

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "dispute.db"))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    init_db()
    key, _ = create_api_key("dispute customer", 100)
    record = get_key_record(key)
    set_subscription(record["id"], "starter", "active", "cus_dispute", "sub_dispute", 100)
    event = {
        "id": "evt_dispute_1", "created": 901, "type": "charge.dispute.created",
        "data": {"object": {"id": "dp_test", "charge": "ch_test"}},
    }
    monkeypatch.setattr(billing.stripe.Webhook, "construct_event", lambda *args: event)
    monkeypatch.setattr(billing.stripe.Charge, "retrieve", lambda _charge: {"customer": "cus_dispute"})
    result = handle_webhook(b"{}", "valid-signature")
    assert result["outcome"] == "recorded"
    updated = get_key_record(key)
    assert updated["active"] == 0
    assert updated["subscription_status"] == "disputed"


def test_paused_subscription_collection_disables_api_key(tmp_path, monkeypatch):
    from app.billing import handle_webhook
    import app.billing as billing

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "paused-collection.db"))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    init_db()
    key, _ = create_api_key("paused customer", 100)
    record = get_key_record(key)
    set_subscription(record["id"], "starter", "active", "cus_paused", "sub_paused", 100)
    event = {
        "id": "evt_pause_collection", "created": 902,
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_paused", "customer": "cus_paused", "status": "active"}},
    }
    monkeypatch.setattr(billing.stripe.Webhook, "construct_event", lambda *args: event)
    monkeypatch.setattr(billing.stripe.Subscription, "retrieve", lambda _id: {
        "id": "sub_paused", "customer": "cus_paused", "status": "active",
        "pause_collection": {"behavior": "void"},
        "metadata": {"plan": "starter"}, "items": {"data": []},
    })
    handle_webhook(b"{}", "valid-signature")
    updated = get_key_record(key)
    assert updated["active"] == 0
    assert updated["subscription_status"] == "paused"


def test_revoked_api_key_cannot_use_billing_key_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "revoked-billing-key.db"))
    init_db()
    key, _ = create_api_key("revoked portal customer", 100)
    headers = {"Authorization": f"Bearer {key}"}
    with TestClient(app) as client:
        first = client.post("/v1/keys/revoke", headers=headers)
        second = client.post("/v1/keys/revoke", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 401


def test_account_deletion_cancels_subscription_and_removes_local_records(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "account-delete.db"))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    init_db()
    key, _ = create_api_key("delete-me@example.com", 100)
    record = get_key_record(key)
    set_subscription(record["id"], "starter", "active", "cus_delete", "sub_delete", 100)
    import app.billing as billing
    canceled = []
    monkeypatch.setattr(billing.stripe.Subscription, "list", lambda **kwargs: {
        "data": [{"id": "sub_delete", "status": "active"}],
    })
    monkeypatch.setattr(billing.stripe.Subscription, "cancel", lambda sub_id: canceled.append(sub_id))
    with TestClient(app) as client:
        response = client.delete("/v1/account", headers={"Authorization": f"Bearer {key}"})
    assert response.status_code == 200
    assert canceled == ["sub_delete"]
    assert response.json()["status"] == "deleted"
    assert get_key_record(key) is None


def test_checkout_email_delivery_claim_is_atomic_and_retryable(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from app.security import (
        provision_checkout_key, claim_checkout_email_delivery,
        release_checkout_email_delivery, mark_checkout_email_sent,
    )
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "email-lease.db"))
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    init_db()
    provision_checkout_key("cs_lease_1", "lease@example.com", "starter",
                           "cus_lease", "sub_lease", 100)
    assert claim_checkout_email_delivery("cs_lease_1") is True
    assert claim_checkout_email_delivery("cs_lease_1") is False
    release_checkout_email_delivery("cs_lease_1")
    assert claim_checkout_email_delivery("cs_lease_1") is True
    mark_checkout_email_sent("cs_lease_1")
    assert claim_checkout_email_delivery("cs_lease_1") is False
