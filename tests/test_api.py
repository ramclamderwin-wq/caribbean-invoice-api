import io\n\nimport fitz\nimport pytest\nfrom fastapi.testclient import TestClient\nfrom PIL import Image

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



def _create_key():
    key, _ = create_api_key("file-test", 100)
    return {"Authorization": f"Bearer {key}"}


def test_extract_text_based_pdf_upload(client):
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "ACME SUPPLIES LLC\\nInvoice No: PDF-10\\nDate: 2026-11-20\\n"
        "Currency: USD\\nSubtotal: 50.00\\nTax: 4.00\\nTotal: 54.00",
    )
    payload = document.tobytes()
    document.close()
    response = client.post(
        "/v1/extract-file",
        headers=_create_key(),
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
        lambda _image: "ACME IMAGE SUPPLIES\\nInvoice No: IMG-2\\nDate: 2026-11-20\\n"
                       "Currency: USD\\nSubtotal: 20.00\\nTax: 1.60\\nTotal: 21.60",
    )
    response = client.post(
        "/v1/extract-file",
        headers=_create_key(),
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
        headers=_create_key(),
        files={"file": ("broken.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 400


def test_rejects_unsupported_file_extension(client):
    response = client.post(
        "/v1/extract-file",
        headers=_create_key(),
        files={"file": ("invoice.docx", b"content", "application/octet-stream")},
    )
    assert response.status_code == 415
