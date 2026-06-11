"""Visual editing: overlay editor, crop, remove pages, rasterizing redaction.

The edit tool consumes elements placed in the browser on a rendered page.
Coordinates arrive as fractions of the page size measured from the top-left
(the natural screen frame) and are converted to PDF points from the
bottom-left here. Redaction deliberately rasterizes affected pages so the
text underneath the boxes is *gone*, not hidden.
"""

from __future__ import annotations

import io
import json

import img2pdf
import pypdf
import pypdfium2 as pdfium
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from pdfsmith.tools.helpers import (
    ToolError,
    parse_page_ranges,
    read_pdf,
    safe_stem,
    writer_bytes,
)
from pdfsmith.tools.registry import Option, Tool, ToolResult, UploadedFile, register

REDACT_DPI = 200


def _parse_elements(options: dict, key: str) -> list[dict]:
    raw = options.get(key, "[]")
    try:
        elements = json.loads(raw)
    except json.JSONDecodeError:
        raise ToolError(f"{key} must be valid JSON") from None
    if not isinstance(elements, list) or not elements:
        raise ToolError("nothing to apply — add elements first")
    return elements


def _color(value: str) -> HexColor:
    try:
        return HexColor(value if value.startswith("#") else f"#{value}")
    except Exception:
        raise ToolError(f"bad color {value!r}") from None


def run_edit(files: list[UploadedFile], options: dict) -> ToolResult:
    pdf_file, images = files[0], files[1:]
    elements = _parse_elements(options, "elements")
    reader = read_pdf(pdf_file.data)

    by_page: dict[int, list[dict]] = {}
    for element in elements:
        page_number = int(element.get("page", 1))
        if not 1 <= page_number <= len(reader.pages):
            raise ToolError(f"element on page {page_number}, but the document has "
                            f"{len(reader.pages)} pages")
        by_page.setdefault(page_number - 1, []).append(element)

    writer = pypdf.PdfWriter()
    for index, page in enumerate(reader.pages):
        todo = by_page.get(index)
        if todo:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            buffer = io.BytesIO()
            canvas = rl_canvas.Canvas(buffer, pagesize=(width, height))
            for element in todo:
                _draw_element(canvas, element, width, height, images)
            canvas.save()
            overlay = pypdf.PdfReader(io.BytesIO(buffer.getvalue())).pages[0]
            page.merge_page(overlay)
        writer.add_page(page)
    return ToolResult(f"{safe_stem(pdf_file.name)}_edited.pdf", writer_bytes(writer))


def _draw_element(canvas, element: dict, width: float, height: float,
                  images: list[UploadedFile]) -> None:
    kind = element.get("type")
    x = float(element.get("x", 0)) * width
    y_top = float(element.get("y", 0)) * height

    if kind == "text":
        text = str(element.get("text", "")).strip()
        if not text:
            return
        size = max(6.0, min(96.0, float(element.get("size", 14))))
        canvas.setFont("Helvetica", size)
        canvas.setFillColor(_color(element.get("color", "#111111")))
        for line_number, line in enumerate(text.splitlines()):
            canvas.drawString(x, height - y_top - size * (line_number + 1), line)
    elif kind == "rect":
        w = float(element.get("w", 0.1)) * width
        h = float(element.get("h", 0.05)) * height
        color = _color(element.get("color", "#ffffff"))
        color.alpha = max(0.05, min(1.0, float(element.get("opacity", 1.0))))
        canvas.setFillColor(color)
        canvas.rect(x, height - y_top - h, w, h, stroke=0, fill=1)
    elif kind == "image":
        file_index = int(element.get("file", 0))
        if not 0 <= file_index < len(images):
            raise ToolError("an image element points at a missing upload")
        w = float(element.get("w", 0.25)) * width
        h = float(element.get("h", 0.15)) * height
        canvas.drawImage(
            ImageReader(io.BytesIO(images[file_index].data)),
            x, height - y_top - h, width=w, height=h,
            preserveAspectRatio=False, mask="auto",
        )
    else:
        raise ToolError(f"unknown element type {kind!r}")


MM_TO_PT = 72 / 25.4


