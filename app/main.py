from __future__ import annotations

import io
import os
import re
import shutil
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from datetime import datetime, timezone, timedelta

import pymupdf as fitz
import pytesseract
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.security import (
    UsageLimitExceeded, create_api_key, get_key_record, init_db, key_usage,
    reserve_usage, rotate_api_key, revoke_api_key,
)
from app.billing import create_checkout_session, claim_checkout_key, create_portal_session, handle_webhook
from app.extraction import extract_invoice_fields

APP_NAME = "Quillvora API"
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
MAX_PDF_PAGES = int(os.getenv("MAX_PDF_PAGES", "20"))
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "25000000"))
MAX_PDF_PAGE_PIXELS = int(os.getenv("MAX_PDF_PAGE_PIXELS", "16000000"))
MAX_OCR_PAGES = int(os.getenv("MAX_OCR_PAGES", "5"))
OCR_TIMEOUT_SECONDS = int(os.getenv("OCR_TIMEOUT_SECONDS", "30"))
TESSERACT_CMD = os.getenv("TESSERACT_CMD")
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


@asynccontextmanager
async def lifespan(application: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=APP_NAME,
    lifespan=lifespan,
    description="Quillvora extracts structured invoice data from text, PDFs, scanned PDFs, and invoice photos. Verify every result against the original.",
    version="0.3.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "").split(","),
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
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def require_api_key(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="A valid Bearer API key is required.")
    record = get_key_record(authorization[7:].strip())
    if not record or not record["active"]:
        raise HTTPException(status_code=401, detail="API key is invalid or inactive.")
    if record.get("subscription_status") == "past_due":
        started = record.get("past_due_since")
        if started:
            try:
                past_due_at = datetime.fromisoformat(started)
            except ValueError:
                past_due_at = datetime.now(timezone.utc)
            grace_hours = int(os.getenv("PAYMENT_GRACE_HOURS", "72"))
            if datetime.now(timezone.utc) - past_due_at > timedelta(hours=grace_hours):
                revoke_api_key(record["id"])
                raise HTTPException(status_code=402, detail="Payment is overdue. Update your payment method to restore API access.")
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
    try:
        url = create_checkout_session(request.plan, request.email)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to create Stripe Checkout session.") from exc
    return {"checkout_url": url}


@app.post("/v1/billing/claim")
def billing_claim(request: ClaimRequest, response: Response) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    try:
        api_key = claim_checkout_key(request.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to verify checkout with Stripe.") from exc
    return {"api_key": api_key, "warning": "Copy this API key now. It is displayed only once and cannot be recovered."}


@app.post("/v1/keys/rotate")
def api_key_rotate(key_record: dict[str, Any] = Depends(require_api_key)) -> dict[str, str]:
    try:
        raw_key = rotate_api_key(key_record["id"])
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"api_key": raw_key, "warning": "Your previous key is now invalid. Save this replacement securely."}


@app.post("/v1/keys/revoke")
def api_key_revoke(key_record: dict[str, Any] = Depends(require_billing_key)) -> dict[str, str]:
    revoke_api_key(key_record["id"])
    return {"status": "revoked"}


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
    rpm = int(os.getenv("REQUESTS_PER_MINUTE", "60"))
    try:
        reserve_usage(key_record["id"], key_record["monthly_limit"], rpm)
    except UsageLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


def _require_tesseract() -> None:
    command = pytesseract.pytesseract.tesseract_cmd
    if not shutil.which(command):
        raise HTTPException(
            status_code=503,
            detail="OCR is unavailable. Install the Tesseract OCR engine and English language data, then restart the API.",
        )


def _ocr_image(image: Image.Image) -> str:
    _require_tesseract()
    image = ImageOps.exif_transpose(image)
    if image.width <= 0 or image.height <= 0 or image.width * image.height > MAX_IMAGE_PIXELS:
        raise HTTPException(status_code=413, detail="Image dimensions are too large.")
    try:
        return pytesseract.image_to_string(
            image.convert("RGB"), lang="eng", timeout=OCR_TIMEOUT_SECONDS
        )
    except pytesseract.TesseractNotFoundError:
        _require_tesseract()
        raise
    except RuntimeError as exc:
        # pytesseract raises RuntimeError when its subprocess times out.
        raise HTTPException(status_code=408, detail="OCR processing exceeded its time limit.") from exc


def _extract_pdf(data: bytes) -> tuple[str, bool, int]:
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The uploaded PDF is invalid or unreadable.") from exc
    try:
        if document.page_count > MAX_PDF_PAGES:
            raise HTTPException(status_code=413, detail=f"PDF exceeds the {MAX_PDF_PAGES}-page limit.")
        chunks: list[str] = []
        used_ocr = False
        ocr_pages = 0
        for page in document:
            page_text = page.get_text("text").strip()
            if len(page_text) < 20:
                ocr_pages += 1
                if ocr_pages > MAX_OCR_PAGES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"PDF exceeds the {MAX_OCR_PAGES}-page OCR limit.",
                    )
                rect = page.rect
                estimated_pixels = max(1, int(rect.width * 2)) * max(1, int(rect.height * 2))
                if estimated_pixels > MAX_PDF_PAGE_PIXELS:
                    raise HTTPException(
                        status_code=413,
                        detail="A PDF page is too large to rasterise safely.",
                    )
                _require_tesseract()
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                if pixmap.width * pixmap.height > MAX_PDF_PAGE_PIXELS:
                    raise HTTPException(status_code=413, detail="A PDF page exceeds the OCR pixel limit.")
                with Image.open(io.BytesIO(pixmap.tobytes("png"))) as page_image:
                    page_text = _ocr_image(page_image)
                used_ocr = True
            chunks.append(page_text)
        return "\n".join(chunks), used_ocr, document.page_count
    finally:
        document.close()


