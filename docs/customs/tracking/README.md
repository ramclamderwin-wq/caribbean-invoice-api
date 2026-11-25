# Interview tracking and customer feedback system

Spreadsheet-based on purpose: no paid tools are needed. Keep the working copies in a
**private** folder or a private spreadsheet. These files in Git are empty templates;
never commit real customer data.

| File | One row per | Used in |
|---|---|---|
| `interviews.csv` | Interview (discovery call) | Validation weeks 1–6 |
| `pilots.csv` | Pilot customer | Concierge pilot |
| `pilot_error_log.csv` | Correction made by us or reported by the customer | Pilot (accuracy and cost data) |
| `../prospecting/prospects_100.csv` | Prospect | Outreach |

## Progress against the validation targets

```bash
python scripts/validation_gates.py --interviews private/interviews.csv --pilots private/pilots.csv
```

Reports interviews by country and segment, the 40% country cap, pain scores, paid pilots
or LOIs, sample invoices collected, and pilot conversion against the targets in
`../08-validation-programme.md`. It only counts what is recorded; it never estimates.

## Field guide (`interviews.csv`)

- `pain_score_0_3`:
  - 0 = not mentioned;
  - 1 = mentioned when prompted;
  - 2 = in their top 3 without prompting;
  - 3 = top 3 **with a number** (hours, cost).
- `invoice_rank_top3`: 1, 2, 3, or blank.
- `price_reaction`: their words, plus one of `accept`, `hesitant`, `too_expensive`, `not_asked`.
- `pilot_status`:
  - `none`, `interested`, `loi_signed`, `paid`, `declined`;
  - an LOI counts only if **signed with a price**.
- `samples_received`: the number of invoices received **with a signed consent form**
  (`consent_form_signed` = yes).

## Customer feedback process (pilot)

1. **Every delivery:** the customer reviews the spreadsheet and replies with errors found
   (template below). We log each one in `pilot_error_log.csv`.
2. **Weekly 15-minute call** (agenda below). Notes go into the `pilots.csv` notes column
   and a short weekly summary.
3. **End-of-pilot interview** (questions below), followed by a decision: continue on a
   paid plan or not, and why.
4. **Monthly:** review the error log by `error_type` and `cause`. Fix the top causes in
   the engine, and re-run the synthetic and benchmark tests.

### Error report template (send to customer)

> Please reply with any value that was wrong or missing:
> document name, field (or line number), what we gave, what it should be.
> Thank you. Every correction improves the service.

### Weekly call agenda (15 minutes)

1. What worked well this week? What didn't?
2. Errors you found: were any serious (would they have affected a declaration)?
3. Time: how long does checking our spreadsheet take, compared with keying it yourselves?
4. Anything you need differently (columns, format, turnaround)?
5. Volume next week?

### End-of-pilot interview

1. Did the pilot save your team time? How much per invoice, roughly?
2. How confident are you in the data after your review?
3. What would stop you using it every day?
4. Which features are essential: review screen, export to your system, packing lists,
   email-in, other?
5. Would you continue at **[proposed plan and price]**? If not, at what price, or with
   which change?
6. How likely are you to recommend it to another broker or forwarder (0–10)? Why?
7. Who else should we speak to?

`error_type` values: `missing`, `wrong_value`, `wrong_line_split`, `extra_line`,
`wrong_party`, `format`, `ocr_unreadable`.

`cause` values: `layout`, `scan_quality`, `language`, `number_format`, `engine_rule`,
`source_document_error`.
