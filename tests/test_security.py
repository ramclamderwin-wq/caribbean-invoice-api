from app.security import create_api_key, get_key_record, init_db, key_usage, record_usage


def test_api_key_is_stored_as_hash_and_usage_is_counted(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    init_db()
    raw_key, metadata = create_api_key("test customer", 2)
    record = get_key_record(raw_key)
    assert record is not None
    assert record["label"] == "test customer"
    assert record["monthly_limit"] == 2
    assert raw_key.startswith("iia_live_")
    record_usage(record["id"])
    usage = key_usage(record["id"], record["monthly_limit"])
    assert usage["used"] == 1
    assert usage["remaining"] == 1
    assert get_key_record("not-a-real-key") is None


from fastapi.testclient import TestClient
from app.main import app


def test_protected_api_and_admin_key_creation(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("API_ADMIN_KEY", "test-admin-secret")
    with TestClient(app) as client:
        denied = client.post("/v1/extract-text", json={"text": "Example invoice"})
        assert denied.status_code == 401

        created = client.post(
            "/v1/admin/api-keys",
            headers={"X-Admin-Key": "test-admin-secret"},
            json={"label": "first customer", "monthly_limit": 3},
        )
        assert created.status_code == 200
        api_key = created.json()["api_key"]

        extracted = client.post(
            "/v1/extract-text",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"text": "NORTHSTAR LLC\\nInvoice No: INV-22\\nDate: 2026-11-20\\nSubtotal: 10.00\\nTax: 1.00\\nTotal: 11.00"},
        )
        assert extracted.status_code == 200

        usage = client.get("/v1/usage", headers={"Authorization": f"Bearer {api_key}"})
        assert usage.status_code == 200
        assert usage.json()["used"] == 1
        assert usage.json()["remaining"] == 2


def test_per_minute_rate_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "rate.db"))
    monkeypatch.setenv("API_ADMIN_KEY", "test-admin-secret")
    monkeypatch.setenv("REQUESTS_PER_MINUTE", "1")
    with TestClient(app) as client:
        created = client.post(
            "/v1/admin/api-keys",
            headers={"X-Admin-Key": "test-admin-secret"},
            json={"label": "rate limited customer", "monthly_limit": 20},
        )
        api_key = created.json()["api_key"]
        headers = {"Authorization": f"Bearer {api_key}"}
        payload = {"text": "Supplier LLC\\nInvoice No: A-100\\nDate: 2026-11-20\\nTotal: 20.00"}
        assert client.post("/v1/extract-text", headers=headers, json=payload).status_code == 200
        assert client.post("/v1/extract-text", headers=headers, json=payload).status_code == 429



def test_atomic_quota_reservation_never_exceeds_limit_under_concurrency(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from app.security import UsageLimitExceeded, reserve_usage

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "concurrent.db"))
    init_db()
    raw_key, _ = create_api_key("concurrent customer", 5)
    record = get_key_record(raw_key)

    def attempt():
        try:
            reserve_usage(record["id"], 5, 100)
            return True
        except UsageLimitExceeded:
            return False

    with ThreadPoolExecutor(max_workers=20) as pool:
        outcomes = list(pool.map(lambda _: attempt(), range(40)))

    assert sum(outcomes) == 5
    assert key_usage(record["id"], 5)["used"] == 5



def test_stripe_webhook_events_are_deduplicated_and_older_events_ignored(tmp_path, monkeypatch):
    from app.security import apply_stripe_subscription_event

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "stripe-events.db"))
    init_db()
    raw_key, _ = create_api_key("stripe customer", 1000)
    record = get_key_record(raw_key)
    from app.security import set_subscription
    set_subscription(record["id"], "starter", "active", "cus_1", "sub_1", 1000)

    first = apply_stripe_subscription_event(
        "evt_new", 200, "customer.subscription.updated", "sub_1",
        "active", "business", "cus_1", 20000,
    )
    stale = apply_stripe_subscription_event(
        "evt_old", 100, "invoice.payment_failed", "sub_1",
        "past_due", "starter", "cus_1", 1000,
    )
    duplicate = apply_stripe_subscription_event(
        "evt_new", 200, "customer.subscription.updated", "sub_1",
        "active", "business", "cus_1", 20000,
    )

    updated = get_key_record(raw_key)
    assert first == "applied"
    assert stale == "stale"
    assert duplicate == "duplicate"
    assert updated["plan"] == "business"
    assert updated["monthly_limit"] == 20000
    assert updated["active"] == 1


def test_api_key_rotation_preserves_usage_and_invalidates_old_key(tmp_path, monkeypatch):
    from app.security import reserve_usage, rotate_api_key

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "rotate.db"))
    init_db()
    raw_key, _ = create_api_key("rotation customer", 10)
    old = get_key_record(raw_key)
    reserve_usage(old["id"], 10, 60)

    new_key = rotate_api_key(old["id"])
    assert get_key_record(raw_key) is None
    new = get_key_record(new_key)
    assert new is not None
    assert new["id"] == old["id"]
    assert key_usage(new["id"], new["monthly_limit"])["used"] == 1



def test_public_rate_limit_rejects_excess_requests(tmp_path, monkeypatch):
    from app.security import UsageLimitExceeded, reserve_public_rate_limit

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "public-rate.db"))
    init_db()
    reserve_public_rate_limit("203.0.113.10", "checkout", 2, 3600)
    reserve_public_rate_limit("203.0.113.10", "checkout", 2, 3600)
    with pytest.raises(UsageLimitExceeded):
        reserve_public_rate_limit("203.0.113.10", "checkout", 2, 3600)
