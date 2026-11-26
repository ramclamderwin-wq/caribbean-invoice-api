"""Beta commercial-invoice endpoints: auth, schema, line items, billing, limits."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import create_api_key, key_usage
from scripts.make_demo_invoices import make


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "ci.db"))
    monkeypatch.setenv("REQUESTS_PER_MINUTE", "1000")
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    folder = tmp_path_factory.mktemp("demo")
    make(folder)
    return folder


def _key(limit=100):
    raw, meta = create_api_key("commercial-invoice-test", limit)
    return {"Authorization": f"Bearer {raw}"}, meta["id"]


TEXT = """COMMERCIAL INVOICE
Seller: Demo Bright Tools Co., Ltd.
Buyer: Sample Imports LLC
Invoice No: CI-77  Date: 2026-04-12  Currency: USD
Incoterm: FOB Shenzhen
Description            Qty   Unit Price   Amount
Steel hammer 500g      100   4.50         450.00
Tape measure 5m        50    3.00         150.00
Subtotal: 600.00
Freight: 40.00
Insurance: 10.00
Total: 650.00
"""


def test_requires_api_key(client):
    assert client.post("/v1/commercial-invoice/extract-text", json={"text": TEXT}).status_code == 401
    assert client.post("/v1/commercial-invoice/extract-file", files={"file": ("a.pdf", b"%PDF")}).status_code == 401


def test_text_endpoint_returns_schema_and_line_items(client):
    headers, key_id = _key()
    response = client.post("/v1/commercial-invoice/extract-text", headers=headers, json={"text": TEXT})
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "commercial_invoice.v1"
    assert body["extraction_metadata"]["status"] == "beta"
    assert body["review_required"] is True
    assert body["classification"]["hs_codes_inferred"] is False
    assert (body["freight"], body["insurance"], body["total"]) == ("40.00", "10.00", "650.00")
    assert len(body["line_items"]) == 2 and body["line_items_total"] == "600.00"
    assert body["source"] == {"type": "text", "ocr_used": False}
    assert key_usage(key_id, 100)["used"] == 1


def test_file_endpoint_on_demo_pdf_and_page_billing(client, demo):
    headers, key_id = _key()
    pdf = (demo / "demo-001-en-standard.pdf").read_bytes()
    response = client.post("/v1/commercial-invoice/extract-file", headers=headers,
                           files={"file": ("demo-001-en-standard.pdf", pdf)})
    assert response.status_code == 200
    body = response.json()
    assert body["invoice_number"] == "DBT-2026-0412" and body["total"] == "3067.00"
    assert len(body["line_items"]) == 4
    assert body["source"]["pages"] == 1 and body["source"]["ocr_used"] is False
    assert key_usage(key_id, 100)["used"] == 1


def test_errors_are_flagged_not_fixed(client, demo):
    headers, _ = _key()
    pdf = (demo / "demo-004-with-errors.pdf").read_bytes()
    body = client.post("/v1/commercial-invoice/extract-file", headers=headers,
                       files={"file": ("demo-004.pdf", pdf)}).json()
    assert "line_items" in body["fields_needing_review"]
    assert any(issue["field"] == "line_items" for issue in body["issues"])


def test_rejected_upload_is_not_billed(client):
    headers, key_id = _key()
    assert client.post("/v1/commercial-invoice/extract-file", headers=headers,
                       files={"file": ("x.docx", b"hello")}).status_code == 415
    assert client.post("/v1/commercial-invoice/extract-file", headers=headers,
                       files={"file": ("bad.pdf", b"not a pdf")}).status_code == 400
    assert key_usage(key_id, 100)["used"] == 0


def test_line_item_cap(client, monkeypatch):
    monkeypatch.setenv("MAX_LINE_ITEMS", "1")
    headers, _ = _key()
    body = client.post("/v1/commercial-invoice/extract-text", headers=headers, json={"text": TEXT}).json()
    assert len(body["line_items"]) == 1 and body["line_items_truncated"] is True
    assert "line_items" in body["fields_needing_review"]


def test_existing_header_endpoint_is_unchanged(client):
    headers, _ = _key()
    body = client.post("/v1/extract-text", headers=headers, json={"text": TEXT}).json()
    assert "line_items" not in body and body["fields"]["total"] == "650.00"
