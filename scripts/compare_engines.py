#!/usr/bin/env python3
"""Compare extraction engines on labelled commercial invoices.

Engines (both emit the ``commercial_invoice.v1`` structure):
  rules   current OCR + rule-based extractor (local; no per-page fee)
  claude  Claude document/vision model with a strict JSON schema (API cost per call)

Manifest (JSON), one entry per invoice; leave a field out or null when it is not
printed on the invoice. See benchmarks/commercial_manifest.template.json.

    {"documents": [{"file": "inv-001.pdf", "pages": 1, "segment": "broker-A",
                    "expected": {"seller_name": "...", "invoice_number": "...", "invoice_date": "2026-04-12",
                                 "currency": "USD", "subtotal": "...", "tax": null, "total": "...",
                                 "line_items": [{"description": "...", "quantity": "50",
                                                 "unit_price": "32.50", "line_total": "1625.00"}]},
                    "correction_seconds": {"rules": 140, "claude": 35}}]}

Examples:
    python scripts/compare_engines.py --manifest private/manifest.json --engines rules
    python scripts/compare_engines.py --manifest private/manifest.json --engines rules,claude \\
        --confirm-data-sharing          # documents are sent to the Anthropic API

Honesty rules: results on fewer than 50 permissioned real invoices are reported as
"insufficient sample", and synthetic documents never support an accuracy claim.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_invoices import normalise  # noqa: E402

HEADER_FIELDS = ("seller_name", "buyer_name", "invoice_number", "invoice_date", "currency",
                 "incoterm", "subtotal", "tax", "total")
KEY_FIELDS = ("seller_name", "invoice_number", "invoice_date", "total")
LINE_FIELDS = ("description", "sku", "quantity", "unit_of_measure", "unit_price", "line_total", "country_of_origin")
MONEY = {"subtotal", "tax", "total", "unit_price", "line_total"}
MIN_SAMPLE_FOR_CLAIM = 50
DEFAULT_SECONDS_PER_FIX = 15  # assumption for the estimate; replace with measured pilot timings

from app.ai_extraction import AI_SCHEMA, PRICES, ClaudeExtractionEngine, ai_enabled  # noqa: E402,F401


@dataclass
class EngineResult:
    output: dict[str, Any] | None
    seconds: float
    cost_usd: float = 0.0
    error: str | None = None
    usage: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------
def rules_engine(path: Path) -> EngineResult:
    from fastapi import HTTPException
    from app.commercial_invoice import extract_commercial_invoice
    from app.main import _process_file

    started = time.monotonic()
    try:
        text, _ocr, _pages, _kind = _process_file(path.read_bytes(), path.suffix.lower(), path.name)
        output = extract_commercial_invoice(text)
        return EngineResult(output, time.monotonic() - started)
    except HTTPException as exc:
        return EngineResult(None, time.monotonic() - started, error=f"HTTP {exc.status_code}: {exc.detail}")


class ClaudeEngine:
    """Benchmark wrapper around app.ai_extraction.ClaudeExtractionEngine.

    The CLI only builds this after --confirm-data-sharing and RAMVORA_AI_ENABLED=true.
    """

    def __init__(self, model: str = "claude-opus-5-5", effort: str = "medium", client: Any = None):
        self.engine = ClaudeExtractionEngine(model, effort, client)

    def __call__(self, path: Path) -> EngineResult:
        r = self.engine.extract(path.read_bytes(), path.suffix, data_sharing_confirmed=True)
        return EngineResult(r.result, r.seconds, r.cost_usd, r.error, r.usage)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def _flatten(output: dict[str, Any]) -> dict[str, Any]:
    flat = dict(output)
    flat["seller_name"] = (output.get("seller") or {}).get("name")
    flat["buyer_name"] = (output.get("buyer") or {}).get("name")
    return flat


def _norm(field_name: str, value: Any) -> str:
    if value is None or str(value).strip() == "":
        return ""
    if field_name in MONEY:
        return normalise("total", value)
    if field_name == "invoice_date":
        return normalise("invoice_date", value)
    if field_name == "currency":
        return normalise("currency", value)
    if field_name == "quantity":
        try:
            return format(Decimal(str(value).replace(",", "")).normalize(), "f")
        except (InvalidOperation, ValueError):
            return str(value).strip().casefold()
    return " ".join(str(value).replace(",", " ").split()).casefold().strip(" .")


def _similar(a: Any, b: Any) -> float:
    return SequenceMatcher(None, _norm("description", a), _norm("description", b)).ratio()


def match_lines(expected: list[dict], predicted: list[dict]) -> list[tuple[int, int]]:
    """Greedy best-description matching (similarity >= 0.6), in order of confidence."""
    pairs = sorted(((_similar(e.get("description"), p.get("description")), i, j)
                    for i, e in enumerate(expected) for j, p in enumerate(predicted)), reverse=True)
    used_e, used_p, matches = set(), set(), []
    for score, i, j in pairs:
        if score < 0.6 or i in used_e or j in used_p:
            continue
        used_e.add(i); used_p.add(j); matches.append((i, j))
    return sorted(matches)


def score_document(expected: dict[str, Any], output: dict[str, Any] | None,
                   seconds_per_fix: float = DEFAULT_SECONDS_PER_FIX) -> dict[str, Any]:
    flat = _flatten(output or {})
    header = {}
    for name in HEADER_FIELDS:
        if name not in expected:
            continue  # not labelled
        want, got = _norm(name, expected[name]), _norm(name, flat.get(name))
        header[name] = {"correct": want == got, "expected": expected[name], "got": flat.get(name)}

    exp_lines = expected.get("line_items") or []
    got_lines = (output or {}).get("line_items") or []
    matches = match_lines(exp_lines, got_lines)
    line_fields: dict[str, dict[str, int]] = {f: {"correct": 0, "labelled": 0} for f in LINE_FIELDS}
    fixes = sum(1 for result in header.values() if not result["correct"])
    exact_lines = 0
    for i, j in matches:
        all_ok = True
        for name in LINE_FIELDS:
            if exp_lines[i].get(name) is None:
                continue
            line_fields[name]["labelled"] += 1
            ok = (_similar(exp_lines[i][name], got_lines[j].get(name)) >= 0.85 if name == "description"
                  else _norm(name, exp_lines[i][name]) == _norm(name, got_lines[j].get(name)))
            line_fields[name]["correct"] += ok
            fixes += not ok
            all_ok &= ok
        exact_lines += all_ok
    missed = len(exp_lines) - len(matches)
    extra = len(got_lines) - len(matches)
    fixes += missed * 4 + extra  # re-keying a missed row ~4 fields; deleting an extra row ~1 action
    keys = [header[k]["correct"] for k in KEY_FIELDS if k in header]
    return {
        "header": header,
        "key_fields_all_correct": bool(keys) and all(keys),
        "lines": {"expected": len(exp_lines), "predicted": len(got_lines), "matched": len(matches),
                  "exact": exact_lines, "fields": line_fields},
        "estimated_fixes": fixes,
        "estimated_correction_seconds": fixes * seconds_per_fix,
    }


def summarise(docs: list[dict[str, Any]], engine: str) -> dict[str, Any]:
    rows = [d["engines"][engine] for d in docs if engine in d["engines"]]
    n = len(rows)
    header_acc = {}
    for name in HEADER_FIELDS:
        vals = [r["score"]["header"][name]["correct"] for r in rows if name in r["score"]["header"]]
        if vals:
            header_acc[name] = {"accuracy": sum(vals) / len(vals), "labelled": len(vals)}
    line_totals = {f: {"correct": 0, "labelled": 0} for f in LINE_FIELDS}
    exp = pred = matched = exact = 0
    for r in rows:
        lines = r["score"]["lines"]
        exp += lines["expected"]; pred += lines["predicted"]; matched += lines["matched"]; exact += lines["exact"]
        for f in LINE_FIELDS:
            line_totals[f]["correct"] += lines["fields"][f]["correct"]
            line_totals[f]["labelled"] += lines["fields"][f]["labelled"]
    pages = sum(r["pages"] for r in rows) or 1
    measured = [r["measured_correction_seconds"] for r in rows if r.get("measured_correction_seconds") is not None]
    key_ok = sum(r["score"]["key_fields_all_correct"] for r in rows)
    return {
        "documents": n,
        "errors": sum(1 for r in rows if r["error"]),
        "header_accuracy": header_acc,
        "key_fields_all_correct_rate": key_ok / n if n else None,
        "line_item_recall": matched / exp if exp else None,
        "line_item_precision": matched / pred if pred else None,
        "line_item_exact_rate": exact / exp if exp else None,
        "line_field_accuracy": {f: (v["correct"] / v["labelled"] if v["labelled"] else None)
                                for f, v in line_totals.items()},
        "seconds_per_document": sum(r["seconds"] for r in rows) / n if n else None,
        "cost_usd_total": round(sum(r["cost_usd"] for r in rows), 4),
        "cost_usd_per_page": round(sum(r["cost_usd"] for r in rows) / pages, 5),
        "estimated_correction_seconds_per_document":
            sum(r["score"]["estimated_correction_seconds"] for r in rows) / n if n else None,
        "measured_correction_seconds_per_document": sum(measured) / len(measured) if measured else None,
        "sample_status": "ok" if n >= MIN_SAMPLE_FOR_CLAIM else
                         f"insufficient sample (<{MIN_SAMPLE_FOR_CLAIM}): do not quote accuracy",
    }


def run(manifest_path: Path, engines: dict[str, Callable[[Path], EngineResult]],
        seconds_per_fix: float = DEFAULT_SECONDS_PER_FIX) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    docs = []
    for entry in manifest["documents"]:
        path = (base / entry["file"]).resolve()
        doc = {"file": entry["file"], "segment": entry.get("segment"), "engines": {}}
        for name, engine in engines.items():
            if not path.is_file():
                result = EngineResult(None, 0.0, error="file not found")
            else:
                result = engine(path)
            doc["engines"][name] = {
                "error": result.error, "seconds": round(result.seconds, 3), "cost_usd": result.cost_usd,
                "usage": result.usage, "pages": int(entry.get("pages") or 1),
                "score": score_document(entry["expected"], result.output, seconds_per_fix),
                "measured_correction_seconds": (entry.get("correction_seconds") or {}).get(name),
                "output": result.output,
            }
        docs.append(doc)
    return {"documents": docs, "summary": {name: summarise(docs, name) for name in engines}}


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def markdown_report(results: dict[str, Any]) -> str:
    engines = list(results["summary"])
    lines = ["# Extraction engine comparison", "",
             "| Metric | " + " | ".join(engines) + " |", "|---|" + "---|" * len(engines)]
    def row(label: str, getter: Callable[[dict], str]) -> None:
        lines.append(f"| {label} | " + " | ".join(getter(results["summary"][e]) for e in engines) + " |")
    row("Documents", lambda s: str(s["documents"]))
    row("Sample status", lambda s: s["sample_status"])
    for name in HEADER_FIELDS:
        row(f"{name} accuracy", lambda s, n=name: _pct(s["header_accuracy"].get(n, {}).get("accuracy")))
    row("Key fields all correct (supplier, number, date, total)", lambda s: _pct(s["key_fields_all_correct_rate"]))
    row("Line-item recall", lambda s: _pct(s["line_item_recall"]))
    row("Line-item precision", lambda s: _pct(s["line_item_precision"]))
    row("Line items fully correct", lambda s: _pct(s["line_item_exact_rate"]))
    for name in LINE_FIELDS:
        row(f"line {name} accuracy", lambda s, n=name: _pct(s["line_field_accuracy"][n]))
    row("Seconds per document", lambda s: "n/a" if s["seconds_per_document"] is None else f"{s['seconds_per_document']:.2f}")
    row("Cost per page (USD, model fees only)", lambda s: f"{s['cost_usd_per_page']:.4f}")
    row("Est. correction seconds/doc (assumption-based)",
        lambda s: "n/a" if s["estimated_correction_seconds_per_document"] is None else f"{s['estimated_correction_seconds_per_document']:.0f}")
    row("Measured correction seconds/doc (pilot)",
        lambda s: "n/a" if s["measured_correction_seconds_per_document"] is None else f"{s['measured_correction_seconds_per_document']:.0f}")
    lines += ["", "Correction-time estimates assume a fixed number of seconds per fix; use measured pilot timings for decisions.",
              "Accuracy is exact match after normalisation over labelled fields only. Do not quote results below the sample threshold."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--engines", default="rules", help="comma list: rules,claude")
    parser.add_argument("--model", default="claude-opus-5-5", help="Claude model for the AI engine")
    parser.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--seconds-per-fix", type=float, default=DEFAULT_SECONDS_PER_FIX)
    parser.add_argument("--confirm-data-sharing", action="store_true",
                        help="required for AI engines: confirms you have permission to send these documents to the provider")
    parser.add_argument("--output", default="engine_comparison.json")
    parser.add_argument("--report", default="engine_comparison.md")
    args = parser.parse_args(argv)

    engines: dict[str, Callable[[Path], EngineResult]] = {}
    for name in [e.strip() for e in args.engines.split(",") if e.strip()]:
        if name == "rules":
            engines["rules"] = rules_engine
        elif name == "claude":
            if not args.confirm_data_sharing:
                parser.error("The claude engine sends documents to the Anthropic API. Re-run with "
                             "--confirm-data-sharing only if every document owner has given permission.")
            if not ai_enabled():
                parser.error("The AI engine is disabled. Set RAMVORA_AI_ENABLED=true only after the owner "
                             "authorises paid AI usage.")
            engines["claude"] = ClaudeEngine(args.model, args.effort)
        else:
            parser.error(f"Unknown engine: {name}")
    results = run(Path(args.manifest), engines, args.seconds_per_fix)
    Path(args.output).write_text(json.dumps(results, indent=2, default=str))
    Path(args.report).write_text(markdown_report(results))
    print(markdown_report(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
