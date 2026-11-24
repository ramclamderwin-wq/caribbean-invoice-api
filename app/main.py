from __future__ import annotations

import io
import os
from contextlib import asynccontextmanager
import re
import shutil
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pymupdf as fitz
import pytesseract
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.security import create_api_key, get_key_record, init_db, key_usage, record_usage, requests_in_last_minute
from app.billing import claim_checkout_session, create_checkout_session, create_portal_session, handle_webhook

APP_NAME = "Invoice Intelligence API"
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
MAX_PDF_PAGES = int(os.getenv("MAX_PDF_PAGES", "20"))
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "25000000"))
TESSERACT_CMD = os.getenv("TESSERACT_CMD")
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

@asynccontextmanager
async def lifespan(application: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=APP_NAME,
    lifespan=lifespan,
    description="Extract structured invoice data from text, PDFs, scanned PDFs, and invoice photos. Verify every result against the original.",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)


class CreateKeyRequest(BaseModel):
    label: str = Field(min_length=2, max_length=100)
    monthly_limit: int = Field(default=1000, ge=1, le=1_000_000)


class CheckoutRequest(BaseModel):
    plan: str = Field(pattern=r"^(starter|professional|business)$")
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$")


class ClaimRequest(BaseModel):
    session_id: str = Field(min_length=10, max_length=255)


def require_api_key(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="A valid Bearer API key is required.")
    raw_key = authorization[7:].strip()
    record = get_key_record(raw_key)
    if not record or not record["active"]:
        raise HTTPException(status_code=401, detail="API key is invalid or inactive.")
    usage = key_usage(record["id"], record["monthly_limit"])
    if usage["used"] >= usage["monthly_limit"]:
        raise HTTPException(status_code=429, detail="Monthly API usage limit reached.")
    requests_per_minute = int(os.getenv("REQUESTS_PER_MINUTE", "60"))
    if requests_in_last_minute(record["id"]) >= requests_per_minute:
        raise HTTPException(status_code=429, detail="Per-minute API rate limit reached. Please retry shortly.")
    return record


def require_billing_key(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="A valid Bearer API key is required.")
    record = get_key_record(authorization[7:].strip())
    if not record:
        raise HTTPException(status_code=401, detail="API key is invalid.")
    return record


@app.post("/v1/billing/checkout")
def billing_checkout(request: CheckoutRequest) -> dict[str, str]:
    """Public signup endpoint; no existing API key is required."""
    try:
        url = create_checkout_session(request.plan, request.email)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to create Stripe Checkout session.") from exc
    return {"checkout_url": url}


@app.post("/v1/billing/claim")
def billing_claim(request: ClaimRequest) -> dict[str, str]:
    try:
        return {"api_key": claim_checkout_session(request.session_id)}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to verify Stripe Checkout session.") from exc


@app.get("/signup/success", include_in_schema=False)
def signup_success() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "signup-success.html")


@app.post("/v1/billing/portal")
def billing_portal(
    key_record: dict[str, Any] = Depends(require_billing_key),
) -> dict[str, str]:
    try:
        url = create_portal_session(key_record)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to create Stripe customer portal session.") from exc
    return {"portal_url": url}


@app.post("/v1/billing/webhook")
async def billing_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, str]:
    payload = await request.body()
    try:
        return handle_webhook(payload, stripe_signature)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature or payload.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Stripe webhook processing failed.") from exc


def _record_request(key_record: dict[str, Any]) -> None:
    record_usage(key_record["id"])


