from __future__ import annotations

import io
import asyncio
import os
import re
import shutil
import warnings
import logging
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from datetime import datetime, timezone, timedelta

import pypdfium2 as pdfium
import pytesseract
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.security import (
    UsageLimitExceeded, get_key_record, init_db, key_usage,
    reserve_usage, reserve_request_event, release_usage_reservation, reserve_public_rate_limit,
    rotate_api_key, revoke_api_key, database_health_check, delete_customer_local_data,
    expire_past_due_access, count_public_rate_limit,
)
from app.billing import (
    create_checkout_session, create_portal_session, handle_webhook,
    request_api_key_recovery, confirm_api_key_recovery, cancel_customer_subscriptions,
)
from app.extraction import extract_invoice_fields
from app.admin import router as admin_router
from app.net import client_ip

APP_NAME = "Quillvora API"
logger = logging.getLogger("invoice_api")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
MAX_WEBHOOK_BODY_BYTES = int(os.getenv("MAX_WEBHOOK_BODY_BYTES", str(1024 * 1024)))
# Every other endpoint (JSON bodies such as /v1/extract-text, at most 200,000
# characters) is capped too, so oversized bodies are never buffered in memory.
MAX_JSON_BODY_BYTES = int(os.getenv("MAX_JSON_BODY_BYTES", str(1024 * 1024)))
_UPLOAD_PATHS = {"/v1/extract-file", "/v1/extract-pdf"}
MAX_PDF_PAGES = int(os.getenv("MAX_PDF_PAGES", "20"))
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "25000000"))
MAX_PDF_PAGE_PIXELS = int(os.getenv("MAX_PDF_PAGE_PIXELS", "16000000"))
MAX_OCR_PAGES = int(os.getenv("MAX_OCR_PAGES", "5"))
OCR_TIMEOUT_SECONDS = int(os.getenv("OCR_TIMEOUT_SECONDS", "30"))
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "eng+spa")
_FILE_PROCESSING_SEMAPHORE = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_FILE_JOBS", "1")) )
TESSERACT_CMD = os.getenv("TESSERACT_CMD")
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


async def _backup_scheduler() -> None:
    """Periodic encrypted backups when BACKUP_ENABLED=true (see app/backup.py)."""
    from app import backup
    interval = max(1.0, float(os.getenv("BACKUP_INTERVAL_HOURS", "24"))) * 3600
    await asyncio.sleep(max(0.0, float(os.getenv("BACKUP_FIRST_DELAY_MINUTES", "10"))) * 60)
    while True:
        try:
            await run_in_threadpool(backup.run_backup)
        except Exception as exc:  # keep the API running; failures are recorded and logged
            backup.record_failure(exc)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(application: FastAPI):
    init_db()
    task = None
    if os.getenv("BACKUP_ENABLED", "").lower() in {"1", "true", "yes"}:
        task = asyncio.create_task(_backup_scheduler())
    try:
        yield
    finally:
        if task:
            task.cancel()


app = FastAPI(
    title=APP_NAME,
    lifespan=lifespan,
    description="Quillvora extracts structured invoice data from text, PDFs, scanned PDFs, and invoice photos. Verify every result against the original.",
    version="0.4.0",
)
class UploadBodySizeLimitMiddleware:
    """Reject oversized upload bodies before multipart parsing can spool them."""
    def __init__(self, application, max_bytes: int):
        self.application = application
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        path = scope.get("path")
        if scope["type"] != "http":
            await self.application(scope, receive, send)
            return

        if path == "/v1/billing/webhook":
            body_limit = MAX_WEBHOOK_BODY_BYTES
        elif path in _UPLOAD_PATHS:
            body_limit = self.max_bytes
        else:
            body_limit = MAX_JSON_BODY_BYTES
        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > body_limit:
                    await self._reject(send)
                    return
            except ValueError:
                await self._reject(send)
                return

        total = 0
        oversized = False

        async def limited_receive():
            nonlocal total, oversized
            if oversized:
                return {"type": "http.request", "body": b"", "more_body": False}
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > body_limit:
                    oversized = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def guarded_send(message):
            if not oversized:
                await send(message)

        await self.application(scope, limited_receive, guarded_send)
        if oversized:
            await self._reject(send)

    async def _reject(self, send):
        body = b'{"detail":"Request body exceeds the configured size limit."}'
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        })
        await send({"type": "http.response.body", "body": body})


