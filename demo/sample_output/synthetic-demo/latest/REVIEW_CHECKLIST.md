# Review checklist: Synthetic Demo

Engine: `rules`. Files: 5 (clean 4, needs review 1, errors 0). Model cost: US$0.0000.

**Nothing goes to the customer until every box below is ticked.**

## Every invoice

- [ ] Compare each row in `invoices.csv` with the original (number, date, parties, currency, totals).
- [ ] Compare each line in `line_items.csv` with the original (description, quantity, unit, price, total).
- [ ] Blank cells mean 'not printed on the invoice'. Do not fill them from memory or guesses.
- [ ] `hs_code_as_printed` only if the invoice prints it. Never add tariff codes.
- [ ] Record each correction and the minutes spent in the pilot error log.
- [ ] Set `review_status` to `quillvora_checked` and `reviewed_by` to your name.

## Flagged for review

- [ ] **demo-004-with-errors.pdf**: buyer; line_items; subtotal
    - Quantity x unit price (1200.00) does not equal the line total (1250.00).
    - Buyer/importer was not identified.
    - Line totals add up to 1970.00, not the invoice subtotal 2100.00.
