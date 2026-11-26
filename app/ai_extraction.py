"""AI document extraction engine: DISABLED BY DEFAULT.

Turns a commercial invoice (PDF or image) into ``commercial_invoice.v1`` using a
Claude document/vision model, then applies the same validation as the rule engine.

It is switched off. It refuses to run unless **all** of the following hold:

1. ``RAMVORA_AI_ENABLED=true`` is set (owner authorisation to use a paid AI API);
2. the caller passes ``data_sharing_confirmed=True`` (the document owner allowed
   sending the file to the AI provider);
3. Anthropic API credentials are available to the SDK (only checked when a call is made).

Tests inject a fake client, so no network call or cost happens in CI.
"""
from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from app.commercial_invoice import SCHEMA_VERSION, validate_commercial_invoice

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"

# USD per million tokens (input, output), Anthropic list prices at the time of writing.
# Verify current pricing before relying on cost figures.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}

MEDIA_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
               ".jpeg": "image/jpeg", ".webp": "image/webp"}

_S = {"type": ["string", "null"]}
_PARTY = {"type": ["object", "null"], "properties": {"name": _S, "address": _S, "tax_id": _S},
          "required": ["name", "address", "tax_id"], "additionalProperties": False}
_LINE_FIELDS = ("description", "sku", "hs_code_as_printed", "quantity", "unit_of_measure",
                "unit_price", "line_total", "currency", "country_of_origin")
AI_SCHEMA = {
    "type": "object",
    "properties": {
        "seller": _PARTY, "buyer": _PARTY,
        "invoice_number": _S, "invoice_date": _S, "currency": _S, "incoterm": _S, "incoterm_place": _S,
        "country_of_origin": _S, "subtotal": _S, "discount": _S, "freight": _S, "insurance": _S,
        "tax": _S, "total": _S,
        "line_items": {"type": "array", "items": {
            "type": "object", "properties": {k: _S for k in _LINE_FIELDS},
            "required": list(_LINE_FIELDS), "additionalProperties": False}},
        "unreadable_or_uncertain": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["seller", "buyer", "invoice_number", "invoice_date", "currency", "incoterm", "incoterm_place",
                 "country_of_origin", "subtotal", "discount", "freight", "insurance", "tax", "total",
                 "line_items", "unreadable_or_uncertain"],
    "additionalProperties": False,
}
AI_INSTRUCTIONS = """Extract the commercial invoice in the attached document into the JSON schema.

Rules:
- Copy only values printed on the document. If a value is not printed, use null. Never guess.
- Do not infer or suggest tariff/HS codes. Fill hs_code_as_printed only if the invoice prints one for that line.
- country_of_origin only when explicitly printed (header or line).
- Amounts: plain decimals with a dot separator and no thousands separators or currency symbols, e.g. "1625.00".
  Negative amounts (credits) with a leading minus.
- quantity: the printed number only, e.g. "50" or "2.5"; unit_of_measure separately, e.g. "pcs", "kg".
- invoice_date: ISO YYYY-MM-DD only when day and month are unambiguous; otherwise null and add
  "invoice_date" to unreadable_or_uncertain.
- currency: ISO 4217 code only if printed or unambiguous from a symbol (e.g. "€" is EUR); a bare "$" alone is
  ambiguous: use null and list "currency" as uncertain.
- List one line item per invoice row in printed order. Do not merge or split rows.
- Put any field you could not read confidently in unreadable_or_uncertain (e.g. "line_items[3].quantity")."""


class AIEngineDisabled(RuntimeError):
    """Raised when the AI engine is used without authorisation."""


def ai_enabled() -> bool:
    # QUILLVORA_AI_ENABLED is the pre-rebrand name, still honoured so existing
    # configuration keeps working.
    value = os.getenv("RAMVORA_AI_ENABLED") or os.getenv("QUILLVORA_AI_ENABLED") or ""
    return value.strip().lower() == "true"


@dataclass
class AIExtraction:
    result: dict[str, Any] | None
    seconds: float
    cost_usd: float = 0.0
    model: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    error: str | None = None


class ClaudeExtractionEngine:
    name = "ai"

    def __init__(self, model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT, client: Any = None):
        self.model, self.effort = model, effort
        self._client = client

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not ai_enabled():
            raise AIEngineDisabled(
                "The AI extraction engine is disabled. The owner must authorise paid AI use "
                "(set RAMVORA_AI_ENABLED=true) before it can run."
            )
        import anthropic
        self._client = anthropic.Anthropic()
        return self._client

    def extract(self, data: bytes, suffix: str, *, data_sharing_confirmed: bool) -> AIExtraction:
        if not data_sharing_confirmed:
            raise AIEngineDisabled("Document owner permission to send this file to the AI provider is not confirmed.")
        media = MEDIA_TYPES.get(suffix.lower())
        if media is None:
            return AIExtraction(None, 0.0, error=f"unsupported file type for AI engine: {suffix}")
        client = self._client_or_raise()
        block_type = "document" if media == "application/pdf" else "image"
        content = [{"type": block_type, "source": {"type": "base64", "media_type": media,
                                                   "data": base64.standard_b64encode(data).decode("ascii")}},
                   {"type": "text", "text": AI_INSTRUCTIONS}]
        started = time.monotonic()
        try:
            response = client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": AI_SCHEMA}},
                messages=[{"role": "user", "content": content}],
            )
        except Exception as exc:  # recorded per document; callers continue with the next file
            return AIExtraction(None, time.monotonic() - started, error=f"{type(exc).__name__}: {exc}")
        seconds = time.monotonic() - started
        usage = {"input_tokens": int(getattr(response.usage, "input_tokens", 0) or 0),
                 "output_tokens": int(getattr(response.usage, "output_tokens", 0) or 0)}
        served = getattr(response, "model", None) or self.model
        price_in, price_out = PRICES.get(served, PRICES.get(self.model, (0.0, 0.0)))
        cost = usage["input_tokens"] / 1e6 * price_in + usage["output_tokens"] / 1e6 * price_out
        if response.stop_reason == "refusal":
            return AIExtraction(None, seconds, cost, served, usage, "refused")
        if response.stop_reason == "max_tokens":
            return AIExtraction(None, seconds, cost, served, usage, "truncated (max_tokens)")
        text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), "")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            return AIExtraction(None, seconds, cost, served, usage, "invalid JSON")
        uncertain = raw.pop("unreadable_or_uncertain", []) or []
        result = validate_commercial_invoice({**raw, "schema_version": SCHEMA_VERSION}, extra_uncertain=uncertain)
        result["extraction_metadata"] = {"engine": "ai", "model": served, "method": "document_model"}
        return AIExtraction(result, seconds, cost, served, usage)
