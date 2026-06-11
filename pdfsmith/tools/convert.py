"""Conversions: images ↔ PDF, PDF → Word, Office → PDF, OCR, text extraction."""

from __future__ import annotations

import importlib.util
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

import img2pdf
import pypdfium2 as pdfium

from pdfsmith.tools.helpers import ToolError, read_pdf, safe_stem, zip_files
from pdfsmith.tools.registry import Option, Tool, ToolResult, UploadedFile, register

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def run_images_to_pdf(files: list[UploadedFile], options: dict) -> ToolResult:
    if not files:
        raise ToolError("add at least one image")
    payloads = []
    for uploaded in files:
        try:
            payloads.append(img2pdf.convert(uploaded.data))
        except Exception:
            # img2pdf refuses alpha channels; flatten through Pillow and retry.
            try:
                from PIL import Image

                with Image.open(io.BytesIO(uploaded.data)) as image:
                    buffer = io.BytesIO()
                    image.convert("RGB").save(buffer, format="JPEG", quality=92)
                payloads.append(img2pdf.convert(buffer.getvalue()))
            except Exception as exc:
                raise ToolError(f"{uploaded.name} is not an image format I can read") from exc

    import pypdf

    writer = pypdf.PdfWriter()
    for payload in payloads:
        for page in pypdf.PdfReader(io.BytesIO(payload)).pages:
            writer.add_page(page)
    buffer = io.BytesIO()
    writer.write(buffer)
    return ToolResult("images.pdf", buffer.getvalue())


def run_pdf_to_images(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    image_format = options.get("format", "png")
    dpi = int(options.get("dpi", 150))
    if dpi not in (72, 150, 300):
        raise ToolError("dpi must be 72, 150 or 300")
    stem = safe_stem(uploaded.name)

    try:
        document = pdfium.PdfDocument(uploaded.data)
    except Exception as exc:
        raise ToolError("that file does not look like a valid PDF") from exc

    entries = []
    try:
        for index in range(len(document)):
            bitmap = document[index].render(scale=dpi / 72)
            image = bitmap.to_pil()
            buffer = io.BytesIO()
            if image_format == "jpg":
                image.convert("RGB").save(buffer, format="JPEG", quality=90)
            else:
                image.save(buffer, format="PNG")
            entries.append((f"{stem}_page_{index + 1:03d}.{image_format}", buffer.getvalue()))
    finally:
        document.close()

    if len(entries) == 1:
        name, data = entries[0]
        return ToolResult(name, data, "image/jpeg" if image_format == "jpg" else "image/png")
    return ToolResult(f"{stem}_images.zip", zip_files(entries), "application/zip")


def run_pdf_to_word(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    from pdf2docx import Converter  # heavy import (opencv); keep it lazy

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "in.pdf"
        target = Path(tmp) / "out.docx"
        source.write_bytes(uploaded.data)
        try:
            converter = Converter(str(source))
            converter.convert(str(target))
            converter.close()
        except Exception as exc:
            raise ToolError("could not convert this PDF to Word") from exc
        return ToolResult(f"{safe_stem(uploaded.name)}.docx", target.read_bytes(), DOCX_TYPE)


def soffice_path() -> str | None:
    for candidate in ("soffice", "libreoffice"):
        found = shutil.which(candidate)
        if found:
            return found
    mac_app = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    return str(mac_app) if mac_app.exists() else None


def run_office_to_pdf(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    soffice = soffice_path()
    if not soffice:
        raise ToolError("LibreOffice is not installed on this server")
    suffix = Path(uploaded.name).suffix.lower() or ".docx"
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / f"in{suffix}"
        source.write_bytes(uploaded.data)
        completed = subprocess.run(
            [soffice, "--headless", "--norestore", "--convert-to", "pdf",
             "--outdir", tmp, str(source)],
            capture_output=True,
            timeout=300,
        )
        target = Path(tmp) / "in.pdf"
        if completed.returncode != 0 or not target.exists():
            raise ToolError("LibreOffice could not convert this document")
        return ToolResult(f"{safe_stem(uploaded.name)}.pdf", target.read_bytes())


def ocr_available() -> bool:
    return importlib.util.find_spec("ocrmypdf") is not None and shutil.which("tesseract") is not None


def run_ocr(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    if not ocr_available():
        raise ToolError("OCR needs ocrmypdf and tesseract on the server")
    import ocrmypdf

    language = options.get("language", "eng")
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "in.pdf"
        target = Path(tmp) / "out.pdf"
        source.write_bytes(uploaded.data)
        try:
            ocrmypdf.ocr(str(source), str(target), language=language, skip_text=True,
                         progress_bar=False)
        except Exception as exc:
            raise ToolError(f"OCR failed: {exc}") from exc
        return ToolResult(f"{safe_stem(uploaded.name)}_searchable.pdf", target.read_bytes())


def run_extract_text(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    reader = read_pdf(uploaded.data)
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n\n----- page break -----\n\n".join(pages).strip() + "\n"
    return ToolResult(f"{safe_stem(uploaded.name)}.txt", text.encode(), "text/plain")


register(Tool(
    name="images_to_pdf",
    label="Images → PDF",
    description="Bundle JPG/PNG photos into one tidy PDF.",
    icon="🖼️",
    run=run_images_to_pdf,
    accepts="image/*",
    multiple=True,
    category="convert",
))

register(Tool(
    name="pdf_to_images",
    label="PDF → Images",
    description="Render pages to crisp PNG or JPG.",
    icon="📸",
    run=run_pdf_to_images,
    options=(
        Option("format", "Format", kind="select", default="png",
               choices=(("png", "PNG"), ("jpg", "JPG"))),
        Option("dpi", "Quality", kind="select", default="150",
               choices=(("72", "72 dpi (screen)"), ("150", "150 dpi (sharp)"),
                        ("300", "300 dpi (print)"))),
    ),
    category="convert",
))

register(Tool(
    name="pdf_to_word",
    label="PDF → Word",
    description="Turn a PDF into an editable .docx.",
    icon="📝",
    run=run_pdf_to_word,
    category="convert",
))

register(Tool(
    name="office_to_pdf",
    label="Office → PDF",
    description="Word, Excel, PowerPoint and OpenDocument to PDF.",
    icon="📄",
    run=run_office_to_pdf,
    accepts=".doc,.docx,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.odp,.rtf,.txt",
    available=lambda: soffice_path() is not None,
    unavailable_hint="needs LibreOffice — included in the Docker image",
    category="convert",
))

register(Tool(
    name="ocr",
    label="OCR PDF",
    description="Make scanned PDFs searchable and copyable.",
    icon="🔍",
    run=run_ocr,
    options=(
        Option("language", "Language", kind="select", default="eng",
               choices=(("eng", "English"), ("hin", "Hindi"), ("deu", "German"),
                        ("fra", "French"), ("spa", "Spanish"))),
    ),
    available=ocr_available,
    unavailable_hint="needs tesseract + ocrmypdf — included in the Docker image",
    category="convert",
))

register(Tool(
    name="extract_text",
    label="Extract text",
    description="Pull all text out of a PDF as a .txt file.",
    icon="📜",
    run=run_extract_text,
    category="convert",
))
