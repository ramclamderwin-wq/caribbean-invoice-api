from app.main import extract_invoice_fields


def test_extracts_basic_belize_invoice():
    text = """CARIBBEAN SUPPLIES LTD
INVOICE
Invoice No: CS-1048
Date: 2026-11-15
Currency: BZD
Subtotal: 100.00
Tax: 12.50
Grand Total: 112.50
"""
    result = extract_invoice_fields(text)
    assert result["fields"]["supplier_name"] == "CARIBBEAN SUPPLIES LTD"
    assert result["fields"]["invoice_number"] == "CS-1048"
    assert result["fields"]["invoice_date"] == "2026-11-15"
    assert result["fields"]["currency"] == "BZD"
    assert result["fields"]["subtotal"] == "100.00"
    assert result["fields"]["tax"] == "12.50"
    assert result["fields"]["total"] == "112.50"
    assert result["warnings"] == []
    assert result["review_required"] is True


def test_flags_total_mismatch():
    result = extract_invoice_fields(
        "Example Supplier\nInvoice No: A-1\nDate: 2026-01-02\n"
        "Subtotal: 100.00\nTax: 12.50\nTotal: 120.00"
    )
    assert any("does not equal" in warning for warning in result["warnings"])


def test_missing_fields_are_reported():
    result = extract_invoice_fields("A simple document with no invoice fields")
    assert result["fields"]["invoice_number"] is None
    assert result["fields"]["total"] is None
    assert result["review_required"] is True
    assert result["warnings"]
