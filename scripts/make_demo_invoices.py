#!/usr/bin/env python3
"""Generate SYNTHETIC commercial invoices for demonstrations and tests.

    python scripts/make_demo_invoices.py demo/invoices

All companies, numbers and goods are fictional. Every document carries a
"SYNTHETIC DEMO" footer. Never present these as customer documents or use them
for accuracy claims. Requires the dev dependency ``reportlab``.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

FOOTER = "SYNTHETIC DEMO DOCUMENT - fictional companies and values - not a real invoice"

INVOICES = {
    "demo-001-en-standard.pdf": """Demo Bright Tools Co., Ltd.
COMMERCIAL INVOICE
Invoice No: DBT-2026-0412
Date: 2026-04-12
Seller: Demo Bright Tools Co., Ltd.
No. 8 Example Industrial Rd, Shenzhen, China
Buyer: Sample Hardware Imports Inc.
100 Example Ave, Houston, TX, USA
Incoterm: FOB Shenzhen
Country of Origin: China
Item Code Description HS Code Origin Qty Unit Price Amount
DB-100 Cordless drill 18V 8467.21 CN 50 pcs 32.50 1,625.00
DB-220 Drill bit set 10pc 8207.50 CN 200 sets 4.25 850.00
DB-310 Safety goggles 9004.90 CN 120 pcs 1.10 132.00
DB-415 Work gloves size L 6116.10 CN 300 pairs 0.85 255.00
Subtotal: USD 2,862.00
Freight: USD 180.00
Insurance: USD 25.00
Total: USD 3,067.00""",
    "demo-002-es-factura.pdf": """Distribuidora Ejemplo S.A. de C.V.
FACTURA COMERCIAL
Factura No: DE-7781
Fecha: 15 de marzo de 2026
Vendedor: Distribuidora Ejemplo S.A. de C.V.
Av. Demostración 45, Monterrey, México
Comprador: Importadora Muestra S.A.S.
Calle 10 # 20-30, Bogotá, Colombia
Incoterm: CIF Cartagena
Descripción Cantidad Precio Importe
Café molido 500g 100 3.20 320.00
Azúcar morena 1kg 50 1.80 90.00
Chocolate de mesa 250g 80 2.10 168.00
Subtotal: USD 578.00
Flete: USD 40.00
Total: USD 618.00""",
    "demo-003-eur-comma-decimals.pdf": """Beispiel Maschinenteile GmbH
COMMERCIAL INVOICE
Invoice Number: BM-2026-118
Date: 3 March 2026
Seller: Beispiel Maschinenteile GmbH
Musterstrasse 1, Stuttgart, Germany
Buyer: Example Engineering Supplies Ltd.
Unit 4 Sample Park, Leeds, United Kingdom
Incoterm: DAP Leeds
Part No Description Qty Unit Price Amount
BM-77 Ball bearing 6204 400 pcs 1,25 500,00
BM-81 Hydraulic seal kit 25 sets 18,40 460,00
Subtotal: EUR 960,00
VAT 0%: EUR 0,00
Total: EUR 960,00""",
    "demo-004-with-errors.pdf": """Sample Textiles Trading Co.
COMMERCIAL INVOICE
Invoice No: STT-0099
Date: 2026-05-20
Description Qty Unit Price Amount
Cotton T-shirt white 500 2.40 1,250.00
Cotton T-shirt black 300 2.40 720.00
Subtotal: USD 2,100.00
Total: USD 2,100.00""",
}
SCANNED = ("demo-005-scanned-image.png", """Example Ceramics Export Ltd.
COMMERCIAL INVOICE
Invoice No: ECE-5531
Date: 2026-02-09
Buyer: Demo Home Goods Pty Ltd
Description Qty Unit Price Amount
Ceramic dinner plate 27cm 240 3.50 840.00
Ceramic mug 350ml 360 1.75 630.00
Subtotal: USD 1,470.00
Total: USD 1,470.00""")


def _pdf_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle("Synthetic demo invoice")
    y = 800
    for line in text.splitlines():
        pdf.setFont("Helvetica-Bold" if line.isupper() else "Helvetica", 11)
        pdf.drawString(50, y, line)
        y -= 18
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(50, 40, FOOTER)
    pdf.save()
    return buffer.getvalue()


def make(out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in INVOICES.items():
        path = out / name
        path.write_bytes(_pdf_bytes(text))
        written.append(path)
    # A "scan": render a PDF page to an image so the pipeline must use OCR.
    import pypdfium2 as pdfium
    name, text = SCANNED
    document = pdfium.PdfDocument(_pdf_bytes(text))
    try:
        page = document[0]
        image = page.render(scale=2).to_pil().convert("L")
        page.close()
    finally:
        document.close()
    path = out / name
    image.save(path)
    written.append(path)
    return written


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "demo/invoices"
    for p in make(target):
        print(p)
