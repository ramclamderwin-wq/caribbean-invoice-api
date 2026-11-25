# 6. Line-item extraction development plan

## Status (fact)

- The original engine extracted **no line items**.
- A rule-based prototype now exists in `app/commercial_invoice.py`. It finds the item table
  by its header (quantity plus price/amount columns) and parses each row into:
  - description and SKU;
  - quantity, unit of measure, unit price and line total;
  - currency;
  - country of origin and HS code, **only when printed in their own columns**.
- On synthetic invoices it handles typical layouts (English and Spanish, units, SKUs,
  wrapped descriptions) and flags arithmetic problems. **Real-invoice accuracy is
  unknown.**

## Design rules (implemented)

1. **Present vs missing:** every field is either copied from the document or `null`.
2. **No inference of HS codes, origin or units.** A number inside a description stays in
   the description.
3. **Validation, not correction:**
   - quantity × unit price compared with the line total;
   - sum of lines compared with the subtotal;
   - a missing quantity, price or total;
   - wrapped descriptions.
   Each produces `fields_needing_review`. Printed values are kept even when inconsistent.
4. **Review indicators instead of fake confidence:** per-line and per-document review
   flags. Percent confidence is shown only after calibration against labelled data.

## Expected weaknesses of the rule approach (to measure, not assume)

- Tables where a row spans several lines, or columns are read out of order by OCR.
- Scanned photos with skew or low resolution.
- Rows with discounts per line, multiple currencies, or merged cells.
- Invoices that list goods in free text without a table.

## Plan

| Step | Work | Output | Depends on |
|---|---|---|---|
| 1 (done) | Rule prototype, schema, tests, pilot export | Prototype code | — |
| 2 | Label 50+ real commercial invoices (header and every line) | Private manifest | Validation programme (weeks 2–5) |
| 3 | Run `scripts/compare_engines.py` with rules and AI (after approval) | Measured accuracy, cost, speed | Step 2 + approval to send documents to an AI provider |
| 4 | Choose the engine. **Likely hybrid** (assumption): AI vision for reading tables; rules for validation, arithmetic checks and currency/date normalisation; fall back to rules when AI is unavailable | Decision record | Step 3 |
| 5 | Production endpoint `POST /v1/extract-commercial-invoice` behind existing auth and metering; schema versioned | API | Step 4 |
| 6 | Per-field correction logging during the pilot and review UI | Accuracy over time; calibration data | Pilot |
| 7 | Calibrate confidence (only if data supports it); add packing-list cross-checks | Confidence scores; document matching | Enough corrections logged |

## Acceptance criteria for the production engine

These are proposed and must be agreed after the benchmark:

- Line-item recall ≥ 95% and fully correct lines ≥ 85% on the customer sample, with every
  remaining error flagged or caught in review. Targets are set with pilot customers, not
  claimed in advance.
- No invented values in a manual audit of 100 extracted lines.
- Median processing time under 30 seconds per invoice.
- Model cost below 20% of the per-invoice price.
