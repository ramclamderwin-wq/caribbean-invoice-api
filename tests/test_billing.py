import pytest

from app.billing import create_checkout_session
from app.security import create_api_key, get_key_record, init_db, set_subscription


def test_checkout_requires_server_side_stripe_configuration(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Stripe billing is not configured"):
        create_checkout_session({"id": 1}, "starter", "buyer@example.com")


def test_subscription_activates_api_key_and_sets_plan_quota(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "billing.db"))
    init_db()
    raw_key, _ = create_api_key("billing customer", 1000)
    record = get_key_record(raw_key)

    set_subscription(
        record["id"],
        "professional",
        "active",
        "cus_test_123",
        "sub_test_123",
        5000,
    )
    updated = get_key_record(raw_key)
    assert updated["active"] == 1
    assert updated["plan"] == "professional"
    assert updated["monthly_limit"] == 5000
    assert updated["stripe_customer_id"] == "cus_test_123"
    assert updated["subscription_id"] == "sub_test_123"


def test_past_due_subscription_disables_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "billing.db"))
    init_db()
    raw_key, _ = create_api_key("billing customer", 1000)
    record = get_key_record(raw_key)

    set_subscription(
        record["id"],
        "starter",
        "past_due",
        "cus_test_456",
        "sub_test_456",
        1000,
    )
    assert get_key_record(raw_key)["active"] == 0
