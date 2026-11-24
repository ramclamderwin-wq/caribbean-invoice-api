import io

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.security import create_api_key


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("API_ADMIN_KEY", raising=False)
    with TestClient(app) as test_client:
        yield test_client


def _auth_headers(label="api-test"):
    key, _ = create_api_key(label, 100)
    return {"Authorization": f"Bearer {key}"}


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_extract_text_requires_api_key(client):
    response = client.post("/v1/extract-text", json={"text": "ACME"})
    assert response.status_code == 401


def test_extract_text_returns_structured_invoice(client):
    response = client.post(
        "/v1/extract-text",
        headers=_auth_headers(),
        json={"text": """ACME SUPPLIES
Invoice No: AC-10
Date: 2026-11-20
Currency: USD
Subtotal: 100.00
Tax: 8.00
Total: 108.00"""},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fields"]["supplier_name"] == "ACME SUPPLIES"
    assert body["fields"]["invoice_number"] == "AC-10"
    assert body["fields"]["total"] == "108.00"
    assert body["source"]["type"] == "text"
    assert body["review_required"] is True


def test_usage_counts_successful_extraction(client):
    headers = _auth_headers("usage-test")
    response = client.post(
        "/v1/extract-text",
        headers=headers,
        json={"text": "ACME\nInvoice No: AC-11\nDate: 2026-11-20\nTotal: 10.00"},
    )
    assert response.status_code == 200
    usage = client.get("/v1/usage", headers=headers)
    assert usage.status_code == 200
    assert usage.json()["used"] == 1


def test_extract_text_based_pdf_upload(client):
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(
        fitz.Rect(50, 50, 550, 300),
        """ACME SUPPLIES LLC
Invoice No: PDF-10
Date: 2026-11-20
Currency: USD
Subtotal: 50.00
Tax: 4.00
Total: 54.00""",
    )
    payload = document.tobytes()
    document.close()
    response = client.post(
        "/v1/extract-file",
        headers=_auth_headers("pdf-test"),
        files={"file": ("invoice.pdf", payload, "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fields"]["invoice_number"] == "PDF-10"
    assert body["fields"]["total"] == "54.00"
    assert body["source"]["type"] == "pdf"
    assert body["source"]["ocr_used"] is False


def test_extract_image_upload_uses_ocr(client, monkeypatch):
    image = Image.new("RGB", (320, 160), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    monkeypatch.setattr(
        "app.main._ocr_image",
        lambda _image: """ACME IMAGE SUPPLIES
Invoice No: IMG-2
Date: 2026-11-20
Currency: USD
Subtotal: 20.00
Tax: 1.60
Total: 21.60""",
    )
    response = client.post(
        "/v1/extract-file",
        headers=_auth_headers("image-test"),
        files={"file": ("invoice.png", buffer.getvalue(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fields"]["invoice_number"] == "IMG-2"
    assert body["fields"]["total"] == "21.60"
    assert body["source"]["type"] == "image"
    assert body["source"]["ocr_used"] is True


def test_rejects_invalid_pdf_content(client):
    response = client.post(
        "/v1/extract-file",
        headers=_auth_headers("invalid-pdf-test"),
        files={"file": ("broken.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 400


def test_rejects_unsupported_file_extension(client):
    response = client.post(
        "/v1/extract-file",
        headers=_auth_headers("unsupported-test"),
        files={"file": ("invoice.docx", b"content", "application/octet-stream")},
    )
    assert response.status_code == 415



def test_failed_upload_attempt_is_metered(client):
    headers = _auth_headers("failed-upload-metering")
    response = client.post(
        "/v1/extract-file",
        headers=headers,
        files={"file": ("invoice.docx", b"not supported", "application/octet-stream")},
    )
    assert response.status_code == 415
    usage = client.get("/v1/usage", headers=headers)
    assert usage.status_code == 200
    assert usage.json()["used"] == 1


def test_oversized_pdf_page_is_rejected_before_rasterization(client, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "MAX_PDF_PAGE_PIXELS", 1_000_000)
    document = fitz.open()
    document.new_page(width=1000, height=1000)
    payload = document.tobytes()
    document.close()
    response = client.post(
        "/v1/extract-file",
        headers=_auth_headers("oversized-page"),
        files={"file": ("oversized.pdf", payload, "application/pdf")},
    )
    assert response.status_code == 413
