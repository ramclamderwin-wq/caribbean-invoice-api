# 1. Revised product specification: Quillvora Trade Documents

## Positioning (recommendation)

**Quillvora turns supplier commercial invoices into reviewed, structured line-item data
for customs entries, in minutes instead of manual keying.**

It is an invoice-intelligence and customs-documentation workspace for customs brokers and
importers. The existing Quillvora API stays as the extraction engine underneath and remains
available to software partners.

Quillvora **prepares data**. It does not classify goods, calculate duties, or file
declarations. Those remain the licensed broker's decisions.

## Users

| User | Job to be done |
|---|---|
| Broker data-entry clerk / declarant | Get invoice header and line items into the declaration quickly and correctly |
| Broker owner / manager | More entries per staff member, fewer amendments and penalties, faster clearance for clients |
| In-house import coordinator (importer) | Prepare clean data for their broker or own declarations; reconcile invoices with POs |
| Software partner (later) | Embed extraction in a broker/forwarding system via the API |

## Core workflow (MVP after validation)

1. **Upload:** commercial invoices (PDF, scan or photo), single or batch; later email-in.
2. **Extract:** seller, buyer/importer, invoice number, date, currency, Incoterm and
   place, country of origin (only if printed), subtotal, discount, freight, insurance,
   tax and total.
3. **Line items:** description, SKU/reference, quantity, unit of measure, unit price, line
   total, currency, country of origin and HS code **only when printed on the invoice**.
4. **Check:** missing fields, quantity × price ≠ line total, line sum ≠ subtotal, mixed
   currencies, unreadable fields. Every issue is shown, not silently fixed.
5. **Review:** a side-by-side table with the original document; the reviewer corrects and
   approves. Each correction is logged, which also measures accuracy over time.
6. **Export:** CSV/Excel first (pilot: `invoices.csv` + `line_items.csv`). Later:
   per-country declaration import formats (e.g. ASYCUDA World where an import format
   exists), broker systems, and accounting exports.

## Explicitly out of scope until separately validated

- Tariff (HS) classification, duty/tax calculation, valuation rulings, origin determination.
- Submitting declarations to customs systems.
- Any automatic decision without human review.

Future research track: *suggested* classification from verified tariff data, always shown
as a suggestion with its source, never auto-applied.

## Data model

`commercial_invoice.v1` (implemented in `app/commercial_invoice.py`):

- **Header:** `seller{name,address,tax_id}`, `buyer{…}`, `invoice_number`, `invoice_date`,
  `currency`, `incoterm`, `incoterm_place`, `country_of_origin`, `subtotal`, `discount`,
  `freight`, `insurance`, `tax`, `total`.
- **Line items:** `line_items[]{line_no, description, sku, hs_code_as_printed, quantity,
  unit_of_measure, unit_price, line_total, currency, country_of_origin,
  fields_needing_review[]}`.
- **Review:** `issues[]`, `fields_needing_review[]`, `review_required` (always true), and
  `classification.hs_codes_inferred` (always false).
- **Missing values are `null`; nothing is inferred.**

**Planned additions** (after customer evidence): packing-list fields (gross/net weight,
packages, marks), PO number, payment terms, seller/buyer country codes, and
document-to-document cross-checks (invoice vs packing list vs bill of lading).

## Review and confidence indicators

- Per-field review flags come from validation rules (arithmetic, completeness, format) and
  from the AI engine's own "uncertain" list.
- **No percentage confidence is shown** until it has been calibrated against labelled
  data. Showing uncalibrated scores would mislead reviewers.

## Non-functional requirements

These are mostly reused from the existing platform:

- **Security:** hashed API keys, admin audit log, rate limiting, upload limits, encrypted
  backups (see `SECURITY_REVIEW.md`, `BACKUP_RUNBOOK.md`).
- **Privacy:** invoices are processed in memory and are not stored by the current API. The
  review workspace will need storage, which requires:
  - a retention period;
  - per-customer data isolation;
  - deletion on request;
  - a sub-processor list (including the AI provider if used).
- **International:** currency, language and date handling are configuration, not code
  forks. Country-specific export formats are plug-ins.

## Success measures (product)

- Minutes of reviewer time per invoice (measured), compared with the customer's current
  baseline.
- Field and line accuracy after extraction, before review (from logged corrections).
- Invoices processed per customer per month (retention and expansion).
