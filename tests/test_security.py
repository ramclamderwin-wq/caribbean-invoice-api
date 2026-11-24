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
