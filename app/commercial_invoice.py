"""Commercial-invoice extraction (PROTOTYPE): header parties, trade terms and line items.

Status: prototype for the customs-broker validation programme. It is not wired
to a public endpoint yet. It reuses the existing header extractor
(``app.extraction``) and adds the fields a customs broker needs.

Principles
- **Never invent values.** A field that is not printed on the invoice is
  ``None``. Line-item fields are taken only from the row text.
- **Tariff codes are never inferred.** ``hs_code_as_printed`` holds a code only
  when the invoice itself prints one in an HS/tariff column. Classification is
  a broker's legal decision and a separate, future capability.
- **Flag, don't fix.** Arithmetic or completeness problems become ``issues`` and
  ``fields_needing_review``; values are never "corrected" silently.
- Output follows ``SCHEMA_VERSION`` so the rule engine and an AI engine can be
  benchmarked on identical structures (see ``scripts/compare_engines.py``).

Limits of the rule-based approach (expected, to be measured): it reads OCR or
PDF text line by line, so tables whose columns wrap onto several lines, rotated
scans, or rows without a numeric quantity/price/total will be missed or flagged.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.extraction import (
    _amounts_in_line, _clean_text, _label_amount, _normalise_amount, extract_invoice_fields,
)

SCHEMA_VERSION = "commercial_invoice.v1"

INCOTERMS = ("EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP")
_UOM = (
    r"pcs|pc|pieces?|units?|ea|each|ctns?|cartons?|boxes|box|bx|kgs?|kg|lbs?|lb|"
    r"g|m|mtrs?|meters?|l|ltrs?|litres?|liters?|pairs?|prs|dozen|doz|sets?|rolls?|bags?|"
    r"drums?|pallets?|plts?|cases?|cs|ft|yds?|sqm|m2|m3|cbm|unidades|uds|cajas"
)
_UOM_RE = re.compile(rf"^(?:{_UOM})\.?$", re.I)
_HEADER_QTY = re.compile(r"\b(qty|quantity|cantidad|cant\.?|pcs|units?)\b", re.I)
_HEADER_PRICE = re.compile(r"\b(unit\s*price|price|rate|precio(?:\s+unitario)?|unit\s*cost|p\.?\s*unit)\b", re.I)
_HEADER_AMOUNT = re.compile(r"\b(amount|line\s*total|total|importe|ext(?:ended)?\.?\s*(?:price|amount)?|value)\b", re.I)
_HEADER_DESC = re.compile(r"\b(description|item|goods|product|descripci[oó]n|art[ií]culo|commodity)\b", re.I)
_HEADER_SKU = re.compile(r"\b(sku|part\s*(?:no|number|#)|item\s*(?:no|code|#)|code|ref(?:erence)?|model)\b", re.I)
_HEADER_HS = re.compile(r"\b(hs|h\.s\.|hts|tariff|commodity\s*code)\b", re.I)
_HEADER_ORIGIN = re.compile(r"\b(origin|coo|c\.o\.o\.|country\s+of\s+origin|origen)\b", re.I)
_END_OF_TABLE = re.compile(
    r"^\s*(sub\s*total|subtotal|total|grand\s+total|amount\s+due|balance|tax|vat|gst|iva|freight|"
    r"shipping|insurance|discount|notes?|terms|bank|payment|signature|declar)", re.I
)
_HS_TOKEN = re.compile(r"^\d{4}(?:\.?\d{2}){1,3}$")
_ISO2 = re.compile(r"^[A-Z]{2}$")
_NUMBER = re.compile(r"^\(?-?\d[\d,.]*\)?$")
_CURRENCY_CODES = "USD|BZD|EUR|GBP|CAD|AUD|NZD|MXN|JPY|CHF|INR|SGD|HKD|BRL|COP|GTQ|HNL|CRC|PAB|DOP|JMD|TTD|CNY|RMB"


def _dec(value: str | None) -> Decimal | None:
    try:
        return Decimal(value) if value is not None else None
    except (InvalidOperation, ValueError):
        return None


def _labelled_block(lines: list[str], labels: str) -> dict[str, Any] | None:
    """Party block: the label line's own text, else the next 1-3 lines."""
    label_re = re.compile(rf"^\s*(?:{labels})\s*[:\-]?\s*(.*)$", re.I)
    for index, line in enumerate(lines):
        match = label_re.match(line)
        if not match:
            continue
        inline = match.group(1).strip()
        following = []
        for nxt in lines[index + 1:index + 4]:
            if re.match(r"^\s*[A-Za-z ]{2,30}\s*:", nxt) or _END_OF_TABLE.match(nxt) or _HEADER_QTY.search(nxt):
                break
            following.append(nxt.strip())
        name = inline or (following.pop(0) if following else "")
        if not name:
            return None
        tax = None
        for candidate in [inline, *following]:
            tax_match = re.search(r"\b(?:tax\s*id|tin|vat\s*(?:no|reg)|ein|rfc|nit|rnc)\s*[:#]?\s*([A-Z0-9-]{4,})", candidate, re.I)
            if tax_match:
                tax = tax_match.group(1)
        address = ", ".join(part for part in following if part and not re.search(r"\btax\s*id\b|\btin\b", part, re.I)) or None
        return {"name": name, "address": address, "tax_id": tax}
    return None


