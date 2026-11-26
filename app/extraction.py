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
    r"CAD\s*|AUD\s*|NZD\s*|MXN\s*|JPY\s*|CHF\s*|INR\s*|SGD\s*|HKD\s*|"
    r"BRL\s*|COP\s*|GTQ\s*|HNL\s*|CRC\s*|PAB\s*|DOP\s*|JMD\s*|TTD\s*|[$€£]\s*)?"
    r"\(?-?(?:\d{1,3}(?:[,. ]\d{3})+|\d+)(?:[,.]\d{1,2})?\)?"
    r"(?![A-Za-z0-9%])(?!(?:[.,]\d))",
    re.IGNORECASE,
)
_DATE_TOKEN = re.compile(
    r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}|"
    r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|"
    r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|"
    r"\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4}|"
    r"\d{1,2}\s+de\s+[A-Za-záéíóúñ]+\s+de\s+\d{4})",
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
    value = re.sub(r"^(?:BZ\$|USD|BZD|EUR|GBP|CAD|AUD|NZD|MXN|JPY|CHF|INR|SGD|HKD|BRL|COP|GTQ|HNL|CRC|PAB|DOP|JMD|TTD|[$€£])\s*", "", value, flags=re.I)
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
    # Strip sentence punctuation without changing decimal separators.
    line = line.rstrip(" \t.,;:")
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
    # Require an actual separator followed by a numeric/currency token.
    # This prevents "Total Tax" and "Tax ID" from being mistaken for
    # monetary labels just because they begin with "Total" or "Tax".
    label_re = re.compile(
        rf"^\s*(?:{labels})\b\s*(?:\([^\n)]*%\))?\s*(?:[:#\-]\s*|\s+)"
        rf"(?=(?:BZ\$|USD|BZD|EUR|GBP|CAD|AUD|NZD|MXN|JPY|CHF|INR|SGD|HKD|"
        rf"BRL|COP|GTQ|HNL|CRC|PAB|DOP|JMD|TTD)\s*[(+-]?\d|[(€£$-]|\d)"
        rf"((?:.*?))\s*$", re.I
    )
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = label_re.match(line)
        if not match:
            continue
        value_part = match.group(1)
        amounts = _amounts_in_line(value_part)
        if amounts:
            # The first token belongs to the labelled field. Later tokens
            # may be "Paid", "Balance", or another amount on the same line.
            return _normalise_amount(amounts[0])
        if allow_next_line and index + 1 < len(lines):
            amounts = _amounts_in_line(lines[index + 1])
            if amounts:
                return _normalise_amount(amounts[0])
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
    spanish_short = re.fullmatch(r"(\d{1,2})\s+(?:de\s+)?([A-Za-záéíóúñ]{3,4})\.?\s+(?:de\s+)?(\d{4})", value, re.I)
    if spanish:
        day, month_name, year = spanish.groups()
        spanish_months = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "setiembre": 9, "octubre": 10,
            "noviembre": 11, "diciembre": 12,
            "ene": 1, "enero": 1, "feb": 2, "febrero": 2,
            "mar": 3, "marzo": 3, "abr": 4, "abril": 4,
            "may": 5, "mayo": 5, "jun": 6, "junio": 6,
            "jul": 7, "julio": 7, "ago": 8, "agosto": 8,
            "sep": 9, "sept": 9, "set": 9, "oct": 10,
            "nov": 11, "dic": 12,
        }
        month = spanish_months.get(month_name.lower())
        if month:
            try:
                return date(int(year), month, int(day)).isoformat()
            except ValueError:
                return None
    if spanish_short:
        day, month_name, year = spanish_short.groups()
        spanish_months = {
            "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
            "jul": 7, "ago": 8, "sep": 9, "sept": 9, "set": 9,
            "oct": 10, "nov": 11, "dic": 12,
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
        if re.match(r"^\s*(?:invoice\s+date|date\s+of\s+invoice|fecha\s+de\s+factura|fecha\s+de\s+emisi[oó]n)\b", line, re.I):
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


_SUPPLIER_LABEL = re.compile(
    r"^\s*(?:seller|supplier|vendor|exporter|shipper|sold\s+by|from|issued\s+by|"
    r"vendedor|proveedor|exportador|emisor|remitente)\s*[:\-]\s*(.+)$", re.I
)
_PARTY_LABEL = re.compile(
    r"^\s*(?:buyer|importer|consignee|bill\s+to|sold\s+to|ship\s+to|customer|notify|"
    r"comprador|importador|consignatario|cliente)\b", re.I
)


def _supplier(lines: list[str]) -> str | None:
    # 1. An explicitly labelled supplier ("Seller: X", "Vendedor: X") wins, label removed.
    for line in lines[:15]:
        labelled = _SUPPLIER_LABEL.match(line)
        if labelled and labelled.group(1).strip(" |\t"):
            return labelled.group(1).strip(" |\t")[:160]
    # 2. Otherwise the first plausible line near the top (the letterhead), never a buyer line.
    ignored = re.compile(
        r"\b(invoice|factura|receipt|statement|tax invoice|bill to|ship to|date|"
        r"invoice number|invoice no|invoice #|page \d+)\b", re.I
    )
    for line in lines[:10]:
        if _PARTY_LABEL.match(line):
            continue
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
    # Prefer a plain tax line; fall back to "Total Tax"/"Total VAT" only when no
    # plain line exists. (The total label never matches "Total Tax".)
    tax = _label_amount(text, r"(?:sales\s+tax|tax|gst|vat|iva|impuestos|impuesto)") or _label_amount(
        text, r"(?:total\s+(?:tax|vat|gst|iva)|(?:tax|vat|gst)\s+total)"
    )
    discount = _label_amount(text, r"(?:less\s+discount|discount|descuento|rebate)")
    shipping = _label_amount(
        text, r"(?:shipping(?:\s+(?:and|&)\s+handling)?|freight|delivery(?:\s+charge)?|handling|env[ií]o|flete)"
    )
    # Insurance is not returned as a field yet, but it is part of the invoice sum
    # (e.g. CIF-style commercial invoices), so the arithmetic check includes it.
    insurance = _label_amount(text, r"(?:insurance|seguro)")
    total = _label_amount(
        text,
        r"(?:grand\s+total|total\s+due|amount\s+due|balance\s+due|invoice\s+total|total\s+a\s+pagar|importe\s+total|total)",
    )

    currency = None
    # Prefer an explicit code/symbol attached to a monetary amount over
    # incidental prose such as "Prices in USD" on a BZ$ invoice.
    amount_lines = [line for line in lines if _amounts_in_line(line)]
    amount_context = "\n".join(amount_lines)
    if re.search(r"\bBZ\$", amount_context, re.I):
        currency = "BZD"
    else:
        attached = re.search(
            r"(?<![A-Za-z])(" + "|".join(sorted(_CURRENCY_CODES)) + r")\s*(?=[(+-]?\d)",
            amount_context, re.I
        )
        if attached:
            currency = attached.group(1).upper()
        elif "€" in amount_context:
            currency = "EUR"
        elif "£" in amount_context:
            currency = "GBP"
        else:
            currency_match = re.search(r"\b(" + "|".join(sorted(_CURRENCY_CODES)) + r")\b", text, re.I)
            if currency_match:
                currency = currency_match.group(1).upper()
            elif "$" in amount_context:
                # A bare dollar sign does not identify which dollar currency.
                currency = None

    fields = {
        "supplier_name": supplier,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "currency": currency,
        "subtotal": subtotal,
        "tax": tax,
        "discount": discount,
        "shipping": shipping,
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

    review_fields = {name for name in ("supplier_name", "invoice_number", "invoice_date", "currency", "total")
                     if fields[name] is None}
    if subtotal is not None and total is not None:
        # Run the check even when no tax line was found (common on commercial
        # invoices: FOB + freight + insurance). A missing tax counts as zero, so an
        # unexplained difference is flagged for review rather than silently skipped.
        # Discounts are subtracted whether printed as "-100.00" or "100.00".
        expected = (Decimal(subtotal) - abs(Decimal(discount or "0"))
                    + Decimal(shipping or "0") + Decimal(insurance or "0") + Decimal(tax or "0"))
        if abs(expected - Decimal(total)) > Decimal("0.02"):
            warnings.append(
                "Subtotal plus tax (less discount, plus shipping and insurance) does not equal the extracted total; "
                "check discounts, shipping, fees, rounding, and the original invoice."
            )
            review_fields.update({"subtotal", "tax", "total"})

    document_type = "invoice"
    if re.search(r"\b(?:credit\s+(?:note|memo)|nota\s+de\s+cr[eé]dito)\b", text, re.I) or (
        total is not None and Decimal(total) < 0
    ):
        document_type = "credit_note"
        warnings.append("This looks like a credit note or refund; amounts may be negative. Verify before posting.")
        review_fields.add("total")

    # Confidence is intentionally unavailable until calibrated against a
    # representative, labelled invoice corpus. Do not fabricate a score.
    confidence = {key: None for key in fields}
    return {
        "fields": fields,
        "confidence": confidence,
        "confidence_type": "not_available_not_calibrated",
        "warnings": warnings,
        "review_required": True,
        # Fields that are missing, ambiguous or inconsistent. Every result still
        # needs human review; these need it most.
        "fields_needing_review": sorted(review_fields),
        "extraction_metadata": {
            "method": "rule_based_text_extraction",
            "document_type": document_type,
            "fields_found": sum(value is not None for value in fields.values()),
            "fields_expected": len(fields),
        },
    }
