# Caribbean Invoice Intelligence API — Prototype 0.1

This is the first runnable prototype. It accepts invoice text or a text-based PDF and returns structured JSON.

## Important limitations
- This is an early prototype, not production accounting software.
- Scanned/photo-only PDFs are not supported yet (OCR is the next development step).
- Field extraction uses simple rules and will not correctly understand every invoice layout.
- Always verify extracted values against the original document. Do not use it to approve or pay invoices automatically.

## 1. Install Python
Install Python 3.11 or newer from https://www.python.org/downloads/

## 2. Open a terminal in this project folder

Create a virtual environment:

### macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Windows
```powershell
py -m venv .venv
.venv\Scripts\activate
```

## 3. Install packages
```bash
pip install -r requirements.txt
```

## 4. Start the API
```bash
uvicorn app.main:app --reload
```

## 5. Test it
Open http://127.0.0.1:8000/docs

Try `POST /v1/extract-text` with:
```json
{
  "text": "CARIBBEAN SUPPLIES LTD\nINVOICE\nInvoice No: CS-1048\nDate: 2026-11-15\nCurrency: BZD\nSubtotal: 100.00\nTax: 12.50\nGrand Total: 112.50"
}
```

Or use `POST /v1/extract-pdf` to upload a text-based PDF.

## Endpoints
- `GET /health` — health check
- `POST /v1/extract-text` — extract fields from supplied text
- `POST /v1/extract-pdf` — extract fields from a text-based PDF

## Next development milestones
1. Add OCR for scanned invoices and phone photos.
2. Improve extraction using a structured AI model and add confidence scores.
3. Add arithmetic checks for subtotal, tax, and total.
4. Add API keys, usage limits, privacy controls, and billing.
5. Test with real, permissioned sample invoices from target customers.
