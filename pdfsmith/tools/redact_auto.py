"""Automatic redaction of sensitive content.

Finds personal / sensitive data — emails, phone numbers, government IDs,
credit-card numbers, dates — plus any custom terms you name, and blacks them
out by rasterizing only the affected text. Everything non-sensitive stays
intact and selectable. The blackout reuses the same rasterizing redaction as
the manual tool, so the hidden text is genuinely gone, not merely covered.

Detection works on the page's own word boxes (via pdfplumber): each line is
reassembled, the patterns run over the line text, and every word that overlaps
a match is painted over — so multi-token values like ``(555) 123-4567`` are
caught whole.
"""

from __future__ import annotations

import io
import re

from pdfsmith.tools.edit import _assemble_redacted, _rasterize_redactions
from pdfsmith.tools.helpers import ToolError, read_pdf, safe_stem
from pdfsmith.tools.registry import Option, Tool, ToolResult, UploadedFile, register

# Each detector is (option_name, label, compiled pattern, optional validator).
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<![\w@.])\+?\d[\d\s().\-]{7,}\d(?![\w@.])")
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
ID = re.compile(r"\b[A-Z]{2}\d{6,9}\b")  # passport / national-ID shaped
DATE = re.compile(
    r"\b("
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|\d{4}[/-]\d{1,2}[/-]\d{1,2}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"
    r")\b",
    re.IGNORECASE,
)


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _luhn_ok(number: str) -> bool:
    total, parity = 0, len(number) % 2
    for i, digit in enumerate(number):
        value = int(digit)
        if i % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _spans(line: str, enabled: dict[str, bool], terms: list[str]) -> list[tuple[int, int]]:
    """Character spans in ``line`` that should be redacted."""
    spans: list[tuple[int, int]] = []
    if enabled.get("emails"):
        spans += [m.span() for m in EMAIL.finditer(line)]
    if enabled.get("ssn"):
        spans += [m.span() for m in SSN.finditer(line)]
    if enabled.get("ids"):
        spans += [m.span() for m in ID.finditer(line)]
    if enabled.get("dates"):
        spans += [m.span() for m in DATE.finditer(line)]
    if enabled.get("cards"):
        for m in CARD.finditer(line):
            d = _digits(m.group())
            if 13 <= len(d) <= 19 and _luhn_ok(d):
                spans.append(m.span())
    if enabled.get("phones"):
        for m in PHONE.finditer(line):
            if 7 <= len(_digits(m.group())) <= 15:
                spans.append(m.span())
    for term in terms:
        if term:
            spans += [m.span() for m in re.finditer(re.escape(term), line, re.IGNORECASE)]
    return spans


def _group_lines(words: list[dict]) -> list[list[dict]]:
    """Group pdfplumber words into visual lines by their top coordinate."""
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(word["top"] - lines[-1][0]["top"]) <= max(
            2.0, (word["bottom"] - word["top"]) * 0.6
        ):
            lines[-1].append(word)
        else:
            lines.append([word])
    return lines


ALL_CATEGORIES = {key: True for key in ("emails", "phones", "ssn", "cards", "ids", "dates")}


def detect_word_boxes(data: bytes) -> list[dict]:
    """Per-page word boxes (as page-relative fractions) plus a ``sensitive``
    flag for the interactive redaction screen: the browser draws a clickable
    target over every word and pre-highlights the ones that look like PII."""
    read_pdf(data)  # validate / reject encrypted up front
    import pdfplumber

    pages: list[dict] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            width = page.width or 1.0
            height = page.height or 1.0
            out: list[dict] = []
            for line in _group_lines(page.extract_words(use_text_flow=False)):
                text, ranges = "", []
                for word in line:
                    start = len(text)
                    text += word["text"]
                    ranges.append((start, len(text), word))
                    text += " "
                sensitive_words = set()
                for span_start, span_end in _spans(text, ALL_CATEGORIES, []):
                    for start, end, word in ranges:
                        if start < span_end and end > span_start:
                            sensitive_words.add(id(word))
                for word in line:
                    out.append({
                        "x": word["x0"] / width,
                        "y": word["top"] / height,
                        "w": (word["x1"] - word["x0"]) / width,
                        "h": (word["bottom"] - word["top"]) / height,
                        "text": word["text"],
                        "sensitive": id(word) in sensitive_words,
                    })
            pages.append({"width": width, "height": height, "words": out})
    return pages


def run_auto_redact(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    read_pdf(uploaded.data)  # validates / rejects encrypted up front

    enabled = {
        key: str(options.get(key, "true")).lower() in ("1", "true", "on", "yes")
        for key in ("emails", "phones", "ssn", "cards", "ids", "dates")
    }
    terms = [t.strip() for t in str(options.get("terms", "")).split(",") if t.strip()]
    if not any(enabled.values()) and not terms:
        raise ToolError("pick at least one category to redact, or add custom terms")

    import pdfplumber

    pad_x, pad_y = 1.5, 1.0  # points of slack so glyphs are fully covered
    by_page: dict[int, list[tuple[float, float, float, float]]] = {}
    hits = 0
    with pdfplumber.open(io.BytesIO(uploaded.data)) as pdf:
        for index, page in enumerate(pdf.pages):
            width, height = page.width, page.height
            if not width or not height:
                continue
            words = page.extract_words(use_text_flow=False)
            for line in _group_lines(words):
                # Reassemble the line, tracking each word's char range.
                text, ranges = "", []
                for word in line:
                    start = len(text)
                    text += word["text"]
                    ranges.append((start, len(text), word))
                    text += " "
                for span_start, span_end in _spans(text, enabled, terms):
                    for start, end, word in ranges:
                        if start < span_end and end > span_start:  # overlap
                            x0 = max(0.0, word["x0"] - pad_x)
                            top = max(0.0, word["top"] - pad_y)
                            x1 = min(width, word["x1"] + pad_x)
                            bottom = min(height, word["bottom"] + pad_y)
                            by_page.setdefault(index, []).append((
                                x0 / width, top / height,
                                (x1 - x0) / width, (bottom - top) / height,
                            ))
                            hits += 1

    if not by_page:
        raise ToolError(
            "no sensitive content matched — the document has no text in the "
            "selected categories (if it's a scan, run OCR first)"
        )

    reader = read_pdf(uploaded.data)
    replacements = _rasterize_redactions(uploaded.data, by_page)
    return ToolResult(
        f"{safe_stem(uploaded.name)}_redacted.pdf",
        _assemble_redacted(reader, replacements),
    )


register(Tool(
    name="auto_redact",
    label="Redact Sensitive Data",
    description="Automatically black out emails, phone numbers, IDs, cards and "
                "any custom terms — the rest of the text stays intact.",
    icon="🕶️",
    run=run_auto_redact,
    options=(
        Option("emails", "Email addresses", kind="checkbox", default=True),
        Option("phones", "Phone numbers", kind="checkbox", default=True),
        Option("ssn", "SSN (123-45-6789)", kind="checkbox", default=True),
        Option("cards", "Credit-card numbers", kind="checkbox", default=True),
        Option("ids", "Passport / national IDs", kind="checkbox", default=False),
        Option("dates", "Dates", kind="checkbox", default=False),
        Option("terms", "Custom terms",
               help="comma-separated words/names to also redact, e.g. Acme, John Doe"),
    ),
    category="secure",
))
