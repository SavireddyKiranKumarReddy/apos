"""PDF Intelligence: summarize and translate via the Claude API.

These tools light up when the operator sets ``ANTHROPIC_API_KEY`` (and
installs the ``ai`` extra) — exactly like the LibreOffice/OCR tools light up
when their binaries are present. The default model is ``claude-opus-4-8``;
override with ``PDFSMITH_AI_MODEL`` if you want to trade quality for cost.
"""

from __future__ import annotations

import importlib.util
import os

from pdfsmith.tools.helpers import ToolError, read_pdf, safe_stem
from pdfsmith.tools.registry import Option, Tool, ToolResult, UploadedFile, register

DEFAULT_MODEL = "claude-opus-4-8"
MAX_INPUT_CHARS = 300_000  # roughly 75k tokens — generous, but not unbounded

SUMMARIZE_SYSTEM = (
    "You summarize documents faithfully. Work only from the provided text; if "
    "something is unclear or missing, say so rather than guessing. Use clean "
    "Markdown: a one-paragraph overview, then the key points as bullets, then "
    "any figures, dates or obligations worth flagging."
)

TRANSLATE_SYSTEM = (
    "You are a professional translator. Translate the provided document text "
    "into {language}. Preserve the structure — keep the page-break markers "
    "exactly as they appear, keep lists as lists — and translate everything "
    "else. Output only the translation."
)


def ai_available() -> bool:
    return (
        importlib.util.find_spec("anthropic") is not None
        and bool(os.getenv("ANTHROPIC_API_KEY"))
    )


def _document_text(uploaded: UploadedFile) -> str:
    pages = [page.extract_text() or "" for page in read_pdf(uploaded.data).pages]
    text = "\n\n----- page break -----\n\n".join(pages).strip()
    if not text:
        raise ToolError(
            "no extractable text in this PDF — if it is a scan, run OCR first"
        )
    if len(text) > MAX_INPUT_CHARS:
        raise ToolError(
            f"this document is too large for the AI tools "
            f"({len(text):,} characters; the cap is {MAX_INPUT_CHARS:,}) — "
            f"split it into parts first"
        )
    return text


def _complete(system: str, text: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=os.getenv("PDFSMITH_AI_MODEL", DEFAULT_MODEL),
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": text}],
        )
    except anthropic.AuthenticationError:
        raise ToolError("the server's AI API key was rejected") from None
    except anthropic.RateLimitError:
        raise ToolError("the AI service is rate-limited right now — try again "
                        "in a minute") from None
    except anthropic.APIStatusError as exc:
        raise ToolError(f"the AI request failed ({exc.status_code})") from exc
    except anthropic.APIConnectionError:
        raise ToolError("could not reach the AI service — check the server's "
                        "network") from None

    output = "".join(block.text for block in response.content if block.type == "text")
    if not output.strip():
        raise ToolError("the AI service returned an empty response — try again")
    return output


def run_summarize(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    if not ai_available():
        raise ToolError("AI tools need ANTHROPIC_API_KEY set on the server")
    text = _document_text(uploaded)

    length = options.get("length", "standard")
    instruction = {
        "brief": "Keep it very short: the overview paragraph and at most five bullets.",
        "standard": "Aim for a thorough but readable summary.",
        "detailed": "Be comprehensive: cover every section of the document.",
    }.get(length, "Aim for a thorough but readable summary.")

    summary = _complete(SUMMARIZE_SYSTEM + " " + instruction, text)
    return ToolResult(
        f"{safe_stem(uploaded.name)}_summary.md", summary.encode(), "text/markdown"
    )


def run_translate(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    if not ai_available():
        raise ToolError("AI tools need ANTHROPIC_API_KEY set on the server")
    language = str(options.get("language", "")).strip()
    if not language:
        raise ToolError("pick a target language")
    text = _document_text(uploaded)

    translation = _complete(TRANSLATE_SYSTEM.format(language=language), text)
    return ToolResult(
        f"{safe_stem(uploaded.name)}_{safe_stem(language.lower())}.txt",
        translation.encode(),
        "text/plain",
    )


register(Tool(
    name="summarize",
    label="AI Summarizer",
    description="A faithful Markdown summary of any text PDF.",
    icon="🧠",
    run=run_summarize,
    options=(
        Option("length", "Length", kind="select", default="standard",
               choices=(("brief", "Brief"), ("standard", "Standard"),
                        ("detailed", "Detailed"))),
    ),
    available=ai_available,
    unavailable_hint="set ANTHROPIC_API_KEY on the server to enable",
    category="intelligence",
    produces_pdf=False,
))

register(Tool(
    name="translate",
    label="Translate PDF",
    description="Translate a document's text into another language.",
    icon="🌍",
    run=run_translate,
    options=(
        Option("language", "Target language", default="Hindi",
               help="any language — e.g. Hindi, Spanish, Japanese"),
    ),
    available=ai_available,
    unavailable_hint="set ANTHROPIC_API_KEY on the server to enable",
    category="intelligence",
    produces_pdf=False,
))
