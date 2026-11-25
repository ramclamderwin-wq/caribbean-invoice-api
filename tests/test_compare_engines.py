"""Engine comparison harness: scoring, reporting and the AI adapter (fake client, no network)."""
from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest
from reportlab.pdfgen import canvas

from scripts import compare_engines as ce

INVOICE = """Shenzhen Bright Tools Co., Ltd.
Invoice No: SBT-1
Date: 2026-04-12
Buyer: Island Hardware Ltd.
Incoterm: FOB Shenzhen
Description Qty Unit Price Amount
Cordless drill 18V 50 32.50 1,625.00
Safety goggles 120 1.10 132.00
Subtotal: USD 1,757.00
Total: USD 1,757.00"""

EXPECTED = {
    "seller_name": "Shenzhen Bright Tools Co., Ltd.", "buyer_name": "Island Hardware Ltd.",
    "invoice_number": "SBT-1", "invoice_date": "2026-04-12", "currency": "USD", "incoterm": "FOB",
    "subtotal": "1757.00", "tax": None, "total": "1757.00",
    "line_items": [
        {"description": "Cordless drill 18V", "quantity": "50", "unit_price": "32.50", "line_total": "1625.00"},
        {"description": "Safety goggles", "quantity": "120", "unit_price": "1.10", "line_total": "132.00"},
    ],
}


def _pdf(path, text):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 800
    for line in text.splitlines():
        pdf.drawString(40, y, line)
        y -= 16
    pdf.save()
    path.write_bytes(buffer.getvalue())


@pytest.fixture
def manifest(tmp_path):
    _pdf(tmp_path / "inv1.pdf", INVOICE)
    data = {"documents": [{"file": "inv1.pdf", "pages": 1, "expected": EXPECTED,
                           "correction_seconds": {"rules": 30}}]}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    return path


def _fake_client(payload, usage=(3000, 800), stop_reason="end_turn", model="claude-opus-5-5"):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            stop_reason=stop_reason, model=model,
            usage=SimpleNamespace(input_tokens=usage[0], output_tokens=usage[1]),
            content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        )
    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create))), calls


def test_rules_engine_scores_perfectly_on_clean_synthetic_invoice(manifest):
    results = ce.run(manifest, {"rules": ce.rules_engine})
    summary = results["summary"]["rules"]
    assert summary["key_fields_all_correct_rate"] == 1.0
    assert summary["line_item_recall"] == 1.0 and summary["line_item_exact_rate"] == 1.0
    assert summary["cost_usd_per_page"] == 0
    assert summary["measured_correction_seconds_per_document"] == 30
    assert summary["sample_status"].startswith("insufficient sample")


def test_claude_adapter_request_shape_cost_and_scoring(manifest):
    payload = {
        "seller": {"name": "Shenzhen Bright Tools Co., Ltd.", "address": None, "tax_id": None},
        "buyer": {"name": "Island Hardware Ltd.", "address": None, "tax_id": None},
        "invoice_number": "SBT-1", "invoice_date": "2026-04-12", "currency": "USD", "incoterm": "FOB",
        "incoterm_place": "Shenzhen", "country_of_origin": None, "subtotal": "1757.00", "discount": None,
        "freight": None, "insurance": None, "tax": None, "total": "1757.00", "unreadable_or_uncertain": [],
        "line_items": [
            {"description": "Cordless drill 18V", "sku": None, "hs_code_as_printed": None, "quantity": "50",
             "unit_of_measure": None, "unit_price": "32.50", "line_total": "1625.00", "currency": "USD",
             "country_of_origin": None},
            {"description": "Safety goggles", "sku": None, "hs_code_as_printed": None, "quantity": "100",
             "unit_of_measure": None, "unit_price": "1.10", "line_total": "132.00", "currency": "USD",
             "country_of_origin": None},
        ],
    }
    client, calls = _fake_client(payload)
    results = ce.run(manifest, {"claude": ce.ClaudeEngine(client=client)})
    request = calls[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["output_config"]["format"]["schema"] is ce.AI_SCHEMA
    assert request["messages"][0]["content"][0]["type"] == "document"
    summary = results["summary"]["claude"]
    assert summary["cost_usd_per_page"] == pytest.approx(3000 / 1e6 * 4 + 800 / 1e6 * 20)
    assert summary["line_field_accuracy"]["quantity"] == 0.5  # one wrong quantity is caught
    assert summary["key_fields_all_correct_rate"] == 1.0


def test_refusal_and_bad_json_are_errors_not_scores(manifest):
    client, _ = _fake_client({}, stop_reason="refusal")
    summary = ce.run(manifest, {"claude": ce.ClaudeEngine(client=client)})["summary"]["claude"]
    assert summary["errors"] == 1 and summary["key_fields_all_correct_rate"] == 0.0


def test_line_matching_handles_reordering_and_missing_rows():
    expected = [{"description": "Red widget"}, {"description": "Blue gadget"}, {"description": "Green thing"}]
    predicted = [{"description": "Blue gadget"}, {"description": "red widget."}]
    assert ce.match_lines(expected, predicted) == [(0, 1), (1, 0)]


def test_cli_requires_explicit_permission_for_ai_engine(manifest):
    with pytest.raises(SystemExit):
        ce.main(["--manifest", str(manifest), "--engines", "claude"])


def test_markdown_report_flags_small_samples(manifest, tmp_path):
    out, report = tmp_path / "r.json", tmp_path / "r.md"
    assert ce.main(["--manifest", str(manifest), "--engines", "rules", "--output", str(out), "--report", str(report)]) == 0
    text = report.read_text()
    assert "insufficient sample" in text and "Line-item recall" in text
