"""Security and document hygiene: protect, unlock, repair, metadata."""

from __future__ import annotations

import io

import pikepdf

from pdfsmith.tools.helpers import ToolError, safe_stem
from pdfsmith.tools.registry import Option, Tool, ToolResult, UploadedFile, register


def _open_pdf(data: bytes, password: str = "") -> pikepdf.Pdf:
    try:
        return pikepdf.open(io.BytesIO(data), password=password)
    except pikepdf.PasswordError:
        raise ToolError(
            "wrong password" if password else "this PDF is password-protected"
        ) from None
    except pikepdf.PdfError as exc:
        raise ToolError("that file does not look like a valid PDF") from exc


def run_protect(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    password = str(options.get("password", ""))
    if len(password) < 4:
        raise ToolError("pick a password of at least 4 characters")
    with _open_pdf(uploaded.data) as pdf:
        buffer = io.BytesIO()
        pdf.save(buffer, encryption=pikepdf.Encryption(owner=password, user=password, R=6))
    return ToolResult(f"{safe_stem(uploaded.name)}_protected.pdf", buffer.getvalue())


def run_unlock(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    password = str(options.get("password", ""))
    with _open_pdf(uploaded.data, password=password) as pdf:
        buffer = io.BytesIO()
        pdf.save(buffer)
    return ToolResult(f"{safe_stem(uploaded.name)}_unlocked.pdf", buffer.getvalue())


def run_repair(files: list[UploadedFile], options: dict) -> ToolResult:
    """Rebuild the cross-reference table and rewrite the file structure —
    fixes the most common "this PDF won't open" breakage."""
    (uploaded,) = files
    with _open_pdf(uploaded.data) as pdf:
        buffer = io.BytesIO()
        pdf.save(buffer)
    return ToolResult(f"{safe_stem(uploaded.name)}_repaired.pdf", buffer.getvalue())


def run_metadata(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    with _open_pdf(uploaded.data) as pdf:
        with pdf.open_metadata() as meta:
            for field, key in (
                ("title", "dc:title"),
                ("author", "dc:creator"),
                ("subject", "dc:description"),
            ):
                value = str(options.get(field, "")).strip()
                if value:
                    meta[key] = [value] if key == "dc:creator" else value
        buffer = io.BytesIO()
        pdf.save(buffer)
    return ToolResult(f"{safe_stem(uploaded.name)}_metadata.pdf", buffer.getvalue())


register(Tool(
    name="protect",
    label="Protect PDF",
    description="Encrypt with a password (AES-256).",
    icon="🔒",
    run=run_protect,
    options=(Option("password", "Password", kind="password"),),
    category="secure",
))

register(Tool(
    name="unlock",
    label="Unlock PDF",
    description="Remove a password you know.",
    icon="🔓",
    run=run_unlock,
    options=(Option("password", "Current password", kind="password"),),
    category="secure",
))

register(Tool(
    name="repair",
    label="Repair PDF",
    description="Rebuild a damaged file so it opens again.",
    icon="🩹",
    run=run_repair,
    category="secure",
))

register(Tool(
    name="metadata",
    label="Edit metadata",
    description="Set the title, author and subject.",
    icon="🏷️",
    run=run_metadata,
    options=(
        Option("title", "Title"),
        Option("author", "Author"),
        Option("subject", "Subject"),
    ),
    category="secure",
))
