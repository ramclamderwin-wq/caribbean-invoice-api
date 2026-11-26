"""Abuse and robustness: malformed files, body limits, throttles, error hygiene."""
from __future__ import annotations

import io
import random
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from reportlab.pdfgen import canvas

from app.main import app
from app.security import create_api_key, key_usage


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "hardening.db"))
    monkeypatch.setenv("REQUESTS_PER_MINUTE", "1000")
    with TestClient(app, raise_server_exceptions=False) as test_client:
        test_client.db = tmp_path / "hardening.db"
        yield test_client


def _key(limit=1000):
    key, meta = create_api_key("hardening", limit)
    return {"Authorization": f"Bearer {key}"}, meta["id"]


def _valid_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(50, 750, "Invoice No: H-1  Total: 10.00")
    pdf.save()
    return buffer.getvalue()


def _malformed_inputs():
    rng = random.Random(1234)
    valid = _valid_pdf()
    cases = [
        ("empty.pdf", b""),
        ("header-only.pdf", b"%PDF-1.7\n"),
        ("truncated.pdf", valid[: len(valid) // 2]),
        ("no-xref.pdf", valid.replace(b"xref", b"xxxx")),
        ("garbage-header.pdf", b"%PDF-1.4\n" + bytes(rng.getrandbits(8) for _ in range(4000))),
        ("pdf-named-png.png", valid),
        ("text-named-jpg.jpg", b"Invoice 123 total 50"),
        ("truncated.png", _png()[:40]),
    ]
    for n in range(20):  # random byte flips inside an otherwise valid PDF
        data = bytearray(valid)
        for _ in range(8):
            data[rng.randrange(10, len(data))] = rng.getrandbits(8)
        cases.append((f"fuzz-{n}.pdf", bytes(data)))
    return cases


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_malformed_uploads_never_crash_or_bill(client):
    headers, key_id = _key()
    billed_pages = 0
    for name, data in _malformed_inputs():
        response = client.post("/v1/extract-file", headers=headers, files={"file": (name, data)})
        assert response.status_code < 500, (name, response.status_code, response.text[:200])
        assert "Traceback" not in response.text and "/app/" not in response.text
        if response.status_code == 200:
            billed_pages += response.json()["source"]["pages"]
    # Exactly the successfully extracted pages are billed; every failure is released.
    assert key_usage(key_id, 1000)["used"] == billed_pages


def test_decompression_bomb_image_is_rejected(client, monkeypatch):
    headers, key_id = _key()
    buffer = io.BytesIO()
    Image.new("1", (12000, 12000)).save(buffer, format="PNG")  # tiny file, 144M pixels
    response = client.post("/v1/extract-file", headers=headers, files={"file": ("bomb.png", buffer.getvalue())})
    assert response.status_code in {400, 413}
    assert key_usage(key_id, 1000)["used"] == 0


def test_json_endpoints_reject_oversized_bodies(client, monkeypatch):
    headers, _ = _key()
    big = "x" * (1024 * 1024 + 10)
    response = client.post("/v1/extract-text", headers={**headers, "content-type": "application/json"},
                           content='{"text": "' + big + '"}')
    assert response.status_code == 413
    monkeypatch.setattr("app.main.MAX_JSON_BODY_BYTES", 2048)
    response = client.post("/v1/billing/checkout", json={"plan": "starter", "email": "a@b.co", "pad": "y" * 5000})
    assert response.status_code == 413


def test_invalid_api_key_guessing_is_throttled(client, monkeypatch):
    monkeypatch.setenv("INVALID_KEY_RATE_LIMIT", "5")
    codes = [client.get("/v1/usage", headers={"Authorization": f"Bearer iia_live_guess{n}"}).status_code
             for n in range(7)]
    assert codes[:5] == [401] * 5 and codes[5:] == [429, 429]
    # Another client (different proxy-appended IP) is unaffected.
    other = client.get("/v1/usage", headers={"Authorization": "Bearer nope", "X-Forwarded-For": "198.51.100.9"})
    assert other.status_code == 401


def test_request_event_log_is_pruned(client):
    headers, key_id = _key()
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    with sqlite3.connect(client.db) as conn:
        conn.executemany("INSERT INTO api_request_events(api_key_id,created_at) VALUES (?,?)",
                         [(key_id, old)] * 500)
    client.post("/v1/extract-text", headers=headers, json={"text": "Invoice No: P-1 Total: 1.00"})
    with sqlite3.connect(client.db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM api_request_events").fetchone()[0] == 1


def test_public_errors_do_not_reveal_configuration(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.delenv("API_KEY_ENCRYPTION_KEY", raising=False)
    response = client.post("/v1/billing/checkout", json={"plan": "starter", "email": "a@b.co"})
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "ENCRYPTION" not in detail and "RESEND" not in detail and "Stripe price" not in detail


def test_customer_emails_use_product_brand(monkeypatch):
    import json
    import app.email_delivery as email
    sent = {}

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(request, timeout):
        sent.update(json.loads(request.data))
        return Response()

    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("FROM_EMAIL", "RAMVORA <no-reply@example.com>")
    monkeypatch.setattr(email, "urlopen", fake_urlopen)
    email.send_api_key_email("buyer@example.com", "iia_test_abc")
    assert "RAMVORA" in sent["subject"] and "RAMVORA Invoice Intelligence API" in sent["text"]
    assert "RAMVORA" in sent["html"] and "Built for what" in sent["html"] and "<img" not in sent["html"]
