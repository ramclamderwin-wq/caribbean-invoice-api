from decimal import Decimal

import pytest

from app.extraction import extract_invoice_fields


def test_extracts_standard_us_invoice():
    text = """NORTHSTAR SUPPLIES LLC
INVOICE
Invoice No: CS-1048
Invoice Date: 2026-11-15
Currency: USD
Subtotal: $1,000.00
Tax: $80.00
Grand Total: $1,080.00
"""
    result = extract_invoice_fields(text)
    assert result["fields"] == {
        "supplier_name": "NORTHSTAR SUPPLIES LLC",
        "invoice_number": "CS-1048",
        "invoice_date": "2026-11-15",
        "currency": "USD",
        "subtotal": "1000.00",
        "tax": "80.00",
        "total": "1080.00",
    }
    assert not result["warnings"]
    assert result["review_required"] is True
    assert result["confidence_type"] == "heuristic_presence_indicator_not_probability"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ACME LTD\nInvoice #: A-22\nDate: 11/20/2026\nTotal Due: $2,450.75", "2450.75"),
        ("ACME LTD\nInvoice No. INV/2026-9\nDate: 20 Nov 2026\nTotal: EUR 1.234,56", "1234.56"),
        ("ACME LTD\nInvoice No: X-3\nDate: 2026-11-20\nTotal: (125.50)", "-125.50"),
        ("ACME LTD\nInvoice No: X-4\nDate: 2026/11/20\nTotal: 1,250", "1250.00"),
    ],
)
def test_amount_formats_and_date_formats(text, expected):
    result = extract_invoice_fields(text)
    assert result["fields"]["total"] == expected
    assert result["fields"]["invoice_date"] is not None


def test_belize_currency_symbol_is_normalised():
    result = extract_invoice_fields(
        "Belize Trading\nInvoice No: BZ-7\nDate: 2026-10-01\n"
        "Currency: BZD\nSubtotal: BZ$100.00\nGST: BZ$12.50\nTotal: BZ$112.50"
    )
    assert result["fields"]["currency"] == "BZD"
    assert result["fields"]["subtotal"] == "100.00"
    assert result["fields"]["tax"] == "12.50"
    assert result["fields"]["total"] == "112.50"
    assert not result["warnings"]


def test_flags_arithmetic_mismatch_but_does_not_auto_approve():
    result = extract_invoice_fields(
        "Example Supplier\nInvoice No: A-1\nDate: 2026-01-02\n"
        "Subtotal: 100.00\nTax: 12.50\nTotal: 120.00"
    )
    assert any("does not equal" in warning for warning in result["warnings"])
    assert result["review_required"] is True


def test_missing_fields_are_reported_and_not_fabricated():
    result = extract_invoice_fields("A simple document with no invoice fields")
    assert all(value is None for value in result["fields"].values())
    assert result["review_required"] is True
    assert len(result["warnings"]) >= 4


def test_discount_or_shipping_difference_is_flagged_for_human_review():
    result = extract_invoice_fields(
        "ACME\nInvoice No: A-3\nDate: 2026-02-02\n"
        "Subtotal: 100.00\nTax: 8.00\nShipping: 5.00\nDiscount: 3.00\nTotal: 110.00"
    )
    assert any("check discounts, shipping" in warning for warning in result["warnings"])


def test_confidence_is_not_presented_as_probability():
    result = extract_invoice_fields(
        "ACME LTD\nInvoice No: A-4\nDate: 2026-02-02\nTotal: 20.00"
    )
    assert result["confidence_type"] == "heuristic_presence_indicator_not_probability"
    assert set(result["confidence"]) == set(result["fields"])
    assert all(0 <= score <= 1 for score in result["confidence"].values())
