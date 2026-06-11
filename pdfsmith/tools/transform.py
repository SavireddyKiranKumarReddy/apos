"""Page decoration and size reduction: watermark, page numbers, compress."""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

import pikepdf
import pypdf
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas as rl_canvas

from pdfsmith.tools.helpers import ToolError, parse_int, read_pdf, safe_stem, writer_bytes
from pdfsmith.tools.registry import Option, Tool, ToolResult, UploadedFile, register


def _overlay(width: float, height: float, draw) -> pypdf.PageObject:
    """Build a one-page overlay PDF of the given size with reportlab."""
    buffer = io.BytesIO()
    canvas = rl_canvas.Canvas(buffer, pagesize=(width, height))
    draw(canvas, width, height)
    canvas.save()
    return pypdf.PdfReader(io.BytesIO(buffer.getvalue())).pages[0]


def run_watermark(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    text = str(options.get("text", "")).strip()
    if not text:
        raise ToolError("watermark text is empty")
    opacity = parse_int(options, "opacity", 18, 3, 100) / 100
    placement = options.get("placement", "diagonal")

    reader = read_pdf(uploaded.data)
    writer = pypdf.PdfWriter()
    overlays: dict[tuple[float, float], pypdf.PageObject] = {}

    def draw(canvas, width, height):
        size = max(18, min(width, height) / max(len(text), 6) * 1.6)
        canvas.setFont("Helvetica-Bold", size)
        canvas.setFillColor(Color(0.35, 0.35, 0.4, alpha=opacity))
        if placement == "diagonal":
            canvas.saveState()
            canvas.translate(width / 2, height / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, text)
            canvas.restoreState()
        elif placement == "top":
            canvas.drawCentredString(width / 2, height - size * 1.4, text)
        else:  # bottom
            canvas.drawCentredString(width / 2, size * 0.8, text)

    for page in reader.pages:
        key = (float(page.mediabox.width), float(page.mediabox.height))
        if key not in overlays:
            overlays[key] = _overlay(*key, draw)
        page.merge_page(overlays[key])
        writer.add_page(page)
    return ToolResult(f"{safe_stem(uploaded.name)}_watermarked.pdf", writer_bytes(writer))


def run_page_numbers(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    reader = read_pdf(uploaded.data)
    start = parse_int(options, "start", 1, 1, 10_000)
    position = options.get("position", "bottom-center")
    total = len(reader.pages)
    show_total = str(options.get("show_total", "")).lower() in ("true", "on", "1", "yes")

    writer = pypdf.PdfWriter()
    for index, page in enumerate(reader.pages):
        number = start + index
        label = f"{number} / {start + total - 1}" if show_total else str(number)
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)

        def draw(canvas, w, h, label=label):
            canvas.setFont("Helvetica", 10)
            canvas.setFillColor(Color(0.25, 0.25, 0.3, alpha=0.9))
            y = 18 if position.startswith("bottom") else h - 26
            if position.endswith("center"):
                canvas.drawCentredString(w / 2, y, label)
            elif position.endswith("right"):
                canvas.drawRightString(w - 36, y, label)
            else:
                canvas.drawString(36, y, label)

        page.merge_page(_overlay(width, height, draw))
        writer.add_page(page)
    return ToolResult(f"{safe_stem(uploaded.name)}_numbered.pdf", writer_bytes(writer))


def ghostscript_path() -> str | None:
    return shutil.which("gs")


_GS_PRESETS = {"balanced": "/ebook", "strong": "/screen"}


def run_compress(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    level = options.get("level", "lossless")
    stem = safe_stem(uploaded.name)

    if level in _GS_PRESETS:
        gs = ghostscript_path()
        if not gs:
            raise ToolError(
                "balanced/strong compression needs Ghostscript on the server — "
                "choose lossless, or run the Docker image which bundles it"
            )
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.pdf"
            target = Path(tmp) / "out.pdf"
            source.write_bytes(uploaded.data)
            completed = subprocess.run(
                [gs, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.6",
                 f"-dPDFSETTINGS={_GS_PRESETS[level]}", "-dNOPAUSE", "-dBATCH",
                 "-dQUIET", f"-sOutputFile={target}", str(source)],
                capture_output=True,
                timeout=300,
            )
            if completed.returncode != 0 or not target.exists():
                raise ToolError("Ghostscript could not process this PDF")
            data = target.read_bytes()
    else:
        try:
            with pikepdf.open(io.BytesIO(uploaded.data)) as pdf:
                buffer = io.BytesIO()
                pdf.save(
                    buffer,
                    compress_streams=True,
                    object_stream_mode=pikepdf.ObjectStreamMode.generate,
                    recompress_flate=True,
                )
                data = buffer.getvalue()
        except pikepdf.PasswordError:
            raise ToolError("this PDF is password-protected — unlock it first") from None
        except pikepdf.PdfError as exc:
            raise ToolError("that file does not look like a valid PDF") from exc

    # Never hand back a bigger file than the one we received.
    if len(data) >= len(uploaded.data):
        data = uploaded.data
    return ToolResult(f"{stem}_compressed.pdf", data)


register(Tool(
    name="compress",
    label="Compress PDF",
    description="Shrink file size — losslessly, or harder via Ghostscript.",
    icon="🗜️",
    run=run_compress,
    options=(
        Option("level", "Level", kind="select", default="lossless",
               choices=(("lossless", "Lossless (always available)"),
                        ("balanced", "Balanced (Ghostscript)"),
                        ("strong", "Strong (Ghostscript)")),
               help="Balanced/strong re-encode images and need Ghostscript"),
    ),
    category="optimize",
))

register(Tool(
    name="watermark",
    label="Watermark",
    description="Stamp translucent text across every page.",
    icon="💧",
    run=run_watermark,
    options=(
        Option("text", "Watermark text", default="CONFIDENTIAL"),
        Option("placement", "Placement", kind="select", default="diagonal",
               choices=(("diagonal", "Diagonal"), ("top", "Top"), ("bottom", "Bottom"))),
        Option("opacity", "Opacity %", kind="number", default=18),
    ),
    category="edit",
))

register(Tool(
    name="page_numbers",
    label="Page numbers",
    description="Add clean page numbers exactly where you want them.",
    icon="🔢",
    run=run_page_numbers,
    options=(
        Option("position", "Position", kind="select", default="bottom-center",
               choices=(("bottom-center", "Bottom center"), ("bottom-right", "Bottom right"),
                        ("bottom-left", "Bottom left"), ("top-right", "Top right"))),
        Option("start", "Start at", kind="number", default=1),
        Option("show_total", "Show total (1 / 12)", kind="checkbox", default=False),
    ),
    category="edit",
))
