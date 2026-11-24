import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import create_api_key


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("API_ADMIN_KEY", raising=False)
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_extract_text_requires_api_key(client):
    response = client.post("/v1/extract-text", json={"text": "ACME"})
    assert response.status_code == 401


def test_extract_text_returns_structured_invoice(client):
    key, _ = create_api_key("automated-test", 100)
    response = client.post(
        "/v1/extract-text",
        headers={"Authorization": f"Bearer {key}"},
        json={"text": "ACME SUPPLIES\nInvoice No: AC-10\nDate: 2026-11-20\n"
                     "Currency: USD\nSubtotal: 100.00\nTax: 8.00\nTotal: 108.00"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fields"]["supplier_name"] == "ACME SUPPLIES"
    assert body["fields"]["invoice_number"] == "AC-10"
    assert body["fields"]["total"] == "108.00"
    assert body["source"]["type"] == "text"
    assert body["review_required"] is True


def test_usage_counts_successful_extraction(client):
    key, _ = create_api_key("usage-test", 100)
    headers = {"Authorization": f"Bearer {key}"}
    response = client.post(
        "/v1/extract-text",
        headers=headers,
        json={"text": "ACME\nInvoice No: AC-11\nDate: 2026-11-20\nTotal: 10.00"},
    )
    assert response.status_code == 200
    usage = client.get("/v1/usage", headers=headers)
    assert usage.status_code == 200
    assert usage.json()["used"] == 1