def _find_table_header(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if _HEADER_QTY.search(line) and (_HEADER_PRICE.search(line) or _HEADER_AMOUNT.search(line)):
            return index
    return None


def _parse_row(line: str, header: str, currency: str | None) -> dict[str, Any] | None:
    # Drop currency symbols/codes attached to amounts so "$2.50" / "USD 25.00" read as numbers.
    cleaned = re.sub(r"(?:BZ\$|[$€£])\s*(?=\d)", "", line)
    cleaned = re.sub(rf"\b(?:{_CURRENCY_CODES})\s+(?=\d)", "", cleaned)
    tokens = cleaned.split()
    # Collect trailing numeric tokens (amounts) from the right.
    numeric_tail: list[str] = []
    while tokens and _NUMBER.match(tokens[-1]):
        numeric_tail.insert(0, tokens.pop())
        if len(numeric_tail) == 3:
            break
    if len(numeric_tail) < 2:
        return None  # a line-item row needs at least quantity/price/total style numbers

    quantity = unit = unit_price = line_total = None
    if len(numeric_tail) == 3:
        quantity, unit_price, line_total = numeric_tail
    else:
        # Two numbers: "<qty> <uom?> ... <price> <total>" or "<desc> <qty> <total>".
        unit_price_candidate, line_total = numeric_tail
        if tokens and _UOM_RE.match(tokens[-1]) and len(tokens) >= 2 and _NUMBER.match(tokens[-2]):
            unit = tokens.pop()
            quantity = tokens.pop()
            unit_price = unit_price_candidate
        else:
            # Ambiguous: could be qty+total or price+total. Keep the total, flag the rest.
            quantity_like = re.fullmatch(r"\d+", unit_price_candidate)
            if quantity_like:
                quantity = unit_price_candidate
            else:
                unit_price = unit_price_candidate
    if unit is None and tokens and _UOM_RE.match(tokens[-1]):
        unit = tokens.pop()
    # Leading quantity layout: "10 pcs Widget ... 2.50 25.00"
    if quantity is not None and len(numeric_tail) == 3 and tokens and _UOM_RE.match(tokens[-1]):
        unit = tokens.pop()
    if len(numeric_tail) == 2 and quantity is None and tokens and re.fullmatch(r"\d+(?:\.\d+)?", tokens[0]):
        quantity = tokens.pop(0)
        if tokens and _UOM_RE.match(tokens[0]):
            unit = tokens.pop(0)

    sku = hs = origin = None
    if _HEADER_HS.search(header):
        for i, tok in enumerate(tokens):
            if _HS_TOKEN.match(tok):
                hs = tokens.pop(i)
                break
    if _HEADER_ORIGIN.search(header):
        for i in range(len(tokens) - 1, -1, -1):
            if _ISO2.match(tokens[i]):
                origin = tokens.pop(i)
                break
    if _HEADER_SKU.search(header) and tokens and re.fullmatch(r"(?=.*\d)[A-Z0-9][A-Z0-9._/-]{2,}", tokens[0], re.I):
        sku = tokens.pop(0)
    description = " ".join(tokens).strip(" -|") or None
    if description is None or not re.search(r"[A-Za-z]", description):
        return None

    def money(value: str | None) -> str | None:
        return _normalise_amount(value) if value else None

    qty_norm = None
    if quantity is not None:
        try:
            qty_norm = format(Decimal(quantity.replace(",", "")).normalize(), "f")
        except (InvalidOperation, ValueError):
            qty_norm = None
    return {
        "description": description,
        "sku": sku,
        "hs_code_as_printed": hs,
        "quantity": qty_norm,
        "unit_of_measure": unit.lower().rstrip(".") if unit else None,
        "unit_price": money(unit_price),
        "line_total": money(line_total),
        "currency": currency,
        "country_of_origin": origin,
    }


def extract_line_items(text: str, currency: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    lines = [line.strip() for line in _clean_text(text).splitlines() if line.strip()]
    issues: list[dict[str, str]] = []
    header_index = _find_table_header(lines)
    if header_index is None:
        issues.append({"severity": "warning", "field": "line_items",
                       "message": "No line-item table header (quantity and price/amount columns) was found."})
        return [], issues
    header = lines[header_index]
    items: list[dict[str, Any]] = []
    for line in lines[header_index + 1:]:
        if _END_OF_TABLE.match(line):
            break
        row = _parse_row(line, header, currency)
        if row is None:
            # Not a row (fewer than two trailing numbers): treat text as a wrapped
            # description of the previous row, and flag it for review.
            if items and re.search(r"[A-Za-z]{2,}", line):
                # Wrapped description continuation of the previous row.
                items[-1]["description"] = f"{items[-1]['description']} {line}"
                items[-1].setdefault("_notes", []).append("description continued on next line")
            continue
        items.append(row)

    for number, item in enumerate(items, start=1):
        item["line_no"] = number
        review: list[str] = []
        qty, price, total = _dec(item["quantity"]), _dec(item["unit_price"]), _dec(item["line_total"])
        for field in ("quantity", "unit_price", "line_total"):
            if item[field] is None:
                review.append(field)
        if qty is not None and price is not None and total is not None and abs(qty * price - total) > Decimal("0.02"):
            review.extend(["quantity", "unit_price", "line_total"])
            issues.append({"severity": "warning", "field": f"line_items[{number}]",
                           "message": f"Quantity x unit price ({qty * price:.2f}) does not equal the line total ({total})."})
        if item.pop("_notes", None):
            review.append("description")
        item["fields_needing_review"] = sorted(set(review))
    return items, issues


def extract_commercial_invoice(raw_text: str) -> dict[str, Any]:
    text = _clean_text(raw_text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    base = extract_invoice_fields(text)
    fields = base["fields"]

    seller = _labelled_block(lines, r"seller|exporter|shipper|supplier|vendor|sold\s+by|from|vendedor|exportador|proveedor")
    buyer = _labelled_block(lines, r"buyer|importer|consignee|bill\s+to|sold\s+to|ship\s+to|customer|comprador|importador|consignatario")
    if seller is None and fields["supplier_name"]:
        seller = {"name": fields["supplier_name"], "address": None, "tax_id": None}

    incoterm_match = re.search(rf"\b({'|'.join(INCOTERMS)})\b(?:\s+([A-Z][A-Za-z .-]{{2,30}}))?", text)
    origin_match = re.search(r"\b(?:country\s+of\s+origin|origin|pa[ií]s\s+de\s+origen)\s*[:\-]\s*([A-Za-z][A-Za-z .]{1,40})", text, re.I)
    freight = _label_amount(text, r"(?:freight|shipping|flete|env[ií]o)")
    insurance = _label_amount(text, r"(?:insurance|seguro)")

    items, item_issues = extract_line_items(text, fields["currency"])
    issues = [{"severity": "warning", "field": "header", "message": message} for message in base["warnings"]]
    issues.extend(item_issues)

    review = set(base["fields_needing_review"])
    if buyer is None:
        review.add("buyer")
        issues.append({"severity": "warning", "field": "buyer", "message": "Buyer/importer was not identified."})
    if seller is None:
        review.add("seller")
    line_sum = sum((_dec(i["line_total"]) or Decimal(0)) for i in items) if items else None
    subtotal = _dec(fields["subtotal"])
    reference = subtotal if subtotal is not None else (_dec(fields["total"]) if fields["tax"] is None and freight is None else None)
    if items and reference is not None and abs(line_sum - reference) > Decimal("0.02"):
        review.update({"line_items", "subtotal"})
        issues.append({"severity": "warning", "field": "line_items",
                       "message": f"Line totals add up to {line_sum:.2f}, not the invoice subtotal {reference}."})
    if any(item["fields_needing_review"] for item in items):
        review.add("line_items")
    if not items:
        review.add("line_items")

    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": "credit_note" if base["extraction_metadata"]["document_type"] == "credit_note" else "commercial_invoice",
        "seller": seller,
        "buyer": buyer,
        "invoice_number": fields["invoice_number"],
        "invoice_date": fields["invoice_date"],
        "currency": fields["currency"],
        "incoterm": incoterm_match.group(1) if incoterm_match else None,
        "incoterm_place": (incoterm_match.group(2) or "").strip() or None if incoterm_match else None,
        "country_of_origin": origin_match.group(1).strip() if origin_match else None,
        "subtotal": fields["subtotal"],
        "discount": fields["discount"],
        "freight": freight,
        "insurance": insurance,
        "tax": fields["tax"],
        "total": fields["total"],
        "line_items": items,
        "line_items_total": f"{line_sum:.2f}" if line_sum is not None else None,
        "issues": issues,
        "fields_needing_review": sorted(review),
        "review_required": True,
        "classification": {
            "hs_codes_inferred": False,
            "note": "Tariff classification, duties and declarations are not determined by Quillvora. "
                    "hs_code_as_printed is copied only when printed on the invoice.",
        },
        "extraction_metadata": {"engine": "rules", "method": "rule_based_text_extraction"},
    }


_KEY_HEADER_FIELDS = ("invoice_number", "invoice_date", "currency", "total")


def validate_commercial_invoice(result: dict[str, Any], *, extra_uncertain: list[str] | None = None) -> dict[str, Any]:
    """Apply engine-independent checks to a commercial_invoice.v1 result.

    Used for the AI engine's output so both engines are reviewed the same way:
    row arithmetic, line sum vs subtotal, missing key fields and parties, and any
    fields the engine itself reported as uncertain. Values are never changed.
    """
    doc = dict(result)
    issues: list[dict[str, str]] = list(doc.get("issues") or [])
    review: set[str] = set(doc.get("fields_needing_review") or [])
    items = [dict(item) for item in (doc.get("line_items") or [])]
    uncertain = list(extra_uncertain or [])

    for number, item in enumerate(items, start=1):
        item["line_no"] = number
        flags = set(item.get("fields_needing_review") or [])
        for name in ("description", "quantity", "unit_price", "line_total"):
            if item.get(name) in (None, ""):
                flags.add(name)
        qty, price, total = _dec(item.get("quantity")), _dec(item.get("unit_price")), _dec(item.get("line_total"))
        if qty is not None and price is not None and total is not None and abs(qty * price - total) > Decimal("0.02"):
            flags.update({"quantity", "unit_price", "line_total"})
            issues.append({"severity": "warning", "field": f"line_items[{number}]",
                           "message": f"Quantity x unit price ({qty * price:.2f}) does not equal the line total ({total})."})
        item["fields_needing_review"] = sorted(flags)
        if flags:
            review.add("line_items")

    for entry in uncertain:
        match = re.match(r"line_items\[(\d+)\]\.?(\w+)?", entry)
        if match:
            index = int(match.group(1))
            # Accept 0- or 1-based indexes from the engine; never fail on a bad index.
            target = items[index - 1] if 1 <= index <= len(items) else (items[index] if 0 <= index < len(items) else None)
            if target is not None and match.group(2):
                target["fields_needing_review"] = sorted(set(target["fields_needing_review"]) | {match.group(2)})
            review.add("line_items")
        else:
            review.add(entry)
        issues.append({"severity": "warning", "field": entry, "message": "The engine reported this field as unreadable or uncertain."})

    for name in _KEY_HEADER_FIELDS:
        if doc.get(name) in (None, ""):
            review.add(name)
            issues.append({"severity": "warning", "field": name, "message": f"{name.replace('_', ' ').capitalize()} was not identified."})
    for party in ("seller", "buyer"):
        if not (doc.get(party) or {}).get("name"):
            review.add(party)
            issues.append({"severity": "warning", "field": party, "message": f"{party.capitalize()} was not identified."})
    if not items:
        review.add("line_items")
        issues.append({"severity": "warning", "field": "line_items", "message": "No line items were extracted."})

    line_sum = sum((_dec(i.get("line_total")) or Decimal(0)) for i in items) if items else None
    subtotal = _dec(doc.get("subtotal"))
    if items and subtotal is not None and abs(line_sum - subtotal) > Decimal("0.02"):
        review.update({"line_items", "subtotal"})
        issues.append({"severity": "warning", "field": "line_items",
                       "message": f"Line totals add up to {line_sum:.2f}, not the invoice subtotal {subtotal}."})

    total = _dec(doc.get("total"))
    doc.update({
        "schema_version": SCHEMA_VERSION,
        "document_type": "credit_note" if total is not None and total < 0 else doc.get("document_type") or "commercial_invoice",
        "line_items": items,
        "line_items_total": f"{line_sum:.2f}" if line_sum is not None else None,
        "issues": issues,
        "fields_needing_review": sorted(review),
        "review_required": True,
        "classification": {
            "hs_codes_inferred": False,
            "note": "Tariff classification, duties and declarations are not determined by Quillvora. "
                    "hs_code_as_printed is copied only when printed on the invoice.",
        },
    })
    return doc
