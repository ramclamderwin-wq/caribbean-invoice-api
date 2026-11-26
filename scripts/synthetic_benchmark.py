"""Synthetic invoice accuracy benchmark (no real customer data).

Generates varied synthetic invoices with known ground truth, runs the rule-based
engines in-process, and reports field-level accuracy, line-item precision/recall
and how well the review flags catch errors.

    python -m scripts.synthetic_benchmark --count 60 --seed 7 --out benchmarks/synthetic_results.md

What it covers: label wording (English/Spanish), date formats, currencies and
symbols, comma-decimal amounts, 1-8 line items, optional discount/freight/insurance/
tax, text PDFs and rasterised (OCR) images with mild noise and rotation.

What it does NOT prove: accuracy on real invoices. Synthetic layouts are simpler
than real supplier documents (no logos, merged cells, wrapped rows, stamps or
handwriting). Treat these numbers as a regression baseline only; real accuracy
must be measured with permissioned invoices (scripts/benchmark_invoices.py).
"""
from __future__ import annotations

import argparse
import io
import random
import time
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

import pypdfium2 as pdfium
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.commercial_invoice import extract_commercial_invoice
from app.extraction import extract_invoice_fields

SUPPLIERS = ["Harbor Point Trading Ltd", "Nordic Valve Systems AB", "Pacific Rim Textiles Co",
             "Andes Coffee Exporters SA", "Delta Marine Parts LLC", "Sunrise Ceramics Pvt Ltd",
             "Atlas Office Supplies Inc", "Meridian Electronics GmbH", "Coral Bay Foods Ltd",
             "Iberia Olive Oil SL"]
BUYERS = ["Island Hardware Ltd", "Metro Retail Group", "Caribe Imports SRL", "Northline Distributors"]
PRODUCTS = [("Steel hammer 500g", "pcs"), ("LED bulb 9W", "pcs"), ("Cotton T-shirt M", "pcs"),
            ("Ground coffee 1kg", "kg"), ("Brass ball valve 1in", "pcs"), ("Ceramic tile 30x30", "box"),
            ("A4 copy paper", "box"), ("USB-C cable 1m", "pcs"), ("Canned tuna 170g", "ctn"),
            ("Olive oil 1L", "pcs"), ("Safety gloves", "pairs"), ("Nylon rope 20m", "rolls")]
CURRENCIES = [("USD", "Currency: USD"), ("EUR", "Currency: EUR"), ("GBP", "Currency: GBP"),
              ("BZD", "Currency: BZD"), ("MXN", "Moneda: MXN"), ("CAD", "Currency: CAD")]
INCOTERMS = ["FOB Shenzhen", "CIF Belize City", "EXW Valencia", "DAP Miami", "FCA Hamburg"]
TWO = Decimal("0.01")


def money(value: Decimal, comma: bool) -> str:
    text = f"{value.quantize(TWO, ROUND_HALF_UP):,.2f}"
    if comma:  # 1,234.56 -> 1.234,56
        text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return text


@dataclass
class Case:
    name: str
    text: str
    truth: dict
    items: list
    as_image: bool
    spanish: bool = False
    meta: dict = field(default_factory=dict)


