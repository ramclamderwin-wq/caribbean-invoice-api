# Stripe plan descriptions

> **Status (2026-11-25): applied in TEST MODE only, by the owner.** The three
> test-mode products are now named **RAMVORA Starter**, **RAMVORA Professional**
> and **RAMVORA Business**, with the descriptions below. The owner re-checked
> afterwards: prices, intervals, currency and price IDs are unchanged. No
> products were created, archived or deleted. **Live mode has not been changed.**
> Repeat the steps below in live mode only when you are ready to take real payments.

The API meters **pages**: each PDF page counts, and an image or pasted text
counts as one page. The product text below says so (the original Stripe text
said "requests per month").

The prices recorded in test mode already match the plan (see
`STRIPE_SANDBOX_TEST_PLAN.md`), so only the wording changes. Editing a product's
description does **not** change prices, existing subscriptions or price IDs.

| Plan | Price ID (test mode) | Price | Page allowance (`PLAN_*_MONTHLY_LIMIT`) |
| --- | --- | --- | --- |
| Starter | `price_1UfA89KqMzLsvG4ZAFDh3MJU` | $19 / month | 1,000 |
| Professional | `price_1UfA8MKqMzLsvG4Zhn16WocE` | $49 / month | 5,000 |
| Business | `price_1UfA8OKqMzLsvG4ZAM90zuJE` | $149 / month | 20,000 |

## Corrected product text

**RAMVORA Starter**
> 1,000 invoice pages per month — $19. Extract supplier, invoice number, date,
> currency, subtotal, tax and total from PDFs, scans and photos. Each PDF page
> counts as one page; an image or pasted text counts as one page. Results are
> flagged for human review.

**RAMVORA Professional**
> 5,000 invoice pages per month — $49. Everything in Starter with a higher
> monthly page allowance. Each PDF page counts as one page; an image or pasted
> text counts as one page. Results are flagged for human review.

**RAMVORA Business**
> 20,000 invoice pages per month — $149. Everything in Professional with the
> highest monthly page allowance. Each PDF page counts as one page; an image or
> pasted text counts as one page. Results are flagged for human review.

Optional "marketing feature" bullets (shown on Stripe Checkout):

- Starter: `1,000 pages/month` · `PDF, scan and photo OCR` · `English and Spanish`
- Professional: `5,000 pages/month` · `PDF, scan and photo OCR` · `English and Spanish`
- Business: `20,000 pages/month` · `PDF, scan and photo OCR` · `English and Spanish`

Do not add accuracy claims ("99% accurate" and similar) until the real-invoice
benchmark has been run and published (see `benchmarks/README.md`).

## How to apply after approval (about 5 minutes)

1. Stripe Dashboard → turn **Test mode** on.
2. **Product catalog** → open *Starter* → **Edit product**.
3. Replace the description with the text above. Optionally add the feature
   bullets. **Do not edit the price.** Save.
4. Repeat for Professional and Business.
5. Start a test Checkout from staging and confirm the new wording is shown.
6. Repeat steps 2–4 in **live mode** only when you are ready to take real payments.

## Already consistent in the code

- The dashboard (`app/static/index.html`) and the README show the same prices
  and page allowances.
- `GET /v1/usage` reports `"unit": "pages"`.
