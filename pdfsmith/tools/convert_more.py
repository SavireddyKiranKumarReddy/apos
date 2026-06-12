"""More conversions: HTML → PDF, PDF → PowerPoint, PDF → Excel, PDF → PDF/A."""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

import pypdfium2 as pdfium

from pdfsmith.tools.helpers import ToolError, safe_stem
from pdfsmith.tools.registry import Option, Tool, ToolResult, UploadedFile, register
from pdfsmith.tools.transform import ghostscript_path

PPTX_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _ensure_macos_lib_path() -> None:
    """WeasyPrint loads pango/cairo/gobject through ctypes, which on macOS only
    searches a few default directories — Homebrew installs to /opt/homebrew/lib
    (Apple Silicon) or /usr/local/lib (Intel), neither of which is searched.
    Add them to DYLD_FALLBACK_LIBRARY_PATH before the first import so HTML → PDF
    lights up the moment ``brew install pango`` is done, with no env tweaking."""
    import os
    import sys

    if sys.platform != "darwin":
        return
    existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    parts = existing.split(":") if existing else []
    for brew_lib in ("/opt/homebrew/lib", "/usr/local/lib"):
        if os.path.isdir(brew_lib) and brew_lib not in parts:
            parts.append(brew_lib)
    # macOS keeps the user-home fallback when the variable is unset; preserve it.
    if not existing and "~/lib" not in parts:
        parts.append(os.path.expanduser("~/lib"))
    os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(parts)


def weasyprint_available() -> bool:
    import contextlib

    _ensure_macos_lib_path()
    try:
        # WeasyPrint prints a loud banner to stderr when its native libraries
        # are missing; the availability probe runs on every /api/tools call,
        # so keep it quiet.
        with contextlib.redirect_stderr(io.StringIO()):
            import weasyprint  # noqa: F401
        return True
    except Exception:
        return False


def run_html_to_pdf(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    _ensure_macos_lib_path()
    if not weasyprint_available():
        raise ToolError("HTML rendering needs WeasyPrint's system libraries")
    from weasyprint import HTML

    def offline_fetcher(url, *args, **kwargs):
        # Embedded data: URIs are handled before the fetcher; anything that
        # reaches here is a network fetch, which we refuse — no SSRF, no
        # surprise traffic from rendering an untrusted file.
        raise ValueError(f"external resources are disabled ({url})")

    html = uploaded.data.decode("utf-8", errors="replace")
    try:
        data = HTML(string=html, url_fetcher=offline_fetcher).write_pdf()
    except Exception as exc:
        raise ToolError(f"could not render this HTML: {exc}") from exc
    return ToolResult(f"{safe_stem(uploaded.name)}.pdf", data)


def run_pdf_to_powerpoint(files: list[UploadedFile], options: dict) -> ToolResult:
    """Each page becomes a full-bleed slide image — faithful layout, robust on
    any PDF (the same approach the popular converters use for non-trivial
    documents)."""
    (uploaded,) = files
    from pptx import Presentation
    from pptx.util import Emu

    try:
        document = pdfium.PdfDocument(uploaded.data)
    except Exception as exc:
        raise ToolError("that file does not look like a valid PDF") from exc

    try:
        first = document[0]
        width_pt, height_pt = first.get_size()
        presentation = Presentation()
        presentation.slide_width = Emu(int(width_pt * 12700))
        presentation.slide_height = Emu(int(height_pt * 12700))
        blank = presentation.slide_layouts[6]

        for index in range(len(document)):
            image = document[index].render(scale=150 / 72).to_pil()
            png = io.BytesIO()
            image.save(png, format="PNG")
            png.seek(0)
            slide = presentation.slides.add_slide(blank)
            slide.shapes.add_picture(png, 0, 0,
                                     width=presentation.slide_width,
                                     height=presentation.slide_height)
    finally:
        document.close()

    output = io.BytesIO()
    presentation.save(output)
    return ToolResult(f"{safe_stem(uploaded.name)}.pptx", output.getvalue(), PPTX_TYPE)


def run_pdf_to_excel(files: list[UploadedFile], options: dict) -> ToolResult:
    """Detected tables become rows per sheet (one sheet per page); pages
    without detectable tables fall back to their text, one line per row."""
    (uploaded,) = files
    import pdfplumber
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.remove(workbook.active)
    try:
        with pdfplumber.open(io.BytesIO(uploaded.data)) as pdf:
            for number, page in enumerate(pdf.pages, start=1):
                sheet = workbook.create_sheet(f"Page {number}")
                row_cursor = 1
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        for row in table:
                            for column, value in enumerate(row, start=1):
                                sheet.cell(row=row_cursor, column=column,
                                           value=value if value is not None else "")
                            row_cursor += 1
                        row_cursor += 1  # blank row between tables
                else:
                    for line in (page.extract_text() or "").splitlines():
                        sheet.cell(row=row_cursor, column=1, value=line)
                        row_cursor += 1
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError("could not read tables from this PDF") from exc

    output = io.BytesIO()
    workbook.save(output)
    return ToolResult(f"{safe_stem(uploaded.name)}.xlsx", output.getvalue(), XLSX_TYPE)


def run_pdf_to_pdfa(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    gs = ghostscript_path()
    if not gs:
        raise ToolError("PDF/A conversion needs Ghostscript on the server")
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "in.pdf"
        target = Path(tmp) / "out.pdf"
        source.write_bytes(uploaded.data)
        completed = subprocess.run(
            [gs, "-dPDFA=2", "-dBATCH", "-dNOPAUSE", "-dQUIET",
             "-sColorConversionStrategy=RGB", "-sDEVICE=pdfwrite",
             "-dPDFACompatibilityPolicy=1",
             f"-sOutputFile={target}", str(source)],
            capture_output=True,
            timeout=300,
        )
        if completed.returncode != 0 or not target.exists():
            raise ToolError("Ghostscript could not convert this PDF to PDF/A")
        return ToolResult(f"{safe_stem(uploaded.name)}_pdfa.pdf", target.read_bytes())


register(Tool(
    name="html_to_pdf",
    label="HTML → PDF",
    description="Render an HTML file to PDF (offline — external resources disabled).",
    icon="🌐",
    run=run_html_to_pdf,
    accepts=".html,.htm",
    available=weasyprint_available,
    unavailable_hint="needs WeasyPrint's pango/cairo — included in the Docker image",
    category="convert",
))

register(Tool(
    name="pdf_to_powerpoint",
    produces_pdf=False,
    label="PDF → PowerPoint",
    description="One faithful full-bleed slide per page (.pptx).",
    icon="📽️",
    run=run_pdf_to_powerpoint,
    category="convert",
))

register(Tool(
    name="pdf_to_excel",
    produces_pdf=False,
    label="PDF → Excel",
    description="Extract detected tables into .xlsx, one sheet per page.",
    icon="📊",
    run=run_pdf_to_excel,
    category="convert",
))

register(Tool(
    name="pdf_to_pdfa",
    label="PDF → PDF/A",
    description="Convert to the ISO archival format via Ghostscript.",
    icon="🗄️",
    run=run_pdf_to_pdfa,
    available=lambda: ghostscript_path() is not None,
    unavailable_hint="needs Ghostscript — included in the Docker image",
    category="convert",
))
