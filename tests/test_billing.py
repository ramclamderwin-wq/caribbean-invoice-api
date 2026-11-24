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

    assert confirmed.status_code == 200
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
