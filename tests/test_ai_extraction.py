"""AI engine: disabled by default, permission-gated, validated like the rule engine (fake client only)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.ai_extraction import AIEngineDisabled, ClaudeExtractionEngine, ai_enabled
from app.commercial_invoice import extract_commercial_invoice, validate_commercial_invoice

PAYLOAD = {
    "seller": {"name": "Shenzhen Bright Tools Co., Ltd.", "address": None, "tax_id": None},
    "buyer": {"name": "Island Hardware Ltd.", "address": None, "tax_id": None},
    "invoice_number": "SBT-1", "invoice_date": "2026-04-12", "currency": "USD", "incoterm": "FOB",
    "incoterm_place": "Shenzhen", "country_of_origin": "China", "subtotal": "1757.00", "discount": None,
    "freight": None, "insurance": None, "tax": None, "total": "1757.00",
    "line_items": [
        {"description": "Cordless drill 18V", "sku": "TB-100", "hs_code_as_printed": None, "quantity": "50",
         "unit_of_measure": "pcs", "unit_price": "32.50", "line_total": "1625.00", "currency": "USD", "country_of_origin": None},
        {"description": "Safety goggles", "sku": None, "hs_code_as_printed": None, "quantity": "120",
         "unit_of_measure": "pcs", "unit_price": "1.10", "line_total": "132.00", "currency": "USD", "country_of_origin": None},
    ],
    "unreadable_or_uncertain": ["line_items[2].quantity"],
}


def fake_client(payload=PAYLOAD, stop_reason="end_turn"):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stop_reason=stop_reason, model="claude-opus-5-5",
                               usage=SimpleNamespace(input_tokens=3000, output_tokens=900),
                               content=[SimpleNamespace(type="text", text=json.dumps(payload))])
    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create))), calls


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("QUILLVORA_AI_ENABLED", raising=False)
    assert ai_enabled() is False
    with pytest.raises(AIEngineDisabled, match="disabled"):
        ClaudeExtractionEngine().extract(b"%PDF-1.4", ".pdf", data_sharing_confirmed=True)


def test_requires_document_owner_permission_even_when_enabled(monkeypatch):
    monkeypatch.setenv("QUILLVORA_AI_ENABLED", "true")
    client, calls = fake_client()
    with pytest.raises(AIEngineDisabled, match="permission"):
        ClaudeExtractionEngine(client=client).extract(b"%PDF-1.4", ".pdf", data_sharing_confirmed=False)
    assert calls == []  # nothing was sent


def test_output_is_validated_and_uncertain_fields_flagged():
    client, calls = fake_client()
    out = ClaudeExtractionEngine(client=client).extract(b"%PDF-1.4", ".pdf", data_sharing_confirmed=True)
    assert out.error is None
    assert calls[0]["output_config"]["format"]["type"] == "json_schema"
    assert calls[0]["messages"][0]["content"][0]["type"] == "document"
    result = out.result
    assert result["schema_version"] == "commercial_invoice.v1"
    assert result["line_items"][1]["fields_needing_review"] == ["quantity"]
    assert "line_items" in result["fields_needing_review"]
    assert result["classification"]["hs_codes_inferred"] is False
    assert result["extraction_metadata"]["engine"] == "ai"
    assert out.cost_usd == pytest.approx(3000 / 1e6 * 4 + 900 / 1e6 * 20)


def test_refusal_and_unsupported_files_are_errors():
    client, _ = fake_client(stop_reason="refusal")
    assert ClaudeExtractionEngine(client=client).extract(b"x", ".pdf", data_sharing_confirmed=True).error == "refused"
    assert "unsupported" in ClaudeExtractionEngine(client=client).extract(b"x", ".docx", data_sharing_confirmed=True).error


def test_shared_validation_flags_arithmetic_and_missing_fields():
    doc = validate_commercial_invoice({
        "seller": None, "buyer": {"name": "B"}, "invoice_number": None, "invoice_date": "2026-01-01",
        "currency": "EUR", "subtotal": "40.00", "total": "-40.00",
        "line_items": [{"description": "Widget", "quantity": "10", "unit_price": "2.50", "line_total": "30.00"}],
    })
    assert {"seller", "invoice_number", "line_items", "subtotal"} <= set(doc["fields_needing_review"])
    assert doc["line_items"][0]["fields_needing_review"] == ["line_total", "quantity", "unit_price"]
    assert doc["document_type"] == "credit_note" and doc["review_required"] is True


def test_shared_validation_agrees_with_rule_engine_on_clean_invoice():
    text = ("Acme Exports\nInvoice No: A-1\nDate: 2026-05-01\nBuyer: Imports Co\n"
            "Description Qty Unit Price Amount\nWidget 10 2.50 25.00\nSubtotal: USD 25.00\nTotal: USD 25.00")
    rules = extract_commercial_invoice(text)
    assert rules["fields_needing_review"] == []
    assert validate_commercial_invoice(rules)["fields_needing_review"] == []
