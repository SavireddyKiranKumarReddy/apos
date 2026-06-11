"""Document comparison: per-page text diff plus a pixel-level difference score."""

from __future__ import annotations

import difflib
import io

import pypdfium2 as pdfium

from pdfsmith.tools.helpers import ToolError, read_pdf, safe_stem
from pdfsmith.tools.registry import Tool, ToolResult, UploadedFile, register


def _page_texts(data: bytes) -> list[str]:
    return [page.extract_text() or "" for page in read_pdf(data).pages]


def _pixel_difference(a: bytes, b: bytes, page_count: int) -> list[float]:
    """Fraction of pixels that differ per page (rendered at 72 dpi)."""
    from PIL import ImageChops

    doc_a, doc_b = pdfium.PdfDocument(a), pdfium.PdfDocument(b)
    scores = []
    try:
        for index in range(page_count):
            image_a = doc_a[index].render(scale=1).to_pil().convert("L")
            image_b = doc_b[index].render(scale=1).to_pil().convert("L")
            if image_a.size != image_b.size:
                image_b = image_b.resize(image_a.size)
            diff = ImageChops.difference(image_a, image_b)
            histogram = diff.histogram()
            changed = sum(histogram[16:])  # ignore near-identical antialiasing noise
            scores.append(changed / (image_a.width * image_a.height))
    finally:
        doc_a.close()
        doc_b.close()
    return scores


def run_compare(files: list[UploadedFile], options: dict) -> ToolResult:
    if len(files) != 2:
        raise ToolError("comparison needs exactly two PDFs")
    first, second = files
    texts_a, texts_b = _page_texts(first.data), _page_texts(second.data)
    common = min(len(texts_a), len(texts_b))
    pixels = _pixel_difference(first.data, second.data, common)

    lines = [
        f"Comparing  A: {first.name}  ({len(texts_a)} pages)",
        f"      with B: {second.name}  ({len(texts_b)} pages)",
        "=" * 56,
        "",
    ]
    if len(texts_a) != len(texts_b):
        lines.append(f"Page counts differ: {len(texts_a)} vs {len(texts_b)}.")
        lines.append("")

    changed_pages = []
    diffs: list[str] = []
    for index in range(common):
        text_changed = texts_a[index].strip() != texts_b[index].strip()
        pixel_pct = pixels[index] * 100
        if text_changed or pixel_pct > 0.5:
            changed_pages.append(index + 1)
            lines.append(f"page {index + 1}: TEXT {'differs' if text_changed else 'identical'}, "
                         f"pixels differ on {pixel_pct:.1f}% of the page")
            if text_changed:
                diff = difflib.unified_diff(
                    texts_a[index].splitlines(), texts_b[index].splitlines(),
                    fromfile=f"A page {index + 1}", tofile=f"B page {index + 1}",
                    lineterm="", n=1,
                )
                diffs.extend(["", *diff])
        else:
            lines.append(f"page {index + 1}: identical")

    lines.append("")
    if changed_pages or len(texts_a) != len(texts_b):
        lines.append(f"Result: documents DIFFER (pages {', '.join(map(str, changed_pages)) or '—'}).")
    else:
        lines.append("Result: no differences found.")
    if diffs:
        lines.extend(["", "Text changes", "-" * 56, *diffs])

    return ToolResult(
        f"{safe_stem(first.name)}_vs_{safe_stem(second.name)}.txt",
        ("\n".join(lines) + "\n").encode(),
        "text/plain",
    )


register(Tool(
    name="compare",
    label="Compare PDF",
    description="Page-by-page text diff plus a visual difference score.",
    icon="⚖️",
    run=run_compare,
    multiple=True,
    min_files=2,
    category="secure",
))
