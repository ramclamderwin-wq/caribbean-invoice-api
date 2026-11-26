"""Evaluate RAMVORA on licence-checked PUBLIC invoice/receipt datasets (no customer data).

Runs the same extraction pipeline the API uses (``app.main._process_file`` + the rule
engines) in-process, so no staging page allowance is consumed.

    python -m scripts.eval_public --data /path/to/ramvora-public-invoices --out results.md

Supported label formats (folders created by the owner's licence-checked download):
- ``cord-v2_*``   CORD v2 receipts (CC BY 4.0): total, subtotal, tax; amounts in IDR where
                  "." is a thousands separator (60.000 = sixty thousand).
- ``*katana*``    Katana/Mendeley synthetic invoices (MIT / CC BY 4.0): invoice number, date,
                  seller, totals (comma decimals), line items.
- ``fatura_*``    FATURA (CC BY 4.0): word-level tags only. Run but NOT scored here, because
                  rebuilding answers from token tags would mean guessing the labels.

The datasets themselves are never committed. Keep their LICENCES_AND_SOURCES.md with them.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.commercial_invoice import extract_commercial_invoice
from app.extraction import extract_invoice_fields


def _num(value: str | None, *, thousands_dot: bool = False, comma_decimal: bool = False) -> Decimal | None:
    if value in (None, ""):
        return None
    text = re.sub(r"[^\d,.\-]", "", str(value))
    if thousands_dot:  # IDR receipts: both "." and "," are thousands separators
        text = text.replace(".", "").replace(",", "")
    elif comma_decimal:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _same(a: Decimal | None, b: Decimal | None) -> bool:
    return a is not None and b is not None and abs(a - b) <= Decimal("0.01")


def _iso(us_date: str) -> str | None:
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", us_date or "")
    return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else None


def _gt(label_path: Path) -> dict:
    data = json.loads(label_path.read_text(encoding="utf-8"))
    gt = data.get("ground_truth", data)
    if isinstance(gt, str):
        gt = json.loads(gt)
    return gt.get("gt_parse", gt)


def _extract(image: Path):
    from app.main import _process_file
    start = time.perf_counter()
    text, ocr, pages, _ = _process_file(image.read_bytes(), image.suffix.lower(), image.name)
    header = extract_invoice_fields(text)
    ci = extract_commercial_invoice(text)
    return header, ci, time.perf_counter() - start


def score_cord(folder: Path, limit: int | None):
    rows = []
    for label in sorted(folder.glob("*.json"))[:limit]:
        image = label.with_suffix(".jpg")
        gt = _gt(label)
        header, ci, secs = _extract(image)
        f = header["fields"]
        total_t = _num((gt.get("total") or {}).get("total_price"), thousands_dot=True)
        sub_t = _num((gt.get("sub_total") or {}).get("subtotal_price"), thousands_dot=True)
        menu = gt.get("menu") or []
        menu = menu if isinstance(menu, list) else [menu]
        rows.append({
            "doc": label.stem, "secs": secs,
            "total": (_same(_num(f["total"]), total_t), total_t, f["total"]),
            "subtotal": (_same(_num(f["subtotal"]), sub_t), sub_t, f["subtotal"]) if sub_t is not None else None,
            "items_truth": len(menu), "items_found": len(ci["line_items"]),
            "flagged": bool(header["warnings"] or header["fields_needing_review"]),
        })
    return rows


def score_katana(folder: Path, limit: int | None):
    rows = []
    for label in sorted(folder.glob("*.json"))[:limit]:
        image = label.with_suffix(".jpg")
        gt = _gt(label)
        h, s = gt.get("header", {}), gt.get("summary", {})
        header, ci, secs = _extract(image)
        f = header["fields"]
        seller_truth = (h.get("seller") or "").lower()
        supplier = (f["supplier_name"] or "").lower()
        truth_totals = [_num(it.get(k), comma_decimal=True) for it in gt.get("items", [])
                        for k in ("item_net_worth", "item_gross_worth")]
        matched_items = sum(1 for row in ci["line_items"] if any(_same(_num(row.get("line_total")), t) for t in truth_totals))
        rows.append({
            "doc": label.stem, "secs": secs,
            "invoice_number": (f["invoice_number"] == h.get("invoice_no"), h.get("invoice_no"), f["invoice_number"]),
            "invoice_date": (f["invoice_date"] == _iso(h.get("invoice_date", "")), _iso(h.get("invoice_date", "")), f["invoice_date"]),
            "supplier": (bool(supplier) and len(supplier) >= 3 and seller_truth.startswith(supplier[:12]), h.get("seller", "")[:30], f["supplier_name"]),
            "total": (_same(_num(f["total"]), _num(s.get("total_gross_worth"), comma_decimal=True)), s.get("total_gross_worth"), f["total"]),
            "subtotal": (_same(_num(f["subtotal"]), _num(s.get("total_net_worth"), comma_decimal=True)), s.get("total_net_worth"), f["subtotal"]),
            "tax": (_same(_num(f["tax"]), _num(s.get("total_vat"), comma_decimal=True)), s.get("total_vat"), f["tax"]),
            "items_truth": len(gt.get("items", [])), "items_found": len(ci["line_items"]), "items_matched": matched_items,
            "flagged": bool(header["warnings"] or header["fields_needing_review"]),
        })
    return rows


def run_fatura(folder: Path, limit: int | None):
    out = []
    for image in sorted(folder.glob("*.jpg"))[:limit]:
        header, ci, secs = _extract(image)
        f = header["fields"]
        out.append({"doc": image.stem, "secs": secs, "found": {k: f[k] for k in ("invoice_number", "invoice_date", "currency", "total")},
                    "items_found": len(ci["line_items"]), "flagged": bool(header["warnings"] or header["fields_needing_review"])})
    return out


def report(results: dict) -> str:
    lines = ["# Public dataset evaluation (licence-checked, no customer data)", "",
             "Same extraction code as the API (in-process). All inputs are **images** (OCR path).", ""]
    for name, rows in results.items():
        if not rows:
            continue
        lines += [f"## {name} ({len(rows)} documents)", ""]
        if name.startswith("FATURA"):
            found_total = sum(1 for r in rows if r["found"]["total"])
            lines += [f"- Not scored (no ready-made labels). A total was found on {found_total}/{len(rows)}; "
                      f"flagged for review: {sum(r['flagged'] for r in rows)}/{len(rows)}.", ""]
            continue
        fields = [k for k in rows[0] if isinstance(rows[0][k], tuple) or rows[0][k] is None]
        fields = [k for k in ("invoice_number", "invoice_date", "supplier", "subtotal", "tax", "total") if k in rows[0]]
        lines += ["| Field | Correct | Wrong, flagged for review | Wrong, not flagged |", "|---|---|---|---|"]
        for k in fields:
            scored = [r for r in rows if r.get(k) is not None]
            ok = sum(1 for r in scored if r[k][0])
            wf = sum(1 for r in scored if not r[k][0] and r["flagged"])
            wn = sum(1 for r in scored if not r[k][0] and not r["flagged"])
            lines.append(f"| {k} | {ok}/{len(scored)} ({100 * ok / max(1, len(scored)):.0f}%) | {wf} | {wn} |")
        if "items_matched" in rows[0]:
            t = sum(r["items_truth"] for r in rows); m = sum(r["items_matched"] for r in rows); f_ = sum(r["items_found"] for r in rows)
            lines += ["", f"Line items: {t} in labels, {f_} returned, {m} matched by line total."]
        else:
            lines += ["", f"Line items: {sum(r['items_truth'] for r in rows)} in labels, {sum(r['items_found'] for r in rows)} returned (receipt rows are not matched individually)."]
        med = sorted(r["secs"] for r in rows)[len(rows) // 2]
        lines += [f"Median time per document: {med:.1f} s", "", "Misses (first 12):", "",
                  "| Document | Field | Expected | Got |", "|---|---|---|---|"]
        n = 0
        for r in rows:
            for k in fields:
                if r.get(k) is not None and not r[k][0] and n < 12:
                    lines.append(f"| {r['doc']} | {k} | {r[k][1]} | {r[k][2]} |"); n += 1
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    root = Path(args.data)
    results = {}
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if folder.name.startswith("cord"):
            results["CORD v2 receipts (real, Indonesia, IDR)"] = score_cord(folder, args.limit)
        elif "katana" in folder.name:
            results["Katana invoices (synthetic, US-style)"] = score_katana(folder, args.limit)
        elif folder.name.startswith("fatura"):
            results["FATURA invoices (synthetic, 50 templates)"] = run_fatura(folder, args.limit)
    text = report(results)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
