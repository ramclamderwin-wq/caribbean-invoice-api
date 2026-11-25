# Third-party software notices

## pypdfium2 and PDFium

The application uses pypdfium2 for PDF text extraction and rasterization instead of PyMuPDF.

The pypdfium2 project states that its code is available under Apache-2.0 or BSD-3-Clause, and PDFium is available under a BSD-style license. PDFium bundles dependencies with additional licenses; pypdfium2's distribution includes the corresponding license materials. The Docker build copies the exact installed wheel's `.dist-info/licenses/` contents, including `BUILD_LICENSES/`, into `/app/THIRD_PARTY_LICENSES/pypdfium2/`. The build fails if the wheel does not expose PDFium BUILD_LICENSES. Verify this directory in the built image and retain it with every redistributed image.

References:
- https://pypdfium2-team.github.io/pypdfium2/readme.html
- https://pypdfium2-team.github.io/pypdfium2/python_api.html

This notice is informational, not legal advice. Confirm the precise dependency/build licensing with qualified counsel before commercial launch.

## ReportLab

ReportLab is used only in development tests to create synthetic PDF fixtures. It is not installed in the production requirements.

## Other runtime dependencies

All other Python runtime dependencies are under permissive licences (MIT, BSD,
Apache-2.0, PSF, MIT-CMU), except `certifi` (MPL-2.0, used unmodified). This
includes `boto3`/`botocore`/`s3transfer` (Apache-2.0), used only for optional
offsite backup upload. Tesseract OCR (Apache-2.0) is installed from Debian
packages in the Docker image. See `COMMERCIAL_LAUNCH_PLAN.md` §9 for the
2026-11-25 licence audit; re-run `pip-licenses` whenever dependencies change.
