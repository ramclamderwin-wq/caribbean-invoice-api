"""Concierge-pilot spreadsheet export (PROTOTYPE).

Turns ``commercial_invoice.v1`` results into two CSV tables that open in Excel:

- ``invoices.csv``: one row per invoice (parties, terms, totals, review status);
- ``line_items.csv``: one row per line item, keyed by document name and line number.

Every cell is either a value printed on the invoice, a reviewer correction, or
blank. ``review_flags`` lists what a person must check. Usage:

    python -m app.pilot_export results.json out_dir/
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Iterable

INVOICE_COLUMNS = [
    "document", "invoice_number", "invoice_date", "seller_name", "seller_address", "seller_tax_id",
    "buyer_name", "buyer_address", "buyer_tax_id", "currency", "incoterm", "incoterm_place",
    "country_of_origin", "subtotal", "discount", "freight", "insurance", "tax", "total",
    "line_count", "line_items_total", "review_flags", "issues", "reviewed_by", "review_status",
]
LINE_COLUMNS = [
    "document", "line_no", "sku", "description", "hs_code_as_printed", "country_of_origin",
    "quantity", "unit_of_measure", "unit_price", "line_total", "currency", "review_flags",
]


def _party(result: dict[str, Any], key: str, field: str) -> Any:
    party = result.get(key) or {}
    return party.get(field)


def _safe(value: Any) -> Any:
    """Prevent spreadsheet formula injection from invoice text (=, +, -, @)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@") and not _looks_numeric(value):
        return "'" + value
    return value


def _looks_numeric(value: str) -> bool:
    try:
        float(value.replace(",", ""))
        return True
    except ValueError:
        return False


def invoice_row(document: str, result: dict[str, Any]) -> dict[str, Any]:
    row = {
        "document": document,
        **{field: result.get(field) for field in (
            "invoice_number", "invoice_date", "currency", "incoterm", "incoterm_place", "country_of_origin",
            "subtotal", "discount", "freight", "insurance", "tax", "total", "line_items_total")},
        "seller_name": _party(result, "seller", "name"),
        "seller_address": _party(result, "seller", "address"),
        "seller_tax_id": _party(result, "seller", "tax_id"),
        "buyer_name": _party(result, "buyer", "name"),
        "buyer_address": _party(result, "buyer", "address"),
        "buyer_tax_id": _party(result, "buyer", "tax_id"),
        "line_count": len(result.get("line_items") or []),
        "review_flags": "; ".join(result.get("fields_needing_review") or []),
        "issues": " | ".join(issue.get("message", "") for issue in result.get("issues") or []),
        "reviewed_by": "",
        "review_status": "pending",
    }
    return {key: _safe(row.get(key)) for key in INVOICE_COLUMNS}


def line_rows(document: str, result: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for item in result.get("line_items") or []:
        row = {"document": document, **item, "review_flags": "; ".join(item.get("fields_needing_review") or [])}
        yield {key: _safe(row.get(key)) for key in LINE_COLUMNS}


def write_pilot_csvs(results: dict[str, dict[str, Any]], out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    invoices, lines = out / "invoices.csv", out / "line_items.csv"
    # utf-8-sig so Excel shows accented supplier names correctly.
    with invoices.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=INVOICE_COLUMNS)
        writer.writeheader()
        for document, result in results.items():
            writer.writerow(invoice_row(document, result))
    with lines.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=LINE_COLUMNS)
        writer.writeheader()
        for document, result in results.items():
            writer.writerows(line_rows(document, result))
    return invoices, lines


if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) != 3:
        raise SystemExit("usage: python -m app.pilot_export results.json out_dir/")
    data = json.loads(Path(sys.argv[1]).read_text())
    print(*write_pilot_csvs(data, sys.argv[2]), sep="\n")
