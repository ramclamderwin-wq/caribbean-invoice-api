FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-spa gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python - <<'PY'
from importlib.metadata import distribution
from pathlib import Path
import shutil

dist = distribution("pypdfium2")
files = list(dist.files or [])
license_files = [
    item for item in files
    if ".dist-info/licenses/" in str(item).replace("\\", "/")
]
if not any("BUILD_LICENSES" in str(item) for item in license_files):
    raise SystemExit("pypdfium2 wheel did not expose PDFium BUILD_LICENSES; refusing to build an unnoted image")
target = Path("/app/THIRD_PARTY_LICENSES/pypdfium2")
for item in license_files:
    source = Path(dist.locate_file(item))
    if source.is_file():
        relative = Path(str(item).split(".dist-info/licenses/", 1)[1])
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
PY

COPY app ./app
COPY THIRD_PARTY_NOTICES.md .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /var/data \
    && chown -R appuser:appuser /app \
    && chmod 755 /usr/local/bin/docker-entrypoint.sh
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
