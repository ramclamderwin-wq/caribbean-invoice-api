# Quillvora API

A global invoice extraction API from Quillvora, built for businesses and developers processing invoices across markets and currencies. It accepts pasted invoice text, text-based PDFs, scanned PDFs, and common invoice photos, then returns structured JSON for review. It is designed for businesses and developers processing invoices across markets and currencies.

> **Important:** This is an early-stage extraction tool, not accounting, tax, audit, or payment-approval software. OCR and rule-based extraction can make mistakes. Always compare results with the original invoice.

## Features

- Extract supplier, invoice number, date, currency, subtotal, tax, and total.
- Accept PDF, PNG, JPG/JPEG, WEBP, TIFF, and BMP uploads.
- OCR scanned PDFs and phone photos with Tesseract (English and Spanish language data in the Docker image).
- Detect explicit currency codes and symbols including BZD; ambiguous dollar symbols remain unknown.
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
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-spa
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

The response contains `fields`, `confidence`, `confidence_type`, `warnings`, `review_required`, `extraction_metadata`, and `source` metadata. Confidence is currently unavailable (null) because it has not been calibrated against a representative labelled invoice corpus. Every result must be reviewed against the original.

## Configuration

- `MAX_UPLOAD_BYTES`: maximum upload size (default 15 MiB).
- `MAX_PDF_PAGES`: maximum PDF pages (default 20).
- `MAX_IMAGE_PIXELS`: maximum image pixels (default 25 million).
- `MAX_PDF_PAGE_PIXELS`: maximum rasterized pixels per scanned PDF page (default 16 million).
- `MAX_OCR_PAGES`: maximum pages requiring OCR in one PDF (default 5).
- `OCR_TIMEOUT_SECONDS`: timeout per OCR page/image (default 30 seconds).
- `OCR_LANGUAGES`: Tesseract language codes (default `eng+spa`).
- `MAX_CONCURRENT_FILE_JOBS`: concurrent file decode/OCR jobs (default 1).
- `TESSERACT_CMD`: optional absolute path to the Tesseract executable.
- `CORS_ORIGINS`: comma-separated allowed origins. Cross-origin access is disabled by default; set only exact frontend origins if needed.

## Deploy with Docker

```bash
docker build -t quillvora-api .
docker run --rm -p 8000:8000 quillvora-api
```

A `render.yaml` is included for a simple Render Docker deployment. The customer-facing product brand is Quillvora; Divine Group Holdings LLC remains the legal company. After pushing the repository, create a new Blueprint in Render and select this repository. Confirm the service URL and test `/health` and `/docs`.

## Development tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

A test suite is included in `tests/`. Tests use synthetic invoices only; they do not establish real-world extraction accuracy.

## Next milestones before selling access

1. Test OCR and extraction against permissioned real invoices from multiple industries, countries, layouts, and currencies.
2. Improve extraction for line items, discounts, delivery charges, sales taxes, VAT/GST, and varied date formats.
3. Build a representative benchmark of at least 200 permissioned real invoices and measure field-level accuracy by format, country, language, and layout.
4. Complete privacy/terms, retention and deletion controls, operational logging, monitoring, backups and restore tests.
5. Verify the full Stripe Sandbox lifecycle and a staging Render deployment before public paid access.
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
- Customer API keys are authenticated by SHA-256 hashes. A separately Fernet-encrypted copy is retained for webhook email retries and browser claim; keep API_KEY_ENCRYPTION_KEY secret and backed up. Email-based recovery verifies a one-time code and rotates the key.
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

## Stripe subscription billing

Stripe Checkout is designed for public customer signup. New customers do not need an API key before choosing a plan.

- `POST /v1/billing/checkout` — public endpoint accepting a plan and email, then returning a hosted Stripe Checkout URL.
- `POST /v1/billing/claim` — accepts `{"session_id":"..."}` in a JSON body, verifies the completed subscription, and issues one API key once. The response is marked `no-store`; the session ID remains a bearer claim token and must not be shared.
- `POST /v1/billing/portal` — creates a Stripe Customer Portal session for an API key linked to a Stripe customer.
- `POST /v1/billing/recovery/request` — sends a short-lived verification code to the email on an eligible Stripe customer account.
- `POST /v1/billing/recovery/confirm` — verifies the one-time code, rotates the API key in place, and emails the replacement.
- `POST /v1/keys/rotate` and `POST /v1/keys/revoke` — rotate or revoke the currently authenticated key.
- `POST /v1/billing/webhook` — verifies Stripe signatures, deduplicates events, ignores older subscription events, maps current Stripe Price IDs to plan quotas, applies a configurable payment-failure grace period, and emails newly provisioned keys on successful checkout.

Checkout is disabled unless the API-key encryption key and email provider are configured. The API key hash is used for authentication; a separately encrypted copy is retained so webhook retries can safely deliver the same key. Keep the encryption key backed up and secret. The browser claim is still one-time, and the session ID remains a bearer token.

Planned subscription tiers (confirm the matching Stripe Sandbox products and prices before launch):
- Starter: $19/month, 1,000 API requests.
- Professional: $49/month, 5,000 API requests.
- Business: $149/month, 20,000 API requests.

Required environment variables:
- `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` (keep these only in Render secret settings).
- `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_PROFESSIONAL`, `STRIPE_PRICE_BUSINESS`.
- `CHECKOUT_SUCCESS_URL`, `CHECKOUT_CANCEL_URL`, `CUSTOMER_PORTAL_RETURN_URL`.
- `API_KEY_ENCRYPTION_KEY`: a Fernet key. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`; store only in Render secret settings and keep a secure backup.
- `RESEND_API_KEY` and `FROM_EMAIL`: a Resend API key and verified sender address.
- `CHECKOUT_RATE_LIMIT` (default 5 requests/hour per client IP), `CLAIM_RATE_LIMIT` (default 10 requests/minute per client IP), and `PAYMENT_GRACE_HOURS` (default 72).
- `RECOVERY_REQUEST_RATE_LIMIT` and `RECOVERY_CONFIRM_RATE_LIMIT` can override the default per-IP recovery throttles.
- Optional quotas: `PLAN_STARTER_MONTHLY_LIMIT` (1,000), `PLAN_PROFESSIONAL_MONTHLY_LIMIT` (5,000), `PLAN_BUSINESS_MONTHLY_LIMIT` (20,000).

Use Sandbox API keys and Sandbox Price IDs together for testing. Never put Stripe secrets in GitHub. Configure a webhook endpoint at `/v1/billing/webhook` for subscription update/deletion/pause/resume and invoice payment failed/paid events before testing subscription lifecycle. Configure Resend with a verified sender domain before enabling Checkout. Checkout key email delivery depends on the webhook and will retry on email-provider failure. Stripe Tax remains disabled until the company determines its registration and collection obligations.

The customer self-signup code is under test and must pass CI and be deployed/configured before it is advertised as a working public service.
