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
