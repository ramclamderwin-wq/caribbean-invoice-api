#!/usr/bin/env python3
"""Run a labelled invoice-extraction benchmark against a RAMVORA API.

Manifest CSV columns:
file,supplier_name,invoice_number,invoice_date,currency,subtotal,tax,total

Use one row per invoice. Leave a ground-truth cell blank when the field is
not present or cannot be established from the source invoice.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

FIELDS = (
    "supplier_name",
    "invoice_number",
    "invoice_date",
    "currency",
    "subtotal",
    "tax",
    "total",
)


def normalise(field: str, value: Any) -> str:
    if value is None:
        return ""
    value = str(value).strip()
    if not value:
        return ""
    if field in {"subtotal", "tax", "total"}:
        candidate = re.sub(r"[^0-9,().-]", "", value)
        negative = candidate.startswith("(") and candidate.endswith(")")
        candidate = candidate.strip("()")
        if "," in candidate and "." in candidate:
            if candidate.rfind(",") > candidate.rfind("."):
                candidate = candidate.replace(".", "").replace(",", ".")
            else:
                candidate = candidate.replace(",", "")
        elif "," in candidate:
            tail = candidate.rsplit(",", 1)[-1]
            candidate = candidate.replace(",", "." if len(tail) in (1, 2) else "")
        elif "." in candidate and len(candidate.rsplit(".", 1)[-1]) == 3:
            candidate = candidate.replace(".", "")
        try:
            number = Decimal(candidate)
            if negative:
                number = -abs(number)
            return str(number.quantize(Decimal("0.01")))
        except (InvalidOperation, ValueError):
            return value.casefold()
    if field == "currency":
        return value.upper().replace("$", "").strip()
    if field == "invoice_date":
        # Accept named-month dates and unambiguous numeric dates. Never guess
        # day/month ordering for values such as 01/02/2026.
        cleaned = value.replace(",", "").strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y",
                    "%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime(cleaned, fmt).date().isoformat()
            except ValueError:
                pass
        numeric = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", cleaned)
        if numeric:
            first, second, year = map(int, numeric.groups())
            if year < 100:
                year += 2000 if year < 70 else 1900
            if first > 12 >= second:
                day, month = first, second
            elif second > 12 >= first:
                month, day = first, second
            else:
                return ""
            try:
                return datetime(year, month, day).date().isoformat()
            except ValueError:
                return ""
        return ""
    return re.sub(r"\s+", " ", value).casefold()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("RAMVORA_BASE_URL") or os.getenv("QUILLVORA_BASE_URL"),
                        help="API base URL, e.g. https://api.example.com")
    parser.add_argument("--api-key", default=os.getenv("RAMVORA_API_KEY") or os.getenv("QUILLVORA_API_KEY"),
                        help="API key; prefer RAMVORA_API_KEY environment variable")
    parser.add_argument("--manifest", default="benchmark_manifest.csv")
    parser.add_argument("--output", default="benchmark_results.json")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    if not args.base_url or not args.api_key:
        parser.error("Set --base-url and --api-key (or RAMVORA_BASE_URL and RAMVORA_API_KEY).")

    manifest = Path(args.manifest)
    if not manifest.is_file():
        parser.error(f"Manifest not found: {manifest}")

    counts = defaultdict(lambda: {"correct": 0, "labelled": 0})
    rows = []
    with manifest.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"file", *FIELDS}
        missing = required - set(reader.fieldnames or [])
        if missing:
            parser.error("Manifest is missing columns: " + ", ".join(sorted(missing)))

        for row_number, record in enumerate(reader, start=2):
            file_path = (manifest.parent / record["file"]).resolve()
            result: dict[str, Any] = {
                "row": row_number,
                "file": record["file"],
                "status": "not_run",
                "fields": {},
            }
            started = time.perf_counter()
            try:
                if not file_path.is_file():
                    raise FileNotFoundError(f"Invoice file not found: {file_path}")
                with file_path.open("rb") as invoice:
                    response = requests.post(
                        args.base_url.rstrip("/") + "/v1/extract-file",
                        headers={"Authorization": f"Bearer {args.api_key}"},
                        files={"file": (file_path.name, invoice)},
                        timeout=args.timeout,
                    )
                result["http_status"] = response.status_code
                response.raise_for_status()
                payload = response.json()
                extracted = payload.get("fields")
                if not isinstance(extracted, dict):
                    raise ValueError(
                        "API response did not contain the expected object at 'fields'. "
                        "Check the staging API version and response schema."
                    )
                for field in FIELDS:
                    expected = normalise(field, record.get(field))
                    actual = normalise(field, extracted.get(field))
                    if expected:
                        counts[field]["labelled"] += 1
                        matched = expected == actual
                        if matched:
                            counts[field]["correct"] += 1
                        result["fields"][field] = {
                            "expected": record[field],
                            "actual": extracted.get(field),
                            "correct": matched,
                        }
                result["status"] = "success"
                result["review_required"] = payload.get("review_required")
                result["warnings"] = payload.get("warnings", [])
            except Exception as exc:
                result["status"] = "error"
                result["error"] = str(exc)
            result["duration_seconds"] = round(time.perf_counter() - started, 3)
            rows.append(result)
            print(f"[{result['status']}] {record['file']}")

    summary = {
        "invoice_count": len(rows),
        "successful": sum(item["status"] == "success" for item in rows),
        "errors": sum(item["status"] == "error" for item in rows),
        "field_accuracy": {
            field: {
                "correct": counts[field]["correct"],
                "labelled": counts[field]["labelled"],
                "accuracy_percent": round(
                    100 * counts[field]["correct"] / counts[field]["labelled"], 2
                ) if counts[field]["labelled"] else None,
            }
            for field in FIELDS
        },
        "results": rows,
        "limitations": [
            "This is exact-match field accuracy on the supplied labelled sample only.",
            "Blank ground-truth cells are excluded from that field's denominator.",
            "Review-required rate and processing time are descriptive, not accuracy measures.",
            "Do not use this report to make public accuracy claims unless the dataset is representative and permissioned.",
        ],
    }
    output = Path(args.output)
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
    print(f"Full report: {output}")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