app.include_router(admin_router)
app.add_middleware(
    UploadBodySizeLimitMiddleware,
    max_bytes=MAX_UPLOAD_BYTES + 128 * 1024,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "").split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)


class CheckoutRequest(BaseModel):
    plan: str = Field(pattern=r"^(starter|professional|business)$")
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class RecoveryRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class RecoveryConfirmRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    code: str = Field(pattern=r"^\d{6}$")


HOLD_DETAIL = "API access is suspended pending a billing review. Contact support."


def _active_key_record(authorization: str | None, request: Request | None = None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="A valid Bearer API key is required.")
    ip = client_ip(request) if request is not None else None
    limit = int(os.getenv("INVALID_KEY_RATE_LIMIT", "30"))
    if ip and count_public_rate_limit(ip, "invalid_api_key", 60) >= limit:
        raise HTTPException(status_code=429, detail="Too many invalid API key attempts. Please wait and try again.")
    record = get_key_record(authorization[7:].strip())
    if not record and ip:
        try:
            reserve_public_rate_limit(ip, "invalid_api_key", limit + 1, 60)
        except UsageLimitExceeded:
            pass
    if not record or record.get("revoked_at"):
        raise HTTPException(status_code=401, detail="API key is invalid or inactive.")
    if record.get("access_hold_reason"):
        raise HTTPException(status_code=403, detail=HOLD_DETAIL)
    if not record["active"]:
        raise HTTPException(status_code=401, detail="API key is invalid or inactive.")
    return record


