# Advanced Professional Suite - Full-fat image with all tools
# Includes Ghostscript, LibreOffice, and Tesseract OCR
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp \
    APP_NAME="Advanced Professional Suite"

RUN apt-get update && apt-get install -y --no-install-recommends \
        ghostscript \
        tesseract-ocr \
        tesseract-ocr-eng \
        libreoffice-writer-nogui \
        libreoffice-calc-nogui \
        libreoffice-impress-nogui \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        fonts-dejavu-core \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY pdfsmith ./pdfsmith
COPY static ./static
RUN pip install --no-cache-dir ".[ocr,ai]"

EXPOSE 8000

RUN useradd --create-home --uid 1000 appuser
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"]

CMD ["uvicorn", "pdfsmith.api:app", "--host", "0.0.0.0", "--port", "8000"]
