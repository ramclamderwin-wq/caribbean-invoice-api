import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from reportlab.pdfgen import canvas

from app.main import app
from app.security import create_api_key


def _make_pdf(text="", page_size=(612, 792), pages=1):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=page_size)
    for page_index in range(pages):
        y = page_size[1] - 50
        for line in text.splitlines():
            pdf.drawString(50, y, line)
            y -= 20
        if page_index < pages - 1:
            pdf.showPage()
    pdf.save()
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("API_ADMIN_KEY", raising=False)
    with TestClient(app) as test_client:
        yield test_client


def _auth_headers(label="api-test", monthly_limit=100):
    key, _ = create_api_key(label, monthly_limit)
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
    payload = _make_pdf("""ACME SUPPLIES LLC
Invoice No: PDF-10
Date: 2026-11-20
Currency: USD
Subtotal: 50.00
Tax: 4.00
Total: 54.00""")
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


def test_pdf_usage_is_metered_by_page_count(client):
    headers = _auth_headers("pdf-page-metering", monthly_limit=2)
    payload = _make_pdf(
        "ACME SUPPLIES\nInvoice No: PDF-20\nDate: 2026-11-20\n"
        "Currency: USD\nSubtotal: 50.00\nTax: 4.00\nTotal: 54.00",
        pages=2,
    )
    response = client.post(
        "/v1/extract-file",
        headers=headers,
        files={"file": ("two-pages.pdf", payload, "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["source"]["pages"] == 2
    usage = client.get("/v1/usage", headers=headers)
    assert usage.json()["used"] == 2


def test_pdf_page_quota_is_checked_before_processing(client):
    headers = _auth_headers("pdf-page-quota", monthly_limit=1)
    payload = _make_pdf(
        "ACME SUPPLIES\nInvoice No: PDF-21\nDate: 2026-11-20\nTotal: 54.00",
        pages=2,
    )
    response = client.post(
        "/v1/extract-file",
        headers=headers,
        files={"file": ("two-pages.pdf", payload, "application/pdf")},
    )
    assert response.status_code == 429
    usage = client.get("/v1/usage", headers=headers)
    assert usage.json()["used"] == 0


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



def test_failed_upload_attempt_is_rate_limited_but_not_billed(client):
    headers = _auth_headers("failed-upload-metering")
    response = client.post(
        "/v1/extract-file",
        headers=headers,
        files={"file": ("invoice.docx", b"not supported", "application/octet-stream")},
    )
    assert response.status_code == 415
    usage = client.get("/v1/usage", headers=headers)
    assert usage.status_code == 200
    assert usage.json()["used"] == 0
    from app.security import requests_in_last_minute, get_key_record
    key = headers["Authorization"].split(" ", 1)[1]
    assert requests_in_last_minute(get_key_record(key)["id"]) == 1


def test_oversized_pdf_page_is_rejected_before_rasterization(client, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "MAX_PDF_PAGE_PIXELS", 1_000_000)
    payload = _make_pdf("x", page_size=(1000, 1000))
    response = client.post(
        "/v1/extract-file",
        headers=_auth_headers("oversized-page"),
        files={"file": ("oversized.pdf", payload, "application/pdf")},
    )
    assert response.status_code == 413



def test_security_headers_are_present(client):
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"



def test_oversized_request_is_rejected_before_multipart_parsing(client):
    headers = _auth_headers("oversized-request")
    headers["Content-Length"] = str(16 * 1024 * 1024)
    response = client.post(
        "/v1/extract-file",
        headers=headers,
        files={"file": ("invoice.png", b"tiny", "image/png")},
    )
    assert response.status_code == 413



def test_oversized_stripe_webhook_body_is_rejected_before_reading(client):
    payload = b"x" * (1024 * 1024 + 1)
    response = client.post("/v1/billing/webhook", content=payload)
    assert response.status_code == 413
    assert response.json()["detail"] == "Request body exceeds the configured size limit."


def test_dashboard_has_content_security_policy(client):
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_health_returns_unavailable_when_database_is_unwritable(client, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "database_health_check", lambda: False)
    response = client.get("/health")
    assert response.status_code == 503


def test_ocr_timeout_is_reported_as_timeout(monkeypatch):
    import app.main as main
    from fastapi import HTTPException
    image = Image.new("RGB", (20, 20), "white")
    monkeypatch.setattr(main, "_require_tesseract", lambda: None)
    monkeypatch.setattr(main.pytesseract, "image_to_string", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Tesseract process timeout")))
    with pytest.raises(HTTPException) as exc:
        main._ocr_image(image)
    assert exc.value.status_code == 408


def test_non_timeout_ocr_runtime_error_is_not_misreported(monkeypatch):
    import app.main as main
    from fastapi import HTTPException
    image = Image.new("RGB", (20, 20), "white")
    monkeypatch.setattr(main, "_require_tesseract", lambda: None)
    monkeypatch.setattr(main.pytesseract, "image_to_string", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("image pipeline failed")))
    with pytest.raises(HTTPException) as exc:
        main._ocr_image(image)
    assert exc.value.status_code == 500


def test_legacy_past_due_key_without_timestamp_is_not_granted_indefinite_grace(client):
    from app.security import get_key_record, set_subscription, _connect
    key = _auth_headers("legacy-past-due")["Authorization"].split(" ", 1)[1]
    record = get_key_record(key)
    set_subscription(record["id"], "starter", "past_due", "cus_legacy", "sub_legacy", 100)
    with _connect() as conn:
        conn.execute("UPDATE api_keys SET past_due_since=NULL WHERE id=?", (record["id"],))
    response = client.get("/v1/usage", headers={"Authorization": f"Bearer {key}"})
    assert response.status_code == 402
    assert get_key_record(key)["active"] == 0
