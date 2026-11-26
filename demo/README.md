# RAMVORA demonstration (synthetic invoices)

Everything in this folder is **synthetic**: fictional companies, numbers and goods, each
marked "SYNTHETIC DEMO" in its footer. Use it to show prospects how RAMVORA works
without touching any real customer document. It must never be used for accuracy claims.

## What's here

| File | Shows |
|---|---|
| `invoices/demo-001-en-standard.pdf` | English invoice, China → USA: SKUs, HS codes and origin printed per line, FOB, freight and insurance |
| `invoices/demo-002-es-factura.pdf` | Spanish *factura*, Mexico → Colombia, CIF |
| `invoices/demo-003-eur-comma-decimals.pdf` | Germany → UK, euro amounts with comma decimals (`1,25`), DAP |
| `invoices/demo-004-with-errors.pdf` | Deliberate problems: a wrong line total, line sum ≠ subtotal, no buyer. Shows how issues are flagged, not "fixed" |
| `invoices/demo-005-scanned-image.png` | An image "scan", read with OCR |
| `sample_output/synthetic-demo/latest/` | What the customer receives: `invoices.csv`, `line_items.csv`, plus `run_log.csv`, `results.json`, `REVIEW_CHECKLIST.md` |

## Run it yourself (about 2 minutes)

```bash
pip install -r requirements.txt -r requirements-dev.txt   # once
python scripts/make_demo_invoices.py demo/invoices          # regenerate the synthetic invoices
python -m app.pilot_run --customer "Synthetic Demo" --input demo/invoices --output pilot_runs
```

Open the newest folder under `pilot_runs/synthetic-demo/`; `invoices.csv` and
`line_items.csv` open in Excel. Tesseract OCR must be installed for the PNG; the Docker
image and CI already include it.

## Suggested 10-minute demo script (video call)

1. **Their problem first:** ask how long they spend keying a 20-line invoice (from the
   questionnaire).
2. Show `demo-001` next to `line_items.csv`: every line, SKU, quantity, unit, price,
   total, and origin and HS code **only because they're printed**.
3. Show `demo-003`: European number formats handled.
4. Show `demo-004`: "We don't hide problems. The line total is wrong on the invoice, so
   it's flagged for your review."
5. Show `REVIEW_CHECKLIST.md`: during the pilot, we check every invoice before it reaches
   them.
6. **Ask:** "Could we run 3–5 of your real invoices (with your permission) through the
   same process?" Then propose the pilot (see `docs/customs/15-first-pilots-plan.md`).

**Do not claim** accuracy percentages, automatic classification or duty calculation.
