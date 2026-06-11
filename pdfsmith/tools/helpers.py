"""Shared plumbing for the tool implementations."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import PurePosixPath

import pypdf


class ToolError(ValueError):
    """A user-facing problem (bad file, bad options) — surfaces as HTTP 400."""


def safe_stem(filename: str) -> str:
    stem = PurePosixPath(filename.replace("\\", "/")).stem or "file"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", stem)[:80]


def read_pdf(data: bytes, *, password: str | None = None) -> pypdf.PdfReader:
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ToolError("that file does not look like a valid PDF") from exc
    if reader.is_encrypted:
        if password is None:
            raise ToolError("this PDF is password-protected — use the Unlock tool first")
        if not reader.decrypt(password):
            raise ToolError("wrong password for this PDF")
    return reader


def writer_bytes(writer: pypdf.PdfWriter) -> bytes:
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def parse_page_ranges(spec: str, page_count: int) -> list[int]:
    """Parse "1-3, 7, 12-" into zero-based page indexes (order preserved).

    Pages are 1-based in the spec, an open end ("12-") runs to the last page.
    """
    if not spec or not spec.strip():
        raise ToolError("no pages selected — use a range like 1-3,7")
    indexes: list[int] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = re.fullmatch(r"(\d+)?\s*-\s*(\d+)?|\d+", chunk)
        if not match:
            raise ToolError(f"could not understand page selection {chunk!r}")
        if "-" in chunk:
            start_text, end_text = chunk.split("-", 1)
            start = int(start_text) if start_text.strip() else 1
            end = int(end_text) if end_text.strip() else page_count
        else:
            start = end = int(chunk)
        if start < 1 or end > page_count or start > end:
            raise ToolError(
                f"page selection {chunk!r} is outside this document (1-{page_count})"
            )
        indexes.extend(range(start - 1, end))
    if not indexes:
        raise ToolError("no pages selected — use a range like 1-3,7")
    return indexes


def zip_files(entries: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


def parse_int(options: dict, name: str, default: int, lo: int, hi: int) -> int:
    raw = options.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ToolError(f"{name} must be a whole number") from None
    if not lo <= value <= hi:
        raise ToolError(f"{name} must be between {lo} and {hi}")
    return value
