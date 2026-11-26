# 10. Concierge pilot design and proposed pricing

**Purpose:** prove customers will **pay for the outcome** (accurate structured invoice
data, fast) before building the platform. During the pilot, the team corrects extraction
errors by hand.

## Scope

- **Customers:** 3–5 brokers or importers from the validation interviews, in any country
  (everything runs by email and spreadsheet).
- **Duration:** 4 weeks.
- **Volume:** up to 150 invoices per customer (≈5–8 per working day).
- **Turnaround:** within 1 business day (target 4 working hours), with the cut-off in the
  customer's time zone.

## Workflow

1. **Submit:** the customer sends invoices to a dedicated pilot mailbox or shared folder,
   one per customer. Each file is logged with its time received.
2. **Extract:**
   - run `app/commercial_invoice.py` locally (rules);
   - if approved after the benchmark, run the chosen AI engine;
   - export with `app/pilot_export.py`.
3. **Correct:** a team member reviews against the original and corrects in the
   spreadsheet. **Record the corrected fields and minutes spent**, which is the real
   accuracy and cost data.
4. **Deliver:** return `invoices.csv` + `line_items.csv` (or one Excel workbook with two
   sheets) with the invoice's issues listed, and mark `review_status=ramvora_checked`.
5. **Customer review:**
   - the customer checks before using the data in their declaration;
   - they report any errors with a one-click form or reply;
   - each error is logged.

No data enters any customs system from RAMVORA. The broker remains responsible for the
declaration.

## Onboarding (day 0–2)

1. Signed pilot agreement covering:
   - scope, price and term;
   - confidentiality;
   - data use (processing only; deletion within 30 days after the pilot unless retained
     by agreement);
   - permission for benchmark use;
   - AI-provider sub-processing if used;
   - no liability for declarations.
2. A 30-minute kickoff:
   - their current process and baseline time per invoice (measure 5 invoices together);
   - their preferred column layout;
   - who submits and who reviews.
3. Agree the column mapping. The default layout is below; a custom XLSX layout comes later.
4. Test with 3 invoices before the clock starts.

## Output spreadsheet structure (implemented in `app/pilot_export.py`)

**Sheet 1, `invoices`:** one row per invoice

```
document | invoice_number | invoice_date | seller_name | seller_address | seller_tax_id
buyer_name | buyer_address | buyer_tax_id | currency | incoterm | incoterm_place | country_of_origin
subtotal | discount | freight | insurance | tax | total | line_count | line_items_total
review_flags | issues | reviewed_by | review_status
```

**Sheet 2, `line_items`:** one row per line

```
document | line_no | sku | description | hs_code_as_printed | country_of_origin
quantity | unit_of_measure | unit_price | line_total | currency | review_flags
```

**Rules:**
- blank means "not printed on the invoice";
- `hs_code_as_printed` is only ever copied from the invoice, never assigned;
- text cells are neutralised against spreadsheet formula injection.

## Proposed pilot pricing (hypothesis to test in interviews)

| Option | Price | Notes |
|---|---|---|
| **Recommended: fixed pilot fee** | **US$249 for 4 weeks, up to 150 invoices** (about $1.66 per invoice) | Simple yes/no. Credited against the first 2 months of a subscription if they continue |
| Per invoice | US$2.00 per invoice, minimum US$150 | For lower or uncertain volumes |
| Founding-customer discount | 30% off the first 6 months of the subscription | In exchange for a testimonial or case study and feedback calls |

**Rationale (assumptions to verify):**

- Keying a 10–30-line invoice is assumed to take 10–30 minutes.
- At clerk costs of roughly US$5–15 an hour in lower-cost markets and US$20–35 an hour in
  high-cost markets (assumptions to verify), that is about US$1–17 per invoice of labour.
  Errors and peak backlogs add cost.
- Brokers charge clients on the order of US$100–250 per entry (sources in `SOURCES.md`),
  so a ~$2 data cost per invoice is small relative to the fee.
- **Do not go free:** a free pilot does not test willingness to pay.
- If 3+ firms won't pay US$249, that's a key finding, not a reason to drop the price
  without learning why.

## Feedback process

- **Weekly 15-minute call:** what worked, what was wrong, time saved, what they'd pay.
- **Error log:** every customer-reported error, its type and its cause.
- **End-of-pilot interview:**
  - continue or not;
  - at what price;
  - which features are essential (review UI, direct system export, packing lists, email-in);
  - net promoter question.

## Success measures

| Measure | Target (proposed) |
|---|---|
| Customers paying for the pilot | ≥ 3 |
| Customers converting to a paid plan after the pilot | ≥ 2 of 3 |
| Customer-measured time saved per invoice | ≥ 50% vs baseline |
| Errors reaching the customer after our check | < 1 per 20 invoices, trending down |
| Our correction minutes per invoice (internal cost) | Falls week over week; sets the automation target |
| Turnaround met | ≥ 95% same-day |

**Unit-economics check:** (model cost + our correction minutes × cost per minute) per
invoice must fall well below the per-invoice price by the end of the pilot. Otherwise
the platform is not yet viable.
