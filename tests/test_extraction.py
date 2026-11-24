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
    assert result["confidence_type"] == "not_available_not_calibrated"


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
    assert result["confidence_type"] == "not_available_not_calibrated"
    assert set(result["confidence"]) == set(result["fields"])
    assert all(score is None for score in result["confidence"].values())



@pytest.mark.parametrize("case", range(50))
def test_fifty_synthetic_invoice_variations(case):
    suppliers = [f"Supplier {case:02d} LLC", f"Global Trade {case:02d}", f"Northwind Parts {case:02d}"]
    number_labels = ["Invoice No", "Invoice #", "Invoice Number", "Inv #"]
    date_labels = ["Date", "Invoice Date"]
    total_labels = ["Grand Total", "Total Due", "Amount Due", "Total"]
    currencies = ["USD", "BZD", "EUR", "GBP", "CAD"]
    total = Decimal("100.00") + Decimal(case)
    tax = Decimal("8.00")
    subtotal = total - tax
    supplier = suppliers[case % len(suppliers)]
    text = (
        f"{supplier}\n"
        f"{number_labels[case % len(number_labels)]}: INV-{case:04d}\n"
        f"{date_labels[case % len(date_labels)]}: 2026-11-{(case % 28) + 1:02d}\n"
        f"Currency: {currencies[case % len(currencies)]}\n"
        f"Subtotal: {subtotal:.2f}\n"
        f"Tax: {tax:.2f}\n"
        f"{total_labels[case % len(total_labels)]}: {total:.2f}"
    )
    result = extract_invoice_fields(text)
    assert result["fields"]["supplier_name"] == supplier
    assert result["fields"]["invoice_number"] == f"INV-{case:04d}"
    assert result["fields"]["total"] == f"{total:.2f}"
    assert result["fields"]["currency"] == currencies[case % len(currencies)]
    assert not result["warnings"]



def test_gst_rate_is_not_extracted_as_tax_amount_and_bzd_symbol_is_detected():
    result = extract_invoice_fields(
        "Belize Supplier\nInvoice No: BZ-8\nInvoice Date: 2026-03-04\n"
        "Subtotal: BZ$ 400.00\nGST (12.5%): BZ$ 50.00\nGrand Total: BZ$ 450.00"
    )
    assert result["fields"]["tax"] == "50.00"
    assert result["fields"]["currency"] == "BZD"
    assert result["fields"]["total"] == "450.00"
    assert not result["warnings"]


def test_sub_total_is_not_mistaken_for_invoice_total():
    result = extract_invoice_fields(
        "Example Supplier\nInvoice No: A-55\nDate: 2026-04-03\n"
        "Sub Total: 100.00\nTax: 8.00\nTotal: 108.00"
    )
    assert result["fields"]["subtotal"] == "100.00"
    assert result["fields"]["total"] == "108.00"


def test_thousands_separator_is_not_treated_as_decimal():
    result = extract_invoice_fields("Example Supplier\nInvoice No: A-56\nDate: 2026-04-03\nTotal: 1.000")
    assert result["fields"]["total"] == "1000.00"


def test_malformed_ocr_amount_is_not_silently_truncated():
    result = extract_invoice_fields("Example Supplier\nInvoice No: A-57\nDate: 2026-04-03\nTotal: 1O5.00")
    assert result["fields"]["total"] is None
    assert any("Invoice total" in warning for warning in result["warnings"])


def test_due_date_is_not_used_as_invoice_date():
    result = extract_invoice_fields(
        "Example Supplier\nInvoice No: A-58\nDue Date: 2026-04-30\nTotal: 108.00"
    )
    assert result["fields"]["invoice_date"] is None


def test_ambiguous_numeric_date_is_not_guessed():
    result = extract_invoice_fields(
        "Example Supplier\nInvoice No: A-59\nDate: 01/02/2026\nTotal: 108.00"
    )
    assert result["fields"]["invoice_date"] is None
    assert any("ambiguous" in warning for warning in result["warnings"])


def test_spanish_invoice_labels_are_supported():
    result = extract_invoice_fields(
        "Comercial del Caribe\nFactura No: FC-100\nFecha de factura: 20 de noviembre de 2026\n"
        "Moneda: BZD\nSubtotal: 100.00\nIVA: 12.50\nTotal a pagar: 112.50"
    )
    assert result["fields"]["invoice_number"] == "FC-100"
    assert result["fields"]["invoice_date"] == "2026-11-20"
    assert result["fields"]["tax"] == "12.50"
    assert result["fields"]["total"] == "112.50"


def test_total_tax_and_tax_id_are_not_misread_as_money():
    result = extract_invoice_fields(
        "Example Supplier\nInvoice No: A-90\nDate: 2026-04-03\n"
        "Total Tax: 50.00\nTax ID: 12345\nSubtotal: 100.00\nTax: 8.00\nTotal: 108.00"
    )
    assert result["fields"]["total"] == "108.00"
    assert result["fields"]["tax"] == "8.00"


def test_trailing_punctuation_and_first_amount_are_handled():
    result = extract_invoice_fields(
        "Example Supplier\nInvoice No: A-91\nDate: 2026-04-03\n"
        "Total: 108.00, Paid: 100.00."
    )
    assert result["fields"]["total"] == "108.00"


def test_amount_attached_currency_beats_incidental_currency_note():
    result = extract_invoice_fields(
        "Example Supplier\nInvoice No: A-92\nDate: 2026-04-03\n"
        "Prices in USD\nSubtotal: BZ$ 100.00\nTax: BZ$ 8.00\nTotal: BZ$ 108.00"
    )
    assert result["fields"]["currency"] == "BZD"
