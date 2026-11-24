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
