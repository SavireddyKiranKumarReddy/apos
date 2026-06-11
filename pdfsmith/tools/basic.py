"""Core page operations: merge, split, organize, rotate."""

from __future__ import annotations

import pypdf

from pdfsmith.tools.helpers import (
    ToolError,
    parse_page_ranges,
    read_pdf,
    safe_stem,
    writer_bytes,
    zip_files,
)
from pdfsmith.tools.registry import Option, Tool, ToolResult, UploadedFile, register


def run_merge(files: list[UploadedFile], options: dict) -> ToolResult:
    if len(files) < 2:
        raise ToolError("merging needs at least two PDFs")
    writer = pypdf.PdfWriter()
    for uploaded in files:
        for page in read_pdf(uploaded.data).pages:
            writer.add_page(page)
    return ToolResult("merged.pdf", writer_bytes(writer))


def run_split(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    reader = read_pdf(uploaded.data)
    mode = options.get("mode", "ranges")
    stem = safe_stem(uploaded.name)

    if mode == "every_page":
        entries = []
        for index, page in enumerate(reader.pages, start=1):
            writer = pypdf.PdfWriter()
            writer.add_page(page)
            entries.append((f"{stem}_page_{index:03d}.pdf", writer_bytes(writer)))
        return ToolResult(f"{stem}_pages.zip", zip_files(entries), "application/zip")

    indexes = parse_page_ranges(options.get("pages", ""), len(reader.pages))
    writer = pypdf.PdfWriter()
    for index in indexes:
        writer.add_page(reader.pages[index])
    return ToolResult(f"{stem}_extracted.pdf", writer_bytes(writer))


def run_organize(files: list[UploadedFile], options: dict) -> ToolResult:
    """Reorder / delete / duplicate pages. ``order`` is a 1-based list like
    "3,1,1,2" — omitted pages are deleted, repeated pages are duplicated."""
    (uploaded,) = files
    reader = read_pdf(uploaded.data)
    order_spec = str(options.get("order", "")).strip()
    if not order_spec:
        raise ToolError("provide the new page order, e.g. 3,1,2")

    writer = pypdf.PdfWriter()
    for chunk in order_spec.split(","):
        chunk = chunk.strip()
        if not chunk.isdigit():
            raise ToolError(f"page order entries must be numbers, got {chunk!r}")
        index = int(chunk)
        if not 1 <= index <= len(reader.pages):
            raise ToolError(f"page {index} is outside this document (1-{len(reader.pages)})")
        writer.add_page(reader.pages[index - 1])
    return ToolResult(f"{safe_stem(uploaded.name)}_organized.pdf", writer_bytes(writer))


def run_rotate(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    reader = read_pdf(uploaded.data)
    angle = int(options.get("angle", 90))
    if angle % 90:
        raise ToolError("rotation must be a multiple of 90 degrees")
    pages_spec = str(options.get("pages", "")).strip()
    targets = (
        set(parse_page_ranges(pages_spec, len(reader.pages)))
        if pages_spec
        else set(range(len(reader.pages)))
    )

    writer = pypdf.PdfWriter()
    for index, page in enumerate(reader.pages):
        if index in targets:
            page.rotate(angle)
        writer.add_page(page)
    return ToolResult(f"{safe_stem(uploaded.name)}_rotated.pdf", writer_bytes(writer))


register(Tool(
    name="merge",
    label="Merge PDF",
    description="Combine PDFs in the order you want.",
    icon="🧩",
    run=run_merge,
    multiple=True,
    min_files=2,
    category="organize",
))

register(Tool(
    name="split",
    interactive=True,
    label="Split PDF",
    description="Extract a page range, or burst every page into its own file.",
    icon="✂️",
    run=run_split,
    wants_pages=True,
    options=(
        Option("mode", "Mode", kind="select", default="ranges",
               choices=(("ranges", "Extract selected pages"), ("every_page", "One file per page"))),
        Option("pages", "Pages", help="e.g. 1-3,7 (used when extracting)"),
    ),
    category="organize",
))

register(Tool(
    name="organize",
    interactive=True,
    label="Organize PDF",
    description="Reorder, duplicate or delete pages visually.",
    icon="🗂️",
    run=run_organize,
    wants_pages=True,
    options=(
        Option("order", "New page order", help="e.g. 3,1,2 — omit to delete, repeat to duplicate"),
    ),
    category="organize",
))

register(Tool(
    name="rotate",
    label="Rotate PDF",
    description="Rotate every page, or just the ones you pick.",
    icon="🔄",
    run=run_rotate,
    wants_pages=True,
    options=(
        Option("angle", "Angle", kind="select", default="90",
               choices=(("90", "90° right"), ("180", "180°"), ("270", "90° left"))),
        Option("pages", "Pages", help="leave empty for all pages"),
    ),
    category="organize",
))
