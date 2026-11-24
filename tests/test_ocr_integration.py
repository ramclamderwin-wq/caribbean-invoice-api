import io
import shutil

from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.extraction import extract_invoice_fields
from app.main import _extract_pdf, _ocr_image


pytestmark = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="Tesseract OCR engine is not installed",
)


def make_invoice_image():
    image = Image.new("RGB", (1800, 1100), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 52
    )
    lines = [
        "ACME INDUSTRIAL SUPPLIES",
        "INVOICE",
        "Invoice No: TEST-2026-105",
        "Invoice Date: 2026-11-20",
        "Currency: USD",
        "Subtotal: 100.00",
        "Tax: 8.00",
        "Grand Total: 108.00",
    ]
    y = 90
    for line in lines:
        draw.text((100, y), line, fill="black", font=font)
        y += 115
    return image


def test_tesseract_reads_invoice_photo_and_fields():
    image = make_invoice_image()
    text = _ocr_image(image)
    result = extract_invoice_fields(text)

    assert "ACME" in text.upper()
    assert result["fields"]["invoice_number"] == "TEST-2026-105"
    assert result["fields"]["total"] == "108.00"
    assert result["fields"]["currency"] == "USD"
    assert result["review_required"] is True


def test_tesseract_reads_scanned_pdf():
    image = make_invoice_image()
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")

    pdf_buffer = io.BytesIO()
    pdf = canvas.Canvas(pdf_buffer, pagesize=(900, 550))
    pdf.drawImage(ImageReader(io.BytesIO(image_bytes.getvalue())), 0, 0, width=900, height=550)
    pdf.save()
    pdf_bytes = pdf_buffer.getvalue()

    text, ocr_used, page_count = _extract_pdf(pdf_bytes)
    result = extract_invoice_fields(text)

    assert ocr_used is True
    assert page_count == 1
    assert result["fields"]["invoice_number"] == "TEST-2026-105"
    assert result["fields"]["total"] == "108.00"
