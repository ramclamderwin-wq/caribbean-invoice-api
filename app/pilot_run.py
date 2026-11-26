"""One-command concierge pilot tool.

    python -m app.pilot_run --customer "Acme Brokers" --input ./incoming/acme --output ./pilot_runs

For each invoice in --input (PDF, PNG, JPG, JPEG, TIFF, BMP, WEBP) it extracts a
``commercial_invoice.v1`` result and writes, under
``<output>/<customer-slug>/<UTC timestamp>/``:

- ``invoices.csv`` and ``line_items.csv``: the customer spreadsheet (Excel-ready);
- ``results.json``: full results, including every issue;
- ``run_log.csv``: per-file status, engine, pages, seconds, cost, flags;
- ``REVIEW_CHECKLIST.md``: what the reviewer must check before sending the files back.

Engines: ``rules`` (default; local, no cost) or ``ai``. The AI engine stays disabled unless
RAMVORA_AI_ENABLED=true **and** --confirm-data-sharing is given (document-owner permission).
Input files are never modified, moved or deleted.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.pilot_export import write_pilot_csvs

SUPPORTED = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
MAX_FILE_BYTES = 15 * 1024 * 1024


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "customer"


def _rules_extract(data: bytes, suffix: str, name: str) -> tuple[dict[str, Any], int]:
    from fastapi import HTTPException
    from app.commercial_invoice import extract_commercial_invoice
    from app.main import _process_file
    try:
        text, _ocr_used, pages, _kind = _process_file(data, suffix, name)
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from exc
    if not text.strip():
        raise ValueError("No readable text found (try a clearer scan).")
    result = extract_commercial_invoice(text)
    return result, pages


def process_folder(input_dir: str | Path, output_dir: str | Path, customer: str, *, engine: str = "rules",
                   confirm_data_sharing: bool = False, ai_engine: Any = None,
                   timestamped: bool = True) -> Path:
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    if not input_dir.is_dir():
        raise SystemExit(f"Input folder not found: {input_dir}")
    if engine == "ai":
        from app.ai_extraction import AIEngineDisabled, ClaudeExtractionEngine, ai_enabled
        if not confirm_data_sharing:
            raise SystemExit("The AI engine needs --confirm-data-sharing (document-owner permission).")
        if ai_engine is None and not ai_enabled():
            raise SystemExit("The AI engine is disabled. The owner must authorise it (RAMVORA_AI_ENABLED=true).")
        ai_engine = ai_engine or ClaudeExtractionEngine()
    elif engine != "rules":
        raise SystemExit(f"Unknown engine: {engine}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / _slug(customer) / (stamp if timestamped else "latest")
    run_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in input_dir.iterdir() if p.is_file() and not p.name.startswith("."))
    results: dict[str, dict[str, Any]] = {}
    log: list[dict[str, Any]] = []
    for path in files:
        row: dict[str, Any] = {"file": path.name, "engine": engine, "status": "ok", "error": "",
                               "pages": "", "seconds": "", "cost_usd": 0.0, "line_items": 0,
                               "fields_needing_review": "", "issues": 0}
        suffix = path.suffix.lower()
        started = time.monotonic()
        try:
            if suffix not in SUPPORTED:
                raise ValueError(f"unsupported file type {suffix}")
            data = path.read_bytes()
            if len(data) > MAX_FILE_BYTES:
                raise ValueError("file larger than 15 MB")
            if engine == "rules":
                result, pages = _rules_extract(data, suffix, path.name)
                row["pages"] = pages
            else:
                out = ai_engine.extract(data, suffix, data_sharing_confirmed=True)
                row["cost_usd"] = round(out.cost_usd, 5)
                if out.error:
                    raise ValueError(out.error)
                result = out.result
            results[path.name] = result
            row["line_items"] = len(result.get("line_items") or [])
            row["fields_needing_review"] = "; ".join(result.get("fields_needing_review") or [])
            row["issues"] = len(result.get("issues") or [])
            if row["fields_needing_review"]:
                row["status"] = "needs_review"
        except Exception as exc:  # one bad file never stops the batch
            row["status"], row["error"] = "error", str(exc)[:300]
        row["seconds"] = round(time.monotonic() - started, 3)
        log.append(row)

    write_pilot_csvs(results, run_dir)
    (run_dir / "results.json").write_text(json.dumps(
        {"customer": customer, "engine": engine, "generated_at": stamp, "results": results}, indent=2, ensure_ascii=False))
    with (run_dir / "run_log.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(log[0].keys()) if log else ["file"])
        writer.writeheader()
        writer.writerows(log)
    _write_checklist(run_dir, customer, engine, log, results)
    return run_dir


def _write_checklist(run_dir: Path, customer: str, engine: str, log: list[dict[str, Any]],
                     results: dict[str, dict[str, Any]]) -> None:
    ok = sum(1 for r in log if r["status"] == "ok")
    review = [r for r in log if r["status"] == "needs_review"]
    errors = [r for r in log if r["status"] == "error"]
    cost = sum(float(r["cost_usd"] or 0) for r in log)
    lines = [
        f"# Review checklist: {customer}", "",
        f"Engine: `{engine}`. Files: {len(log)} (clean {ok}, needs review {len(review)}, errors {len(errors)}). "
        f"Model cost: US${cost:.4f}.", "",
        "**Nothing goes to the customer until every box below is ticked.**", "",
        "## Every invoice", "",
        "- [ ] Compare each row in `invoices.csv` with the original (number, date, parties, currency, totals).",
        "- [ ] Compare each line in `line_items.csv` with the original (description, quantity, unit, price, total).",
        "- [ ] Blank cells mean 'not printed on the invoice'. Do not fill them from memory or guesses.",
        "- [ ] `hs_code_as_printed` only if the invoice prints it. Never add tariff codes.",
        "- [ ] Record each correction and the minutes spent in the pilot error log.",
        "- [ ] Set `review_status` to `ramvora_checked` and `reviewed_by` to your name.", "",
    ]
    if review:
        lines += ["## Flagged for review", ""]
        for r in review:
            issues = results.get(r["file"], {}).get("issues") or []
            lines.append(f"- [ ] **{r['file']}**: {r['fields_needing_review']}")
            lines += [f"    - {i.get('message')}" for i in issues[:6]]
        lines.append("")
    if errors:
        lines += ["## Could not be processed (handle manually or ask for a better copy)", ""]
        lines += [f"- [ ] **{r['file']}**: {r['error']}" for r in errors]
        lines.append("")
    (run_dir / "REVIEW_CHECKLIST.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.pilot_run", description=__doc__.split("\n")[0])
    parser.add_argument("--customer", required=True, help="Customer name (used for the output folder)")
    parser.add_argument("--input", required=True, help="Folder containing the customer's invoices")
    parser.add_argument("--output", default="pilot_runs", help="Where to write results (keep out of Git)")
    parser.add_argument("--engine", choices=["rules", "ai"], default="rules")
    parser.add_argument("--confirm-data-sharing", action="store_true",
                        help="AI engine only: the document owner allowed sending files to the AI provider")
    parser.add_argument("--no-timestamp", action="store_true", help="Write to a fixed 'latest' folder")
    args = parser.parse_args(argv)
    run_dir = process_folder(args.input, args.output, args.customer, engine=args.engine,
                             confirm_data_sharing=args.confirm_data_sharing, timestamped=not args.no_timestamp)
    print(f"Done. Results in {run_dir}")
    print((run_dir / "REVIEW_CHECKLIST.md").read_text(encoding="utf-8").split("\n\n")[1])
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