def make_case(i: int, rng: random.Random, image_share: float) -> Case:
    spanish = rng.random() < 0.2
    comma = rng.random() < 0.2
    currency, currency_line = rng.choice(CURRENCIES)
    supplier, buyer = rng.choice(SUPPLIERS), rng.choice(BUYERS)
    number = f"{rng.choice(['INV', 'CI', 'F', 'EXP'])}-{rng.randint(2025, 2026)}-{rng.randint(100, 9999)}"
    y, m, d = 2026, rng.randint(1, 12), rng.randint(1, 28)
    date_iso = f"{y:04d}-{m:02d}-{d:02d}"
    months = ["January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"]
    date_text = rng.choice([date_iso, f"{d} {months[m - 1]} {y}", f"{months[m - 1][:3]} {d}, {y}"])

    items = []
    for name, uom in rng.sample(PRODUCTS, rng.randint(1, 8)):
        qty = rng.randint(1, 500)
        price = Decimal(rng.randint(50, 50000)) / 100
        items.append({"description": name, "quantity": str(qty), "uom": uom,
                      "unit_price": f"{price:.2f}", "line_total": f"{(price * qty).quantize(TWO):.2f}"})
    subtotal = sum(Decimal(it["line_total"]) for it in items)
    discount = (subtotal * Decimal("0.05")).quantize(TWO) if rng.random() < 0.15 else None
    freight = Decimal(rng.randint(2000, 90000)) / 100 if rng.random() < 0.5 else None
    insurance = Decimal(rng.randint(500, 9000)) / 100 if freight and rng.random() < 0.5 else None
    tax = ((subtotal - (discount or 0)) * Decimal("0.08")).quantize(TWO) if rng.random() < 0.4 else None
    total = subtotal - (discount or 0) + (freight or 0) + (insurance or 0) + (tax or 0)

    L = (lambda en, es: es if spanish else en)
    lines = [L("COMMERCIAL INVOICE", "FACTURA COMERCIAL"), f"{L('Seller', 'Vendedor')}: {supplier}",
             f"{L('Buyer', 'Comprador')}: {buyer}",
             f"{L('Invoice No', 'Factura No')}: {number}", f"{L('Date', 'Fecha')}: {date_text}",
             currency_line, f"Incoterm: {rng.choice(INCOTERMS)}", "",
             L("Description            Qty   Unit Price   Amount",
               "Descripcion            Cantidad   Precio Unitario   Importe")]
    for it in items:
        lines.append(f"{it['description']:<22} {it['quantity']} {it['uom']}   "
                     f"{money(Decimal(it['unit_price']), comma)}   {money(Decimal(it['line_total']), comma)}")
    lines.append("")
    lines.append(f"Subtotal: {money(subtotal, comma)}")
    if discount:
        lines.append(f"{L('Discount', 'Descuento')}: {money(discount, comma)}")
    if freight:
        lines.append(f"{L('Freight', 'Flete')}: {money(freight, comma)}")
    if insurance:
        lines.append(f"{L('Insurance', 'Seguro')}: {money(insurance, comma)}")
    if tax:
        lines.append(f"{L('Tax', 'IVA')}: {money(tax, comma)}")
    lines.append(f"{L('Total', 'Total a pagar')}: {money(total, comma)}")

    truth = {"supplier_name": supplier, "invoice_number": number, "invoice_date": date_iso,
             "currency": currency, "subtotal": f"{subtotal:.2f}", "tax": f"{tax:.2f}" if tax else None,
             "total": f"{total.quantize(TWO):.2f}"}
    return Case(f"synthetic-{i:03d}", "\n".join(lines), truth, items, rng.random() < image_share,
                spanish, {"comma": comma, "n_items": len(items)})


def _pdf(text: str) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    y = 800
    for line in text.splitlines():
        pdf.setFont("Courier", 9.5)  # monospaced keeps table columns aligned
        pdf.drawString(40, y, line)
        y -= 15
    pdf.save()
    return buffer.getvalue()


def _to_text(case: Case, rng: random.Random) -> tuple[str, bool]:
    """Return extracted text the way the API would: PDF text layer or OCR of an image."""
    from app.main import _process_file  # same pipeline the API uses
    data = _pdf(case.text)
    if not case.as_image:
        text, ocr, *_ = _process_file(data, ".pdf", f"{case.name}.pdf")
        return text, ocr
    page = pdfium.PdfDocument(data)[0]
    image = page.render(scale=rng.choice([1.6, 2.0, 2.4])).to_pil().convert("L")
    image = image.rotate(rng.uniform(-1.2, 1.2), expand=True, fillcolor=255)
    if rng.random() < 0.5:
        image = image.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 0.8)))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    text, ocr, *_ = _process_file(buffer.getvalue(), ".png", f"{case.name}.png")
    return text, ocr


def _eq(a, b) -> bool:
    return (a or None) == (b or None)


