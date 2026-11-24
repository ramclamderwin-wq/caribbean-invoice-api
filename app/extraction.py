from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

# Deliberately conservative, layout-tolerant rules. This is deterministic
# extraction, not an AI model; all outputs require verification against source.
_AMOUNT = r"(?:\(?\s*-?\s*(?:[A-Z]{3}\s*)?(?:[$€£]\s*)?\d[\d.,' ]*(?:\d{1,4})?\s*\)?)"
_DATE = (
    r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}|"
    r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|"
    r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|"
    r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})"
)


def _clean_text(value: str) -> str:
    value = value.replace("\x00", " ").replace("\u00a0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _first_match(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip(" \t:#")
    return None


def _normalise_amount(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().replace(" ", "").replace("'", "")
    negative = value.startswith("(") and value.endswith(")")
    value = value.strip("()")
    value = re.sub(r"^[A-Z]{3}", "", value, flags=re.I)
    value = value.replace("BZ$", "").replace("$", "").replace("€", "").replace("£", "")
    # Infer decimal separator when both comma and dot occur; otherwise a
    # single comma with exactly two trailing digits is treated as decimal.
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        tail = value.rsplit(",", 1)[-1]
        value = value.replace(",", ".") if len(tail) in (1, 2) else value.replace(",", "")
    try:
        amount = Decimal(value)
        if negative:
            amount = -amount
        return str(amount.quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return None


def _label_value(text: str, labels: str) -> str | None:
    # Accept amount on same line or next line, with optional currency prefix.
    pattern = rf"\b(?:{labels})\b\s*[:#\-]?\s*({_AMOUNT})"
    return _normalise_amount(_first_match([pattern], text))


def _supplier(lines: list[str]) -> str | None:
    ignored = re.compile(
        r"\b(invoice|receipt|statement|tax invoice|bill to|ship to|date|"
        r"invoice number|invoice no|invoice #|page \d+)\b", re.I
    )
    for line in lines[:10]:
        candidate = line.strip(" |\t")
        if len(candidate) >= 2 and not ignored.search(candidate):
            if not re.fullmatch(r"[-=*_ ]+", candidate):
                return candidate[:160]
    return None


def extract_invoice_fields(raw_text: str) -> dict[str, Any]:
    text = _clean_text(raw_text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    invoice_number = _first_match([
        r"\b(?:invoice\s*(?:number|no\.?|#|num(?:ber)?)|inv\s*(?:no\.?|#)?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{1,})"
    ], text)
    invoice_date = _first_match([
        rf"\b(?:invoice\s*date|date\s*of\s*invoice|date)\s*[:#\-]?\s*{_DATE}"
    ], text)
    supplier = _supplier(lines)

    subtotal = _label_value(text, r"sub[\s-]?total|net\s+amount|amount\s+before\s+tax")
    tax = _label_value(text, r"tax|gst|vat|sales\s+tax")
    total = _label_value(text, r"grand\s+total|total\s+due|amount\s+due|balance\s+due|invoice\s+total|total")

    currency = _first_match([
        r"\bcurrency\s*[:\-]?\s*([A-Z]{3})\b",
        r"\b(USD|BZD|EUR|GBP|CAD|AUD|NZD|MXN|JPY|CHF|INR|SGD|HKD)\b",
        r"\b(BZ\$)\b",
    ], text)
    if currency:
        currency = {"BZ$": "BZD"}.get(currency.upper(), currency.upper())

    fields = {
        "supplier_name": supplier,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "currency": currency,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
    }
    warnings: list[str] = []
    if not supplier:
        warnings.append("Supplier name was not confidently identified.")
    if not invoice_number:
        warnings.append("Invoice number was not confidently identified.")
    if not invoice_date:
        warnings.append("Invoice date was not confidently identified.")
    if not currency:
        warnings.append("Currency was not explicitly identified; verify it on the invoice.")
    if not total:
        warnings.append("Invoice total was not confidently identified.")

    if subtotal is not None and tax is not None and total is not None:
        try:
            difference = Decimal(subtotal) + Decimal(tax) - Decimal(total)
            if abs(difference) > Decimal("0.02"):
                warnings.append(
                    "Subtotal plus tax does not equal the extracted total; check discounts, "
                    "shipping, fees, rounding, and the original invoice."
                )
        except InvalidOperation:
            warnings.append("Could not validate the invoice arithmetic.")

    present = [key for key, value in fields.items() if value is not None]
    # These are completeness indicators only, not calibrated probabilities.
    confidence = {key: (0.5 if value is not None else 0.0) for key, value in fields.items()}
    return {
        "fields": fields,
        "confidence": confidence,
        "confidence_type": "heuristic_presence_indicator_not_probability",
        "warnings": warnings,
        "review_required": True,
        "extraction_metadata": {
            "method": "rule_based_text_extraction",
            "fields_found": len(present),
            "fields_expected": len(fields),
        },
    }