def _clean_text(value: str) -> str:
    value = value.replace("\x00", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _first_match(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip(" \t:#")
    return None


def _money(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().replace(",", "")
    cleaned = re.sub(r"^[A-Z]{3}\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("$", "").replace("BZD", "").replace("USD", "").strip()
    match = re.search(r"-?\d+(?:\.\d{1,4})?", cleaned)
    if not match:
        return None
    try:
        return str(Decimal(match.group(0)).quantize(Decimal("0.01")))
    except InvalidOperation:
        return None


def extract_invoice_fields(raw_text: str) -> dict[str, Any]:
    text = _clean_text(raw_text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    invoice_number = _first_match(
        [r"(?:invoice\s*(?:number|no\.?|#|num(?:ber)?)|inv\b\s*#?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{1,})"],
        text,
    )
    invoice_date = _first_match(
        [
            r"(?:invoice\s*date|date\s*of\s*invoice|date)\s*[:#\-]?\s*((?:\d{4}[-/]\d{1,2}[-/]\d{1,2})|(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4})|(?:[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}))"
        ],
        text,
    )
    supplier = None
    for line in lines[:8]:
        if re.search(r"\b(invoice|receipt|statement|tax invoice)\b", line, re.I):
            continue
        if re.search(r"\b(invoice\s*(number|no|date)|date\s*:)", line, re.I):
            continue
        if len(line) >= 2:
            supplier = line[:160]
            break

    def amount(labels: str) -> str | None:
        value = _first_match(
            [
                rf"\b(?:{labels})\b\s*[:\-]?\s*(?:BZD|USD|BZ\$|\$)?\s*([(\-]?\s*\d[\d,]*(?:\.\d{{1,4}})?\s*\)?)"
            ],
            text,
        )
        return _money(value)

    subtotal = amount(r"sub[\s-]?total|net\s+amount|amount\s+before\s+tax")
    tax = amount(r"tax|gst|vat")
    total = amount(r"grand\s+total|total\s+due|amount\s+due|balance\s+due|invoice\s+total|total")

    currency = _first_match(
        [r"(?:currency)\s*[:\-]?\s*([A-Z]{3})", r"\b(BZD|USD|BZ\$)\b"],
        text,
    )
    if currency:
        currency = {"BZ$": "BZD"}.get(currency.upper(), currency.upper())

    fields = {
        "supplier_name": supplier,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "currency": currency,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
    }
    warnings: list[str] = []
    if not invoice_number:
        warnings.append("Invoice number was not confidently identified.")
    if not invoice_date:
        warnings.append("Invoice date was not confidently identified.")
    if not total:
        warnings.append("Invoice total was not confidently identified.")
    if subtotal and tax and total:
        try:
            if abs((Decimal(subtotal) + Decimal(tax)) - Decimal(total)) > Decimal("0.02"):
                warnings.append("Subtotal plus tax does not equal the extracted total; check discounts, fees, rounding, and the original invoice.")
        except InvalidOperation:
            warnings.append("Could not validate the invoice arithmetic.")

    return {
        "fields": fields,
        "confidence": {key: (0.90 if value is not None else 0.0) for key, value in fields.items()},
        "warnings": warnings,
        "review_required": True,
    }


def _require_tesseract() -> None:
    if not shutil.which(pytesseract.pytesseract.tesseract_cmd):
        raise HTTPException(
            status_code=503,
            detail="OCR is unavailable. Install the Tesseract OCR engine and English language data, then restart the API.",
        )


def _ocr_image(image: Image.Image) -> str:
    _require_tesseract()
    image = ImageOps.exif_transpose(image)
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise HTTPException(status_code=413, detail="Image dimensions are too large.")
    try:
        return pytesseract.image_to_string(image.convert("RGB"), lang="eng")
    except pytesseract.TesseractNotFoundError:
        _require_tesseract()
        raise


def _extract_pdf(data: bytes) -> tuple[str, bool, int]:
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The uploaded PDF is invalid or unreadable.") from exc
    if document.page_count > MAX_PDF_PAGES:
        raise HTTPException(status_code=413, detail=f"PDF exceeds the {MAX_PDF_PAGES}-page limit.")
    chunks: list[str] = []
    used_ocr = False
    for page in document:
        page_text = page.get_text("text").strip()
        if len(page_text) < 20:
            _require_tesseract()
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            page_text = _ocr_image(Image.open(io.BytesIO(pixmap.tobytes("png"))))
            used_ocr = True
        chunks.append(page_text)
    return "\n".join(chunks), used_ocr, document.page_count


@app.get("/")
def root() -> dict[str, str]:
    return {"name": APP_NAME, "version": "0.3.0", "dashboard": "/dashboard", "docs": "/docs", "health": "/health"}


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.post("/v1/admin/api-keys")
def admin_create_api_key(
    request: CreateKeyRequest,
    x_admin_key: str | None = Header(default=None),
) -> dict[str, Any]:
    admin_secret = os.getenv("API_ADMIN_KEY")
    if not admin_secret:
        raise HTTPException(status_code=503, detail="API key administration is not configured.")
    import hmac
    if not x_admin_key or not hmac.compare_digest(x_admin_key, admin_secret):
        raise HTTPException(status_code=401, detail="Administrator authorization failed.")
    raw_key, metadata = create_api_key(request.label, request.monthly_limit)
    return {"api_key": raw_key, "warning": "Copy this key now. It cannot be retrieved later.", "customer": metadata}


@app.get("/v1/usage")
def usage(key_record: dict[str, Any] = Depends(require_api_key)) -> dict[str, Any]:
    return key_usage(key_record["id"], key_record["monthly_limit"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "invoice-intelligence-api"}


@app.post("/v1/extract-text")
def extract_text(request: TextRequest, key_record: dict[str, Any] = Depends(require_api_key)) -> dict[str, Any]:
    result = extract_invoice_fields(request.text)
    result["source"] = {"type": "text", "ocr_used": False}
    _record_request(key_record)
    return result


@app.post("/v1/extract-file")
async def extract_file(file: UploadFile = File(...), key_record: dict[str, Any] = Depends(require_api_key)) -> dict[str, Any]:
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
    if suffix not in allowed:
        raise HTTPException(status_code=415, detail="Upload a PDF, PNG, JPG, WEBP, TIFF, or BMP file.")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the configured upload limit.")
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    if suffix == ".pdf":
        if not data.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail="The file does not appear to be a valid PDF.")
        text, ocr_used, page_count = _extract_pdf(data)
        source_type = "pdf"
    else:
        try:
            image = Image.open(io.BytesIO(data))
            image.verify()
            image = Image.open(io.BytesIO(data))
        except (UnidentifiedImageError, OSError) as exc:
            raise HTTPException(status_code=400, detail="The uploaded image is invalid or unreadable.") from exc
        text = _ocr_image(image)
        ocr_used, page_count, source_type = True, 1, "image"

    if not text.strip():
        raise HTTPException(status_code=422, detail="No readable text was found. Try a clearer scan or higher-resolution photo.")
    result = extract_invoice_fields(text)
    result["source"] = {"type": source_type, "filename": filename, "ocr_used": ocr_used, "pages": page_count}
    _record_request(key_record)
    return result


@app.post("/v1/extract-pdf", include_in_schema=False)
async def extract_pdf_legacy(file: UploadFile = File(...), key_record: dict[str, Any] = Depends(require_api_key)) -> dict[str, Any]:
    return await extract_file(file, key_record)
