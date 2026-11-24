# Third-party software notices

## pypdfium2 and PDFium

The application uses pypdfium2 for PDF text extraction and rasterization instead of PyMuPDF.

The pypdfium2 project states that its code is available under Apache-2.0 or BSD-3-Clause, and PDFium is available under a BSD-style license. PDFium bundles dependencies with additional licenses; pypdfium2's distribution includes the corresponding license materials. The exact wheel/build and all bundled notices must be retained and reviewed before redistributing the container image.

References:
- https://pypdfium2-team.github.io/pypdfium2/readme.html
- https://pypdfium2-team.github.io/pypdfium2/python_api.html

This notice is informational, not legal advice. Confirm the precise dependency/build licensing with qualified counsel before commercial launch.

## ReportLab

ReportLab is used only in development tests to create synthetic PDF fixtures. It is not installed in the production requirements.