def run_crop(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    reader = read_pdf(uploaded.data)
    margins = {}
    for side in ("top", "right", "bottom", "left"):
        try:
            margins[side] = max(0.0, float(options.get(side, 0) or 0)) * MM_TO_PT
        except ValueError:
            raise ToolError(f"{side} margin must be a number (mm)") from None
    if not any(margins.values()):
        raise ToolError("all margins are zero — nothing to crop")

    pages_spec = str(options.get("pages", "")).strip()
    targets = (
        set(parse_page_ranges(pages_spec, len(reader.pages)))
        if pages_spec
        else set(range(len(reader.pages)))
    )

    writer = pypdf.PdfWriter()
    for index, page in enumerate(reader.pages):
        if index in targets:
            box = page.mediabox
            new_box = (
                float(box.left) + margins["left"],
                float(box.bottom) + margins["bottom"],
                float(box.right) - margins["right"],
                float(box.top) - margins["top"],
            )
            if new_box[2] - new_box[0] < 36 or new_box[3] - new_box[1] < 36:
                raise ToolError("those margins would crop the page away entirely")
            for target_box in (page.mediabox, page.cropbox):
                target_box.lower_left = new_box[:2]
                target_box.upper_right = new_box[2:]
        writer.add_page(page)
    return ToolResult(f"{safe_stem(uploaded.name)}_cropped.pdf", writer_bytes(writer))


def run_remove_pages(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    reader = read_pdf(uploaded.data)
    doomed = set(parse_page_ranges(options.get("pages", ""), len(reader.pages)))
    if len(doomed) >= len(reader.pages):
        raise ToolError("that would remove every page")
    writer = pypdf.PdfWriter()
    for index, page in enumerate(reader.pages):
        if index not in doomed:
            writer.add_page(page)
    return ToolResult(f"{safe_stem(uploaded.name)}_removed.pdf", writer_bytes(writer))


def run_redact(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    regions = _parse_elements(options, "regions")
    reader = read_pdf(uploaded.data)

    by_page: dict[int, list[dict]] = {}
    for region in regions:
        page_number = int(region.get("page", 1))
        if not 1 <= page_number <= len(reader.pages):
            raise ToolError(f"region on page {page_number}, but the document has "
                            f"{len(reader.pages)} pages")
        by_page.setdefault(page_number - 1, []).append(region)

    document = pdfium.PdfDocument(uploaded.data)
    try:
        replacements: dict[int, bytes] = {}
        for index, page_regions in by_page.items():
            image = document[index].render(scale=REDACT_DPI / 72).to_pil().convert("RGB")
            from PIL import ImageDraw

            draw = ImageDraw.Draw(image)
            for region in page_regions:
                x = float(region["x"]) * image.width
                y = float(region["y"]) * image.height
                w = float(region.get("w", 0.1)) * image.width
                h = float(region.get("h", 0.05)) * image.height
                draw.rectangle((x, y, x + w, y + h), fill=(0, 0, 0))
            png = io.BytesIO()
            image.save(png, format="PNG")
            layout = img2pdf.get_fixed_dpi_layout_fun((REDACT_DPI, REDACT_DPI))
            replacements[index] = img2pdf.convert(png.getvalue(), layout_fun=layout)
    finally:
        document.close()

    writer = pypdf.PdfWriter()
    for index, page in enumerate(reader.pages):
        if index in replacements:
            writer.add_page(pypdf.PdfReader(io.BytesIO(replacements[index])).pages[0])
        else:
            writer.add_page(page)
    return ToolResult(f"{safe_stem(uploaded.name)}_redacted.pdf", writer_bytes(writer))


register(Tool(
    name="edit",
    interactive=True,
    label="Edit PDF",
    description="Type text, stamp images and draw boxes right on the page.",
    icon="✏️",
    run=run_edit,
    multiple=True,  # the PDF plus any stamped images
    options=(Option("elements", "Elements", help="placed visually in the editor"),),
    wants_pages=True,
    category="edit",
))

register(Tool(
    name="crop",
    label="Crop PDF",
    description="Trim margins (in mm) off every page or a selection.",
    icon="🔲",
    run=run_crop,
    options=(
        Option("top", "Top (mm)", kind="number", default=10),
        Option("right", "Right (mm)", kind="number", default=10),
        Option("bottom", "Bottom (mm)", kind="number", default=10),
        Option("left", "Left (mm)", kind="number", default=10),
        Option("pages", "Pages", help="leave empty for all pages"),
    ),
    category="edit",
))

register(Tool(
    name="remove_pages",
    label="Remove pages",
    description="Delete the pages you pick, keep the rest.",
    icon="🗑️",
    run=run_remove_pages,
    wants_pages=True,
    options=(Option("pages", "Pages to remove", help="e.g. 2,5-7"),),
    category="organize",
))

register(Tool(
    name="redact",
    interactive=True,
    label="Redact PDF",
    description="Black out regions — affected pages are rasterized so the text underneath is truly gone.",
    icon="⬛",
    run=run_redact,
    options=(Option("regions", "Regions", help="drawn visually in the editor"),),
    wants_pages=True,
    category="secure",
))
