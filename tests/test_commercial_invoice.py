"""Commercial-invoice prototype: line items, parties, trade terms, no invented values."""
from __future__ import annotations

import io

from reportlab.pdfgen import canvas

from app.commercial_invoice import SCHEMA_VERSION, extract_commercial_invoice, extract_line_items

STANDARD = """Shenzhen Bright Tools Co., Ltd.
COMMERCIAL INVOICE
Invoice No: SBT-2026-0412
Date: 2026-04-12
Seller: Shenzhen Bright Tools Co., Ltd.
No. 8 Industrial Rd, Shenzhen, China
Buyer: Island Hardware Ltd.
12 Albert St, Belize City, Belize
Incoterm: FOB Shenzhen
Country of Origin: China
Item Code Description HS Code Origin Qty Unit Price Amount
TB-100 Cordless drill 18V 8467.21 CN 50 pcs 32.50 1,625.00
TB-220 Drill bit set 10pc 8207.50 CN 200 sets 4.25 850.00
TB-310 Safety goggles 9004.90 CN 120 pcs 1.10 132.00
Subtotal: USD 2,607.00
Freight: USD 180.00
Insurance: USD 25.00
Total: USD 2,812.00"""


def test_standard_commercial_invoice():
    result = extract_commercial_invoice(STANDARD)
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["seller"]["name"] == "Shenzhen Bright Tools Co., Ltd."
    assert result["buyer"] == {"name": "Island Hardware Ltd.", "address": "12 Albert St, Belize City, Belize", "tax_id": None}
    assert (result["invoice_number"], result["invoice_date"], result["currency"]) == ("SBT-2026-0412", "2026-04-12", "USD")
    assert (result["incoterm"], result["incoterm_place"], result["country_of_origin"]) == ("FOB", "Shenzhen", "China")
    assert (result["subtotal"], result["freight"], result["insurance"], result["total"]) == ("2607.00", "180.00", "25.00", "2812.00")
    first = result["line_items"][0]
    assert first == {
        "description": "Cordless drill 18V", "sku": "TB-100", "hs_code_as_printed": "8467.21",
        "quantity": "50", "unit_of_measure": "pcs", "unit_price": "32.50", "line_total": "1625.00",
        "currency": "USD", "country_of_origin": "CN", "line_no": 1, "fields_needing_review": [],
    }
    assert len(result["line_items"]) == 3
    assert result["line_items_total"] == "2607.00"
    assert result["fields_needing_review"] == []
    assert result["review_required"] is True
    assert result["classification"]["hs_codes_inferred"] is False


def test_hs_code_and_origin_never_invented_without_printed_columns():
    text = ("Acme Ltd\nInvoice No: X-1\nDate: 2026-01-01\nBuyer: Imports Co\n"
            "Description Qty Unit Price Amount\nLaptop computer model 8471 CN 2 500.00 1000.00\n"
            "Subtotal: USD 1000.00\nTotal: USD 1000.00")
    item = extract_commercial_invoice(text)["line_items"][0]
    assert item["hs_code_as_printed"] is None
    assert item["country_of_origin"] is None
    assert item["sku"] is None
    assert "8471" in item["description"]  # kept as text, not promoted to a tariff code


def test_spanish_layout_without_units():
    text = ("Distribuidora Andina S.A.\nFactura No: DA-77\nFecha: 15 de marzo de 2026\nBill To: Caribe Imports Ltd\n"
            "Descripción Cantidad Precio Importe\nCafé molido 500g 100 3.20 320.00\nAzúcar morena 1kg 50 1.80 90.00\n"
            "Subtotal: USD 410.00\nTotal: USD 410.00")
    result = extract_commercial_invoice(text)
    assert [(i["description"], i["quantity"], i["unit_price"], i["line_total"]) for i in result["line_items"]] == [
        ("Café molido 500g", "100", "3.20", "320.00"), ("Azúcar morena 1kg", "50", "1.80", "90.00")]
    assert all(i["unit_of_measure"] is None for i in result["line_items"])  # not printed, not guessed


def test_row_arithmetic_and_subtotal_mismatches_are_flagged_not_fixed():
    text = ("ACME Exports\nInvoice No: A-9\nDate: 2026-05-01\nBuyer: Test Imports\n"
            "Description Qty Unit Price Amount\nWidget blue 10 2.50 30.00\nWidget red 4 1.00 4.00\n"
            "Subtotal: USD 40.00\nTotal: USD 40.00")
    result = extract_commercial_invoice(text)
    first = result["line_items"][0]
    assert first["line_total"] == "30.00"  # printed value kept
    assert set(first["fields_needing_review"]) == {"quantity", "unit_price", "line_total"}
    messages = " ".join(issue["message"] for issue in result["issues"])
    assert "does not equal the line total" in messages
    assert "not the invoice subtotal" in messages
    assert {"line_items", "subtotal"} <= set(result["fields_needing_review"])


def test_missing_parties_and_table_are_reported():
    result = extract_commercial_invoice("Some Supplier\nInvoice No: Z-1\nTotal: USD 10.00")
    assert result["buyer"] is None and result["line_items"] == []
    assert {"buyer", "line_items"} <= set(result["fields_needing_review"])
    assert any("No line-item table" in issue["message"] for issue in result["issues"])


def test_wrapped_description_is_joined_and_flagged():
    items, _ = extract_line_items(
        "Description Qty Unit Price Amount\nStainless steel bolts M8 100 0.20 20.00\nzinc coated, box of 100\nSubtotal: 20.00",
        "USD",
    )
    assert items[0]["description"] == "Stainless steel bolts M8 zinc coated, box of 100"
    assert "description" in items[0]["fields_needing_review"]


def test_extracts_line_items_from_a_real_pdf_text_layer():
    from app.main import _extract_pdf

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 800
    for line in STANDARD.splitlines():
        pdf.drawString(40, y, line)
        y -= 16
    pdf.save()
    text, used_ocr, pages = _extract_pdf(buffer.getvalue())
    result = extract_commercial_invoice(text)
    assert used_ocr is False and pages == 1
    assert len(result["line_items"]) == 3
    assert result["line_items"][2]["line_total"] == "132.00"


def test_pilot_export_writes_excel_friendly_csvs(tmp_path):
    import csv
    from app.pilot_export import write_pilot_csvs

    result = extract_commercial_invoice(STANDARD)
    result["line_items"][0]["description"] = "=HYPERLINK(\"http://evil\")"  # formula injection attempt
    invoices, lines = write_pilot_csvs({"invoice-001.pdf": result}, tmp_path)
    with invoices.open(encoding="utf-8-sig") as handle:
        head = list(csv.DictReader(handle))
    with lines.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert head[0]["buyer_name"] == "Island Hardware Ltd." and head[0]["line_count"] == "3"
    assert head[0]["review_status"] == "pending"
    assert len(rows) == 3 and rows[1]["unit_price"] == "4.25"
    assert rows[0]["description"].startswith("'=")  # neutralised for Excel


def test_address_starting_with_unit_is_not_mistaken_for_table_header():
    result = extract_commercial_invoice(
        "Example Co\nInvoice No: X-2\nDate: 2026-03-03\nBuyer: Example Engineering Supplies Ltd.\n"
        "Unit 4 Sample Park, Leeds, United Kingdom\nPart No Description Qty Unit Price Amount\n"
        "BM-77 Ball bearing 400 pcs 1.25 500.00\nSubtotal: EUR 500.00\nTotal: EUR 500.00")
    assert result["buyer"]["address"] == "Unit 4 Sample Park, Leeds, United Kingdom"
    assert len(result["line_items"]) == 1
