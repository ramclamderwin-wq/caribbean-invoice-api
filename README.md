# Invoice Intelligence API

A global invoice extraction API. It accepts pasted invoice text, text-based PDFs, scanned PDFs, and common invoice photos, then returns structured JSON for review. It is designed for businesses and developers processing invoices across markets and currencies.

> **Important:** This is an early-stage extraction tool, not accounting, tax, audit, or payment-approval software. OCR and rule-based extraction can make mistakes. Always compare results with the original invoice.

## Features

- Extract supplier, invoice number, date, currency, subtotal, tax, and total.
- Accept PDF, PNG, JPG/JPEG, WEBP, TIFF, and BMP uploads.
- OCR scanned PDFs and phone photos with Tesseract.
- Detect ISO currency codes explicitly printed on an invoice, including USD and BZD; otherwise currency remains unknown.
- Return warnings when required fields are missing or subtotal plus tax does not match the total.
- Enforce upload-size and PDF-page limits.
- Process uploads in memory; the API does not save invoice files to disk.

## Run locally (macOS)

Install Python 3.11+ and Tesseract OCR:

```bash
brew install tesseract
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs.

## Run locally (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/v1/extract-text` | Extract from JSON text |
| POST | `/v1/extract-file` | Extract from PDF or image upload |
| POST | `/v1/extract-pdf` | Backward-compatible PDF upload route |

### Extract text example

```bash
curl -X POST http://127.0.0.1:8000/v1/extract-text \
  -H "Content-Type: application/json" \
  -d '{"text":"NORTHSTAR SUPPLIES LLC\nINVOICE\nInvoice No: NS-1048\nDate: 2026-11-15\nCurrency: USD\nSubtotal: 100.00\nTax: 8.25\nGrand Total: 108.25"}'
```

### Upload an invoice

```bash
curl -X POST http://127.0.0.1:8000/v1/extract-file \
  -F "file=@invoice-scan.pdf"
```

The response contains `fields`, `confidence`, `warnings`, `review_required`, and `source` metadata. Confidence values are rule-match indicators, not statistically calibrated probabilities.

## Configuration

- `MAX_UPLOAD_BYTES`: maximum upload size (default 15 MiB).
- `MAX_PDF_PAGES`: maximum PDF pages (default 20).
- `MAX_IMAGE_PIXELS`: maximum image pixels (default 25 million).
- `TESSERACT_CMD`: optional absolute path to the Tesseract executable.
- `CORS_ORIGINS`: comma-separated allowed origins. Set explicit production origins before connecting a browser frontend.

## Deploy with Docker

```bash
docker build -t invoice-intelligence-api .
docker run --rm -p 8000:8000 invoice-intelligence-api
```

A `render.yaml` is included for a simple Render Docker deployment. After pushing the repository, create a new Blueprint in Render and select this repository. Confirm the service URL and test `/health` and `/docs`.

## Development tests

```bash
pip install pytest httpx
pytest -q
```

A test suite is included in `tests/test_extraction.py`.

## Next milestones before selling access

1. Test OCR and extraction against permissioned real invoices from multiple industries, countries, layouts, and currencies.
2. Improve extraction for line items, discounts, delivery charges, sales taxes, VAT/GST, and varied date formats.
3. Add API-key authentication, per-customer usage limits, and key rotation.
4. Add privacy and retention controls, customer data deletion, audit logs, and secure secret management.
5. Add subscription billing only after authentication and usage metering are reliable.
6. Add an optional AI extraction provider behind a configurable interface, with strict privacy controls and validation.

Do not put API secrets or customer invoices in source control. Do not use extracted data to automatically pay or approve invoices.


## API authentication and customer usage

Invoice extraction endpoints require a customer API key in the HTTP Authorization header:

```http
Authorization: Bearer iia_live_your_key
```

- `POST /v1/extract-text` and `POST /v1/extract-file` require a valid key.
- `GET /v1/usage` returns the current UTC calendar month's request count and remaining quota.
- `POST /v1/admin/api-keys` creates a customer key. Protect this endpoint with the server-side `API_ADMIN_KEY` environment variable and the `X-Admin-Key` header.
- Customer API keys are stored as SHA-256 hashes; the raw key is shown only once when created.
- `DEFAULT_MONTHLY_LIMIT` sets the default monthly request allowance (default 1,000).
- `DATABASE_PATH` sets the SQLite database file location. Production deployments must use persistent storage and backups.

Example: create a customer key (run only from a trusted administrator environment):

```bash
curl -X POST https://YOUR_API_HOST/v1/admin/api-keys \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: $API_ADMIN_KEY" \
  -d '{"label":"Acme Books","monthly_limit":1000}'
```

Open `/dashboard` on the deployed service to use the lightweight developer dashboard. It does not save API keys in browser storage.

## Render deployment notes

The included Blueprint config uses a paid always-on service and a persistent disk because customer keys and usage records must survive restarts. Before creating the Blueprint, review Render's current service and disk charges. Set the secret `API_ADMIN_KEY` and a comma-separated `CORS_ORIGINS` value in Render's environment settings. Never commit secrets to GitHub.

## Stripe subscription billing (integration in progress)

Stripe Checkout and Customer Portal endpoints are implemented in the API. They require server-side configuration and a verified webhook before they can be used.

- `POST /v1/billing/checkout` — authenticated with an existing API key; creates a hosted subscription Checkout session for Starter, Professional, or Business.
- `POST /v1/billing/portal` — creates a Stripe Customer Portal session for an API key already linked to a Stripe customer.
- `POST /v1/billing/webhook` — verifies Stripe signatures and updates the linked API key's plan, monthly quota, and active status for subscription events.

Required environment variables:
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_PROFESSIONAL`, `STRIPE_PRICE_BUSINESS`
- `CHECKOUT_SUCCESS_URL`, `CHECKOUT_CANCEL_URL`, `CUSTOMER_PORTAL_RETURN_URL`
- Optional quotas: `PLAN_STARTER_MONTHLY_LIMIT` (1,000), `PLAN_PROFESSIONAL_MONTHLY_LIMIT` (5,000), `PLAN_BUSINESS_MONTHLY_LIMIT` (20,000).

Create the three recurring prices in Stripe and place their Price IDs in the environment variables; do not put secret keys or webhook secrets in GitHub. Prices shown in the business plan are proposals until approved and created in Stripe. The company must finish test-mode checkout and webhook testing before any live subscription is offered.

Important current limitation: API keys are still provisioned by the administrator using `POST /v1/admin/api-keys`. The customer self-signup/key-delivery flow is not yet implemented. The API must not be advertised as a fully automated self-service SaaS until that flow, subscription lifecycle tests, and deployment verification are complete.
