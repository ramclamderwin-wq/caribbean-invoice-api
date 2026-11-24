from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

_CURRENCY_CODES = {
    "USD", "BZD", "EUR", "GBP", "CAD", "AUD", "NZD", "MXN", "JPY",
    "CHF", "INR", "SGD", "HKD", "BRL", "COP", "GTQ", "HNL", "CRC",
    "PAB", "DOP", "JMD", "TTD",
}
_CURRENCY_SYMBOLS = {"BZ$": "BZD", "$": None, "€": "EUR", "£": "GBP"}
# Numeric tokens are intentionally strict: malformed OCR such as 1O5.00
# must fail as a whole rather than silently becoming 1.00.
_AMOUNT_TOKEN = re.compile(
    r"(?<![A-Za-z0-9.,])(?:BZ\$\s*|USD\s*|BZD\s*|EUR\s*|GBP\s*|"
    r"CAD\s*|AUD\s*|[$€£]\s*)?"
    r"\(?-?(?:\d{1,3}(?:[,. ]\d{3})+|\d+)(?:[,.]\d{1,2})?\)?"
    r"(?![A-Za-z0-9%.,])",
    re.IGNORECASE,
)
_DATE_TOKEN = re.compile(
    r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}|"
    r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|"
    r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|"
    r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
    re.IGNORECASE,
)