def run(count: int, seed: int, image_share: float) -> dict:
    rng = random.Random(seed)
    cases = [make_case(i + 1, rng, image_share) for i in range(count)]
    fields = list(cases[0].truth)
    stats = {f: {"correct": 0, "wrong_flagged": 0, "wrong_unflagged": 0, "n": 0} for f in fields}
    by_kind = {"pdf": {"docs": 0, "all_header_correct": 0}, "image": {"docs": 0, "all_header_correct": 0}}
    li = {"truth": 0, "found": 0, "matched": 0}
    timings = {"pdf": [], "image": []}
    failures = []
    for case in cases:
        start = time.perf_counter()
        text, _ = _to_text(case, rng)
        header = extract_invoice_fields(text)
        ci = extract_commercial_invoice(text)
        timings["image" if case.as_image else "pdf"].append(time.perf_counter() - start)
        review = set(header["fields_needing_review"])
        all_ok = True
        for f in fields:
            got, want = header["fields"].get(f), case.truth[f]
            stats[f]["n"] += 1
            if _eq(got, want):
                stats[f]["correct"] += 1
            else:
                all_ok = False
                stats[f]["wrong_flagged" if (f in review or header["warnings"]) else "wrong_unflagged"] += 1
                failures.append((case.name, "image" if case.as_image else "pdf", f, want, got))
        kind = "image" if case.as_image else "pdf"
        by_kind[kind]["docs"] += 1
        by_kind[kind]["all_header_correct"] += int(all_ok)
        # Line items: a row matches when quantity and line total both equal the truth.
        li["truth"] += len(case.items)
        li["found"] += len(ci["line_items"])
        remaining = [(it["quantity"], it["line_total"]) for it in case.items]
        for row in ci["line_items"]:
            qty = row.get("quantity")
            key = (str(Decimal(str(qty)).normalize()) if qty not in (None, "") else None, row.get("line_total"))
            for idx, (q, t) in enumerate(remaining):
                if key[1] == t and (key[0] == str(Decimal(q).normalize()) or key[0] is None):
                    li["matched"] += 1
                    remaining.pop(idx)
                    break
    return {"count": count, "seed": seed, "fields": stats, "by_kind": by_kind, "line_items": li,
            "median_s": {k: (sorted(v)[len(v) // 2] if v else 0.0) for k, v in timings.items()}, "failures": failures}


def report(r: dict) -> str:
    out = ["# Synthetic extraction benchmark", "",
           f"Generated by `scripts/synthetic_benchmark.py` (count={r['count']}, seed={r['seed']}). "
           "Synthetic documents only: **this is a regression baseline, not a measure of real-world accuracy.**", "",
           "## Header fields", "", "| Field | Correct | Wrong but flagged for review | Wrong and NOT flagged |",
           "|---|---|---|---|"]
    for f, s in r["fields"].items():
        out.append(f"| {f} | {s['correct']}/{s['n']} ({100 * s['correct'] / s['n']:.0f}%) | {s['wrong_flagged']} | {s['wrong_unflagged']} |")
    out += ["", "## Documents with every header field correct", "", "| Input | Documents | All correct |", "|---|---|---|"]
    for k, v in r["by_kind"].items():
        if v["docs"]:
            out.append(f"| {k} | {v['docs']} | {v['all_header_correct']} ({100 * v['all_header_correct'] / v['docs']:.0f}%) |")
    li = r["line_items"]
    p = li["matched"] / li["found"] if li["found"] else 0
    rc = li["matched"] / li["truth"] if li["truth"] else 0
    out += ["", "## Line items (commercial-invoice engine)", "",
            f"- Rows in ground truth: {li['truth']}; rows returned: {li['found']}; matched (quantity and line total): {li['matched']}",
            f"- Precision {p:.0%}, recall {rc:.0%}", "",
            f"Median local processing time: text PDF {r['median_s']['pdf']:.2f} s, scanned image (OCR) {r['median_s']['image']:.2f} s", "",
            "## Misses (first 25)", "", "| Document | Input | Field | Expected | Got |", "|---|---|---|---|---|"]
    for name, kind, f, want, got in r["failures"][:25]:
        out.append(f"| {name} | {kind} | {f} | {want} | {got} |")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--image-share", type=float, default=0.35)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    text = report(run(args.count, args.seed, args.image_share))
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
