# Public dataset evaluation (licence-checked, no customer data)

Same extraction code as the API (in-process). All inputs are **images** (OCR path).

## CORD v2 receipts (real, Indonesia, IDR) (15 documents)

| Field | Correct | Wrong, flagged for review | Wrong, not flagged |
|---|---|---|---|
| subtotal | 3/11 (27%) | 8 | 0 |
| total | 3/15 (20%) | 12 | 0 |

Line items: 28 in labels, 0 returned (receipt rows are not matched individually).
Median time per document: 0.4 s

Misses (first 12):

| Document | Field | Expected | Got |
|---|---|---|---|
| cord_test_000 | subtotal | 60000 | 0.00 |
| cord_test_000 | total | 60000 | None |
| cord_test_001 | total | 91000 | 31000.00 |
| cord_test_002 | subtotal | 28000 | None |
| cord_test_002 | total | 28000 | None |
| cord_test_003 | total | 11000 | None |
| cord_test_004 | subtotal | 194000 | None |
| cord_test_004 | total | 174600 | None |
| cord_test_005 | subtotal | 28182 | None |
| cord_test_007 | subtotal | 100909 | None |
| cord_test_007 | total | 111000 | None |
| cord_test_008 | subtotal | 45455 | None |

## FATURA invoices (synthetic, 50 templates) (12 documents)

- Not scored (no ready-made labels). A total was found on 9/12; flagged for review: 12/12.

## Katana invoices (synthetic, US-style) (13 documents)

| Field | Correct | Wrong, flagged for review | Wrong, not flagged |
|---|---|---|---|
| invoice_number | 13/13 (100%) | 0 | 0 |
| invoice_date | 8/13 (62%) | 5 | 0 |
| supplier | 0/13 (0%) | 13 | 0 |
| subtotal | 13/13 (100%) | 0 | 0 |
| tax | 13/13 (100%) | 0 | 0 |
| total | 13/13 (100%) | 0 | 0 |

Line items: 45 in labels, 12 returned, 0 matched by line total.
Median time per document: 1.0 s

Misses (first 12):

| Document | Field | Expected | Got |
|---|---|---|---|
| katana_test_000 | supplier | Bradley-Andrade 9879 Elizabeth | None |
| katana_test_001 | supplier | Hopkins and Sons 62283 Flores  | None |
| katana_test_002 | invoice_date | 2015-06-02 | None |
| katana_test_002 | supplier | Trujillo-Hunt 430 Mark Ferry S | None |
| katana_test_003 | invoice_date | 2014-10-01 | None |
| katana_test_003 | supplier | Nichols-Barajas 3882 Stacy Vil | None |
| katana_test_004 | supplier | Smith-Cook 174 Justin Causeway | None |
| katana_test_005 | supplier | Kaiser, Hays and Cook 460 Rich | None |
| katana_test_006 | supplier | Smith Ltd 290 Jodi Gardens Cha | None |
| katana_test_007 | supplier | Gregory, Patterson and Fischer | None |
| katana_test_008 | invoice_date | 2015-08-01 | None |
| katana_test_008 | supplier | Gordon, Alvarado and Jones 943 | None |


## Interpretation
- **No silent errors:** every wrong value in this run was flagged for human review.
- **Katana (synthetic, US-style invoices):** invoice number, subtotal, VAT and total 13/13 after fixes found in this
  evaluation (summary "Total" line with net/VAT/gross; "Date of issue" label). The remaining dates are ambiguous
  numeric dates (e.g. 06/02/2015), which the engine deliberately does not guess. **Supplier 0/13:** side-by-side
  "Seller / Client" columns are merged by OCR; the engine now returns nothing (flagged) instead of a wrong value.
  **Line items 0 matched:** multi-line descriptions and a unit-of-measure column defeat the rule-based table reader.
- **CORD (real, low-quality phone photos of Indonesian receipts):** poor OCR ("SUB [UT" for SUBTOTAL). Receipts are
  not RAMVORA's target document, but this shows the limits of rule-based OCR on poor images.
- **Conclusion:** the rule engine handles clean, well-labelled layouts but not varied real-world layouts and tables.
  Real customer invoices, and the optional AI engine (`scripts/compare_engines.py`, needs owner approval and an API
  key), are needed before quoting accuracy.

## Data attribution (licences checked by the owner on 2026-11-26)
- CORD v2, NAVER Clova AI (https://huggingface.co/datasets/naver-clova-ix/cord-v2), CC BY 4.0.
- Katana invoices (https://huggingface.co/datasets/katanaml-org/invoices-donut-data-v1), MIT; underlying Mendeley
  data doi:10.17632/tnj49gpmtz.2, CC BY 4.0.
- FATURA (https://zenodo.org/records/10371464), CC BY 4.0.
The documents themselves are not stored in this repository.