def _clean_text(value: str) -> str:
    value = value.replace("\x00", " ").replace("\u00a0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _normalise_amount(value: str | None) -> str | None:
    if not value:
        return None
    original = value.strip()
    negative = original.startswith("(") and original.endswith(")")
    value = original.strip("()").strip()
    value = re.sub(r"^(?:BZ\$|USD|BZD|EUR|GBP|CAD|AUD|[$€£])\s*", "", value, flags=re.I)
    value = value.replace(" ", "").replace("'", "")
    if not re.fullmatch(r"-?\d[\d.,]*", value):
        return None

    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        tail = value.rsplit(",", 1)[-1]
        if len(tail) in (1, 2):
            value = value.replace(",", ".")
        elif len(tail) == 3:
            value = value.replace(",", "")
        else:
            return None
    elif "." in value:
        tail = value.rsplit(".", 1)[-1]
        if len(tail) == 3:
            value = value.replace(".", "")
        elif len(tail) not in (1, 2):
            return None

    try:
        amount = Decimal(value)
        if negative:
            amount = -abs(amount)
        return str(amount.quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return None


def _amounts_in_line(line: str) -> list[str]:
    # Percentages are not amounts. A tax line may contain both a rate and
    # the monetary tax amount; preserve only currency/amount tokens.
    candidates: list[str] = []
    for match in _AMOUNT_TOKEN.finditer(line):
        token = match.group(0).strip()
        end = match.end()
        if end < len(line) and line[end:end + 1] == "%":
            continue
        if not any(ch.isdigit() for ch in token):
            continue
        candidates.append(token)
    return candidates


def _label_amount(text: str, labels: str, *, allow_next_line: bool = True) -> str | None:
    label_re = re.compile(rf"^\s*(?:{labels})\s*(?:\([^\n)]*%\))?\s*[:#\-]?\s*(.*?)\s*$", re.I)
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = label_re.match(line)
        if not match:
            continue
        value_part = match.group(1)
        amounts = _amounts_in_line(value_part)
        if amounts:
            # Prefer the last monetary token, e.g. "GST (12.5%): BZ$ 50.00".
            return _normalise_amount(amounts[-1])
        if allow_next_line and index + 1 < len(lines):
            amounts = _amounts_in_line(lines[index + 1])
            if amounts:
                return _normalise_amount(amounts[-1])
    return None


def _normalise_date(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip().replace(",", "")
    formats = ("%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y",
               "%b %d %Y", "%B %d %Y")
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    spanish = re.fullmatch(r"(\d{1,2})\s+de\s+([A-Za-záéíóúñ]+)\s+de\s+(\d{4})", value, re.I)
    if spanish:
        day, month_name, year = spanish.groups()
        spanish_months = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "setiembre": 9, "octubre": 10,
            "noviembre": 11, "diciembre": 12,
        }
        month = spanish_months.get(month_name.lower())
        if month:
            try:
                return date(int(year), month, int(day)).isoformat()
            except ValueError:
                return None
    numeric = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", value)
    if numeric:
        first, second, year = map(int, numeric.groups())
        if year < 100:
            year += 2000 if year < 70 else 1900
        # Resolve only when one component cannot be a month. Ambiguous
        # values such as 01/02/2026 are deliberately not guessed.
        if first > 12 >= second:
            day, month = first, second
        elif second > 12 >= first:
            month, day = first, second
        else:
            return None
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    return None


def _invoice_date(text: str) -> tuple[str | None, bool]:
    lines = text.splitlines()
    # Explicit invoice-date labels take precedence. Due dates are never used.
    for line in lines:
        if re.match(r"^\s*(?:invoice\s+date|date\s+of\s+invoice|fecha\s+de\s+factura)\b", line, re.I):
            match = _DATE_TOKEN.search(line)
            if match:
                return _normalise_date(match.group(1)), True
    for line in lines:
        if re.match(r"^\s*(?:date|fecha)\s*[:#\-]", line, re.I) and not re.search(r"due|vencimiento", line, re.I):
            match = _DATE_TOKEN.search(line)
            if match:
                return _normalise_date(match.group(1)), True
    return None, False


def _first_match(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip(" \t:#")
    return None


def _supplier(lines: list[str]) -> str | None:
    ignored = re.compile(
        r"\b(invoice|factura|receipt|statement|tax invoice|bill to|ship to|date|"
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
        r"\b(?:invoice\s*(?:number|no\.?|#|num(?:ber)?)|inv\s*(?:no\.?|#)|factura\s*(?:no\.?|#|n[uú]mero)|n[uú]mero\s+de\s+factura)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{1,})"
    ], text)
    invoice_date, date_label_found = _invoice_date(text)
    supplier = _supplier(lines)

    subtotal = _label_amount(text, r"(?:sub\s*total|subtotal|sous\s*total|subtotal)")
    tax = _label_amount(text, r"(?:tax|gst|vat|sales\s+tax|iva|impuesto|impuestos)")
    total = _label_amount(
        text,
        r"(?:grand\s+total|total\s+due|amount\s+due|balance\s+due|invoice\s+total|total\s+a\s+pagar|importe\s+total|total)",
    )

    currency = None
    currency_match = re.search(r"\b(" + "|".join(sorted(_CURRENCY_CODES)) + r")\b", text, re.I)
    if currency_match:
        currency = currency_match.group(1).upper()
    elif "BZ$" in text.upper():
        currency = "BZD"
    elif "€" in text:
        currency = "EUR"
    elif "£" in text:
        currency = "GBP"
    elif "$" in text:
        # A bare dollar sign does not identify which dollar currency.
        currency = None

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
        warnings.append("Invoice date was not confidently identified or was ambiguous; verify the original.")
    if not currency:
        warnings.append("Currency was not explicitly identified; verify it on the invoice.")
    if not total:
        warnings.append("Invoice total was not confidently identified.")
    if re.search(r"\b(?:due\s+date|fecha\s+de\s+vencimiento)\b", text, re.I) and not date_label_found:
        warnings.append("Only a due date may be present; it was not used as the invoice date.")

    if subtotal is not None and tax is not None and total is not None:
        difference = Decimal(subtotal) + Decimal(tax) - Decimal(total)
        if abs(difference) > Decimal("0.02"):
            warnings.append(
                "Subtotal plus tax does not equal the extracted total; check discounts, "
                "shipping, fees, rounding, and the original invoice."
            )

    # Confidence is intentionally unavailable until calibrated against a
    # representative, labelled invoice corpus. Do not fabricate a score.
    confidence = {key: None for key in fields}
    return {
        "fields": fields,
        "confidence": confidence,
        "confidence_type": "not_available_not_calibrated",
        "warnings": warnings,
        "review_required": True,
        "extraction_metadata": {
            "method": "rule_based_text_extraction",
            "fields_found": sum(value is not None for value in fields.values()),
            "fields_expected": len(fields),
        },
    }
