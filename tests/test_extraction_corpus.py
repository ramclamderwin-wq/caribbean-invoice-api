"""Synthetic multi-format regression corpus.

These cover layouts, languages, number formats and currencies the extractor
must keep handling. They are SYNTHETIC: passing them says nothing about
accuracy on real invoices. Real-world accuracy must come from the labelled
benchmark in benchmarks/ (target: 200+ permissioned, redacted invoices).
Expected values are what the invoice says, not what the code happened to output.
"""
from __future__ import annotations

import pytest

from app.extraction import extract_invoice_fields

CORPUS = {
    "us_dot_decimal": (
        "Acme Supplies LLC\n123 Main St\nInvoice No: INV-1001\nInvoice Date: 2026-03-15\n"
        "Subtotal: $100.00\nSales Tax: $8.25\nTotal Due: USD 108.25",
        {"supplier_name": "Acme Supplies LLC", "invoice_number": "INV-1001", "invoice_date": "2026-03-15",
         "currency": "USD", "subtotal": "100.00", "tax": "8.25", "total": "108.25"},
    ),
    "eu_comma_decimal_dmy": (
        "Müller GmbH\nRechnung\nInvoice Number: R-2026-77\nDate: 15.03.2026\n"
        "Subtotal: 1.234,50 EUR\nVAT 19%: 234,56 EUR\nTotal: EUR 1.469,06",
        {"supplier_name": "Müller GmbH", "invoice_number": "R-2026-77", "invoice_date": "2026-03-15",
         "currency": "EUR", "subtotal": "1234.50", "tax": "234.56", "total": "1469.06"},
    ),
    "uk_named_month": (
        "Thames Trading Ltd\nInvoice #: UK-55\nInvoice date: 3 March 2026\n"
        "Subtotal £200.00\nVAT £40.00\nTotal £240.00",
        {"supplier_name": "Thames Trading Ltd", "invoice_number": "UK-55", "invoice_date": "2026-03-03",
         "currency": "GBP", "subtotal": "200.00", "tax": "40.00", "total": "240.00"},
    ),
    "spanish_bzd": (
        "Distribuidora del Caribe S.A.\nFactura No: F-889\nFecha de emisión: 12 de marzo de 2026\n"
        "Subtotal: BZ$ 500.00\nIVA: BZ$ 62.50\nTotal a pagar: BZ$ 562.50",
        {"invoice_number": "F-889", "invoice_date": "2026-03-12", "currency": "BZD",
         "subtotal": "500.00", "tax": "62.50", "total": "562.50"},
    ),
    "discount_bzd": (
        "Island Tech Ltd\nInvoice No: D-12\nDate: 2026-02-01\nSubtotal: 1,000.00 BZD\n"
        "Discount: -100.00 BZD\nTax 12.5%: 112.50 BZD\nTotal: 1,012.50 BZD",
        {"currency": "BZD", "subtotal": "1000.00", "discount": "-100.00", "tax": "112.50", "total": "1012.50"},
    ),
    "line_item_table_jmd": (
        "Caribbean Foods Ltd\nINVOICE\nInvoice No. CF-2026-004\nDate: March 5, 2026\n"
        "Qty Item Price Amount\n2 Rice 10.00 20.00\n3 Beans 5.00 15.00\n"
        "Subtotal 35.00\nGST 12.5% 4.38\nTOTAL JMD 39.38",
        {"supplier_name": "Caribbean Foods Ltd", "invoice_number": "CF-2026-004", "invoice_date": "2026-03-05",
         "currency": "JMD", "subtotal": "35.00", "tax": "4.38", "total": "39.38"},
    ),
    "shipping_ttd": (
        "Port of Spain Parts\nInvoice No: P-77\nInvoice Date: 2026-01-10\nSubtotal: TTD 900.00\n"
        "Shipping: TTD 50.00\nVAT: TTD 112.50\nTotal: TTD 1,062.50",
        {"currency": "TTD", "subtotal": "900.00", "shipping": "50.00", "tax": "112.50", "total": "1062.50"},
    ),
    "total_tax_label_only": (
        "Alpha Co\nInvoice No: A-1\nDate: 2026-05-05\nSubtotal: 10.00 USD\nTotal Tax: 1.25 USD\nTotal: 11.25 USD",
        {"subtotal": "10.00", "tax": "1.25", "total": "11.25"},
    ),
}


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_corpus_fields(name):
    text, expected = CORPUS[name]
    result = extract_invoice_fields(text)
    got = {field: result["fields"][field] for field in expected}
    assert got == expected
    # Every case reconciles, so none should carry an arithmetic warning.
    assert not any("does not equal" in warning for warning in result["warnings"])
    assert result["review_required"] is True


def test_due_date_is_never_used_as_invoice_date():
    result = extract_invoice_fields("Northwind\nInvoice No: N-9\nDue Date: 2026-04-30\nTotal: USD 50.00")
    assert result["fields"]["invoice_date"] is None
    assert "invoice_date" in result["fields_needing_review"]


def test_ambiguous_numeric_date_is_not_guessed():
    result = extract_invoice_fields("Gamma Ltd\nInvoice No: G-3\nDate: 03/04/2026\nTotal: CAD 75.00")
    assert result["fields"]["invoice_date"] is None
    assert "invoice_date" in result["fields_needing_review"]


def test_bare_dollar_sign_does_not_guess_currency():
    result = extract_invoice_fields("Delta Ltd\nInvoice No: X-1\nDate: 2026-01-01\nTotal: $20.00")
    assert result["fields"]["currency"] is None
    assert "currency" in result["fields_needing_review"]


@pytest.mark.parametrize("text", [
    "Beta Services\nCredit Note\nInvoice No: CN-4\nDate: 2026-06-01\nTotal: USD 25.00",
    "Beta Services\nInvoice No: CN-5\nDate: 2026-06-01\nTotal: (25.00) USD",
])
def test_credit_notes_are_flagged(text):
    result = extract_invoice_fields(text)
    assert result["extraction_metadata"]["document_type"] == "credit_note"
    assert any("credit note" in warning for warning in result["warnings"])
    assert "total" in result["fields_needing_review"]


def test_complete_consistent_invoice_has_no_priority_review_fields():
    text, _ = CORPUS["us_dot_decimal"]
    result = extract_invoice_fields(text)
    assert result["fields_needing_review"] == []
    assert result["review_required"] is True  # still always reviewed by a person