def _process_file(data: bytes, suffix: str, filename: str) -> tuple[str, bool, int, str]:
    if suffix == ".pdf":
        if not data.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail="The file does not appear to be a valid PDF.")
        text, ocr_used, page_count = _extract_pdf(data)
        return text, ocr_used, page_count, "pdf"

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
            if image.width <= 0 or image.height <= 0 or image.width * image.height > MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=413, detail="Image dimensions are too large.")
            image.verify()
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=413, detail="Image dimensions are too large.")
            text = _ocr_image(image)
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(status_code=400, detail="The uploaded image is invalid, unsafe, or unreadable.") from exc
    return text, True, 1, "image"


@app.get("/")
def root() -> dict[str, str]:
    return {"name": APP_NAME, "version": "0.3.0", "dashboard": "/dashboard", "docs": "/docs", "health": "/health"}


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> Any:
    from fastapi.responses import FileResponse
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
    return {"status": "ok", "service": "quillvora-api"}


@app.post("/v1/extract-text")
def extract_text(request: TextRequest, key_record: dict[str, Any] = Depends(require_api_key)) -> dict[str, Any]:
    _record_request(key_record)
    result = extract_invoice_fields(request.text)
    result["source"] = {"type": "text", "ocr_used": False}
    return result


@app.post("/v1/extract-file")
async def extract_file(file: UploadFile = File(...), key_record: dict[str, Any] = Depends(require_api_key)) -> dict[str, Any]:
    # Reserve quota before reading or decoding untrusted content. Failed and
    # malformed attempts are metered too, so expensive failures are not free.
    _record_request(key_record)
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

    # All PDF parsing, image decoding and OCR run off the ASGI event loop.
    text, ocr_used, page_count, source_type = await run_in_threadpool(
        _process_file, data, suffix, filename
    )
    if not text.strip():
        raise HTTPException(status_code=422, detail="No readable text was found. Try a clearer scan or higher-resolution photo.")
    result = extract_invoice_fields(text)
    result["source"] = {"type": source_type, "filename": filename, "ocr_used": ocr_used, "pages": page_count}
    return result


@app.post("/v1/extract-pdf", include_in_schema=False)
async def extract_pdf_legacy(file: UploadFile = File(...), key_record: dict[str, Any] = Depends(require_api_key)) -> dict[str, Any]:
    return await extract_file(file, key_record)
