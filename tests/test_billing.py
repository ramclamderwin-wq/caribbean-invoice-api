import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.billing import create_checkout_session
from app.security import create_api_key, create_paid_customer_key, get_key_record, init_db, set_subscription


def test_checkout_requires_server_side_stripe_configuration(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Stripe billing is not configured"):
        create_checkout_session("starter", "buyer@example.com")


def test_checkout_endpoint_is_public_for_new_customers(monkeypatch):
    monkeypatch.setattr("app.main.create_checkout_session", lambda plan, email: "https://checkout.stripe.test/session")
    response = TestClient(app).post("/v1/billing/checkout", json={"plan":"starter","email":"buyer@example.com"})
    assert response.status_code == 200
    assert response.json()["checkout_url"].startswith("https://checkout.stripe.test/")


def test_paid_customer_key_is_created_once_and_linked(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "billing.db"))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    init_db()
    raw = create_paid_customer_key("cs_test_unique", "buyer@example.com", "professional", "cus_test_123", "sub_test_123", 5000)
    assert raw.startswith("iia_test_")
    record = get_key_record(raw)
    assert record["active"] == 1
    assert record["plan"] == "professional"
    assert record["monthly_limit"] == 5000
    assert record["stripe_customer_id"] == "cus_test_123"
    assert record["subscription_id"] == "sub_test_123"
    assert create_paid_customer_key("cs_test_unique", "buyer@example.com", "professional", "cus_test_123", "sub_test_123", 5000) is None


def test_subscription_updates_existing_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "billing.db"))
    init_db()
    raw, _ = create_api_key("billing customer", 1000)
    record = get_key_record(raw)
    set_subscription(record["id"], "professional", "active", "cus_test_123", "sub_test_123", 5000)
    updated = get_key_record(raw)
    assert updated["active"] == 1
    assert updated["plan"] == "professional"
    assert updated["monthly_limit"] == 5000
    assert updated["stripe_customer_id"] == "cus_test_123"
    assert updated["subscription_id"] == "sub_test_123"


def test_past_due_subscription_disables_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "billing.db"))
    init_db()
    raw, _ = create_api_key("billing customer", 1000)
    record = get_key_record(raw)
    set_subscription(record["id"], "starter", "past_due", "cus_test_456", "sub_test_456", 1000)
    assert get_key_record(raw)["active"] == 0