def require_api_key(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    record = _active_key_record(authorization, request)
    if record.get("subscription_status") == "past_due":
        started = record.get("past_due_since")
        grace_hours = int(os.getenv("PAYMENT_GRACE_HOURS", "72"))
        # Legacy past_due rows without a timestamp cannot receive an indefinite grace period.
        if not started:
            expire_past_due_access(record["id"])
            raise HTTPException(status_code=402, detail="Payment is overdue. Update your payment method to restore API access.")
        try:
            past_due_at = datetime.fromisoformat(started)
        except ValueError:
            past_due_at = datetime.now(timezone.utc) - timedelta(hours=grace_hours + 1)
        if past_due_at.tzinfo is None:
            past_due_at = past_due_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - past_due_at > timedelta(hours=grace_hours):
            expire_past_due_access(record["id"])
            raise HTTPException(status_code=402, detail="Payment is overdue. Update your payment method to restore API access.")
    return record


def require_deletion_key(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Allow a known key to request erasure even if it has already been revoked."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="A valid Bearer API key is required.")
    record = get_key_record(authorization[7:].strip())
    if not record:
        raise HTTPException(status_code=401, detail="API key is invalid.")
    return record


def require_billing_key(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return _active_key_record(authorization, request)


def _throttle_public_request(request: Request, action: str, default_limit: int, window_seconds: int) -> None:
    subject = client_ip(request)
    try:
        limit = int(os.getenv(f"{action.upper()}_RATE_LIMIT", str(default_limit)))
        reserve_public_rate_limit(subject, action, limit, window_seconds)
    except UsageLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@app.post("/v1/billing/checkout")
def billing_checkout(body: CheckoutRequest, http_request: Request) -> dict[str, str]:
    _throttle_public_request(http_request, "checkout", 5, 3600)
    try:
        url = create_checkout_session(body.plan, body.email)
    except RuntimeError as exc:
        # The specific configuration problem is for operators, not the public.
        logger.error("checkout_unavailable reason=%s", exc)
        raise HTTPException(status_code=503, detail="Checkout is temporarily unavailable. Please try again later.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to create Stripe Checkout session.") from exc
    return {"checkout_url": url}


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


@app.post("/v1/billing/recovery/request")
def billing_recovery_request(body: RecoveryRequest, response: Response, http_request: Request) -> dict[str, str]:
    _throttle_public_request(http_request, "recovery_request", 5, 3600)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    try:
        reserve_public_rate_limit(body.email.lower(), "recovery_email", 3, 3600)
        request_api_key_recovery(body.email.lower())
    except UsageLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("recovery_unavailable reason=%s", exc)
        raise HTTPException(status_code=503, detail="Key recovery is temporarily unavailable. Please try again later.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to process the recovery request right now.") from exc
    return {"message": "If an eligible subscription exists for that email, a verification code has been sent."}


@app.post("/v1/billing/recovery/confirm")
def billing_recovery_confirm(body: RecoveryConfirmRequest, response: Response, http_request: Request) -> dict[str, str]:
    _throttle_public_request(http_request, "recovery_confirm", 10, 600)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    try:
        confirm_api_key_recovery(body.email.lower(), body.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("recovery_unavailable reason=%s", exc)
        raise HTTPException(status_code=503, detail="Key recovery is temporarily unavailable. Please try again later.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to complete key recovery right now.") from exc
    return {"message": "Your API key has been rotated and sent to your verified email address."}


@app.delete("/v1/account")
def delete_account(key_record: dict[str, Any] = Depends(require_deletion_key)) -> dict[str, Any]:
    customer_id = key_record.get("stripe_customer_id")
    if customer_id:
        try:
            cancel_customer_subscriptions(str(customer_id))
        except Exception as exc:
            logger.exception("Stripe subscription cancellation failed during account deletion.")
            raise HTTPException(
                status_code=503,
                detail="Unable to cancel the billing subscription. No local account data was deleted; retry or contact support.",
            ) from exc
    deleted = delete_customer_local_data(int(key_record["id"]))
    return {
        "status": "deleted",
        "local_api_records_deleted": deleted,
        "billing_records": "Stripe retains payment and invoice records as required by its legal obligations.",
    }


@app.post("/v1/billing/portal")
def billing_portal(
    key_record: dict[str, Any] = Depends(require_billing_key),
) -> dict[str, str]:
    try:
        url = create_portal_session(key_record)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("portal_unavailable reason=%s", exc)
        raise HTTPException(status_code=503, detail="The billing portal is temporarily unavailable. Please try again later.") from exc
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
    """Count an API attempt for abuse throttling, regardless of billable outcome."""
    rpm = int(os.getenv("REQUESTS_PER_MINUTE", "60"))
    try:
        reserve_request_event(key_record["id"], rpm)
    except UsageLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


def _reserve_page_usage(key_record: dict[str, Any], pages: int) -> str:
    rpm = int(os.getenv("REQUESTS_PER_MINUTE", "60"))
    try:
        return reserve_usage(
            key_record["id"], key_record["monthly_limit"], rpm,
            units=pages, count_request=False,
        )
    except UsageLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


def _preflight_page_count(data: bytes, suffix: str) -> int:
    """Validate enough of the upload to know billable page units before OCR."""
    if suffix == ".pdf":
        if not data.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail="The file does not appear to be a valid PDF.")
        try:
            document = pdfium.PdfDocument(data)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="The uploaded PDF is invalid or unreadable.") from exc
        try:
            page_count = len(document)
        finally:
            document.close()
        if page_count < 1:
            raise HTTPException(status_code=400, detail="The uploaded PDF contains no pages.")
        if page_count > MAX_PDF_PAGES:
            raise HTTPException(status_code=413, detail=f"PDF exceeds the {MAX_PDF_PAGES}-page limit.")
        return page_count

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
            if image.width <= 0 or image.height <= 0 or image.width * image.height > MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=413, detail="Image dimensions are too large.")
            image.verify()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(status_code=400, detail="The uploaded image is invalid, unsafe, or unreadable.") from exc
    return 1


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
        prepared = ImageOps.autocontrast(ImageOps.grayscale(image.convert("RGB")))
        return pytesseract.image_to_string(
            prepared, lang=OCR_LANGUAGES, config="--psm 6", timeout=OCR_TIMEOUT_SECONDS
        )
    except pytesseract.TesseractNotFoundError:
        _require_tesseract()
        raise
    except RuntimeError as exc:
        # pytesseract uses RuntimeError for timeouts; do not mislabel unrelated
        # image/OCR failures as a timeout.
        if "timeout" in str(exc).lower():
            raise HTTPException(status_code=408, detail="OCR processing exceeded its time limit.") from exc
        logger.exception("OCR engine failed for an image.")
        raise HTTPException(status_code=500, detail="OCR processing failed.") from exc


def _extract_pdf(data: bytes) -> tuple[str, bool, int]:
    try:
        document = pdfium.PdfDocument(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The uploaded PDF is invalid or unreadable.") from exc
    try:
        page_count = len(document)
        if page_count > MAX_PDF_PAGES:
            raise HTTPException(status_code=413, detail=f"PDF exceeds the {MAX_PDF_PAGES}-page limit.")
        chunks: list[str] = []
        used_ocr = False
        ocr_pages = 0
        for page_index in range(page_count):
            page = document[page_index]
            try:
                text_page = page.get_textpage()
                try:
                    page_text = text_page.get_text_bounded().strip()
                finally:
                    text_page.close()
                if len(page_text) < 20:
                    ocr_pages += 1
                    if ocr_pages > MAX_OCR_PAGES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"PDF exceeds the {MAX_OCR_PAGES}-page OCR limit.",
                        )
                    width, height = page.get_size()
                    estimated_pixels = max(1, int(width * 2)) * max(1, int(height * 2))
                    if estimated_pixels > MAX_PDF_PAGE_PIXELS:
                        raise HTTPException(
                            status_code=413,
                            detail="A PDF page is too large to rasterise safely.",
                        )
                    _require_tesseract()
                    bitmap = page.render(scale=2)
                    try:
                        if bitmap.width * bitmap.height > MAX_PDF_PAGE_PIXELS:
                            raise HTTPException(status_code=413, detail="A PDF page exceeds the OCR pixel limit.")
                        page_image = bitmap.to_pil()
                        try:
                            page_text = _ocr_image(page_image)
                        finally:
                            page_image.close()
                    finally:
                        # The rendered bitmap owns the backing buffer; close it
                        # only after the PIL view has been released.
                        if hasattr(bitmap, "warn_on_close"):
                            bitmap.warn_on_close = False
                        bitmap.close()
                    used_ocr = True
                chunks.append(page_text)
            finally:
                page.close()
        return "\n".join(chunks), used_ocr, page_count
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


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    started = time.monotonic()
    request_id = secrets.token_hex(8)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed request_id=%s method=%s path=%s", request_id, request.method, request.url.path)
        raise
    duration_ms = round((time.monotonic() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_complete request_id=%s method=%s path=%s status=%s duration_ms=%s",
        request_id, request.method, request.url.path, response.status_code, duration_ms,
    )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path == "/dashboard":
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'",
        )
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.get("/")
def root() -> dict[str, str]:
    return {"name": APP_NAME, "version": "0.4.0", "dashboard": "/dashboard", "docs": "/docs", "health": "/health"}


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> Any:
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/v1/usage")
def usage(key_record: dict[str, Any] = Depends(require_api_key)) -> dict[str, Any]:
    return key_usage(key_record["id"], key_record["monthly_limit"])


@app.get("/health")
async def health() -> dict[str, str]:
    if not database_health_check():
        raise HTTPException(status_code=503, detail="Database is unavailable.")
    return {"status": "ok", "service": "quillvora-api"}


@app.post("/v1/extract-text")
def extract_text(request: TextRequest, key_record: dict[str, Any] = Depends(require_api_key)) -> dict[str, Any]:
    _record_request(key_record)
    _reserve_page_usage(key_record, 1)
    result = extract_invoice_fields(request.text)
    result["source"] = {"type": "text", "ocr_used": False}
    return result


@app.post("/v1/extract-file")
async def extract_file(file: UploadFile = File(...), key_record: dict[str, Any] = Depends(require_api_key)) -> dict[str, Any]:
    # Rate-limit every attempt, but only reserve billable page units after the
    # upload is validated and its page count is known.
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

    page_units = await run_in_threadpool(_preflight_page_count, data, suffix)
    reservation_id = _reserve_page_usage(key_record, page_units)
    try:
        # All PDF parsing, image decoding and OCR run off the ASGI event loop.
        # Wait asynchronously for a file slot so queued uploads do not consume
        # worker threads or starve synchronous endpoints.
        async with _FILE_PROCESSING_SEMAPHORE:
            text, ocr_used, page_count, source_type = await run_in_threadpool(
                _process_file, data, suffix, filename
            )
        if not text.strip():
            raise HTTPException(status_code=422, detail="No readable text was found. Try a clearer scan or higher-resolution photo.")
        result = extract_invoice_fields(text)
        result["source"] = {"type": source_type, "filename": filename, "ocr_used": ocr_used, "pages": page_count}
        return result
    except Exception:
        release_usage_reservation(key_record["id"], reservation_id)
        raise


@app.post("/v1/extract-pdf", include_in_schema=False)
async def extract_pdf_legacy(file: UploadFile = File(...), key_record: dict[str, Any] = Depends(require_api_key)) -> dict[str, Any]:
    return await extract_file(file, key_record)
