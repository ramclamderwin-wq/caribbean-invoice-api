from __future__ import annotations

import io
import os
import re
import shutil
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import fitz
import pytesseract
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

APP_NAME = "Caribbean Invoice Intelligence API"
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
MAX_PDF_PAGES = int(os.getenv("MAX_PDF_PAGES", "20"))
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "25000000"))
TESSERACT_CMD = os.getenv("TESSERACT_CMD")
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

app = FastAPI(
    title=APP_NAME,
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
        [r"(?:invoice\s*(?:number|no\.?|#|num(?:ber)?)|inv\s*#?)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{1,})"],
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
                rf"\b(?:{labels})\b\s*[:\-]?\s*(?:BZD|USD|BZ\$|\$)?\s*([(\-]?\s*\d[\d,]*(?:\.\d{1,4})?\s*\)?)"
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
    return {"name": APP_NAME, "version": "0.2.0", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "caribbean-invoice-api"}


@app.post("/v1/extract-text")
def extract_text(request: TextRequest) -> dict[str, Any]:
    result = extract_invoice_fields(request.text)
    result["source"] = {"type": "text", "ocr_used": False}
    return result


@app.post("/v1/extract-file")
async def extract_file(file: UploadFile = File(...)) -> dict[str, Any]:
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
    return result


@app.post("/v1/extract-pdf", include_in_schema=False)
async def extract_pdf_legacy(file: UploadFile = File(...)) -> dict[str, Any]:
    return await extract_file(file)
