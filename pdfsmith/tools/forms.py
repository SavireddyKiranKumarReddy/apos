"""AcroForm filling: list a form's fields, fill them, optionally lock them."""

from __future__ import annotations

import io
import json

import pypdf
from pypdf.generic import NameObject, NumberObject

from pdfsmith.tools.helpers import ToolError, read_pdf, safe_stem, writer_bytes
from pdfsmith.tools.registry import Option, Tool, ToolResult, UploadedFile, register

READ_ONLY_FLAG = 1


def list_form_fields(data: bytes) -> list[dict]:
    """Field metadata for the UI to render real inputs from."""
    reader = read_pdf(data)
    fields = reader.get_fields() or {}
    described = []
    for name, field in fields.items():
        field_type = str(field.field_type) if field.field_type else ""
        entry = {
            "name": str(name),
            "type": {"/Tx": "text", "/Btn": "checkbox", "/Ch": "choice"}.get(field_type, "text"),
            "value": "" if field.value is None else str(field.value),
        }
        states = field.get("/_States_")
        if states:
            entry["states"] = [str(state) for state in states]
        described.append(entry)
    return described


def run_form_fill(files: list[UploadedFile], options: dict) -> ToolResult:
    (uploaded,) = files
    try:
        values = json.loads(options.get("fields", "{}"))
    except json.JSONDecodeError:
        raise ToolError("fields must be valid JSON") from None
    if not isinstance(values, dict) or not values:
        raise ToolError("no field values provided")

    reader = read_pdf(uploaded.data)
    known = set((reader.get_fields() or {}).keys())
    if not known:
        raise ToolError("this PDF has no fillable form fields")
    unknown = set(values) - {str(k) for k in known}
    if unknown:
        raise ToolError(f"unknown form fields: {', '.join(sorted(unknown))}")

    writer = pypdf.PdfWriter(clone_from=reader)
    writer.set_need_appearances_writer(True)
    for page in writer.pages:
        writer.update_page_form_field_values(page, values, auto_regenerate=False)

    if str(options.get("lock", "")).lower() in ("true", "on", "1", "yes"):
        for page in writer.pages:
            for annotation in page.get("/Annots") or []:
                obj = annotation.get_object()
                if obj.get("/T") and str(obj["/T"]) in values:
                    obj[NameObject("/Ff")] = NumberObject(
                        int(obj.get("/Ff", 0)) | READ_ONLY_FLAG
                    )

    return ToolResult(f"{safe_stem(uploaded.name)}_filled.pdf", writer_bytes(writer))


register(Tool(
    name="form_fill",
    interactive=True,
    label="Fill PDF form",
    description="Fill a form's fields — they appear automatically when you add the file.",
    icon="🖊️",
    run=run_form_fill,
    options=(
        Option("fields", "Field values", help="filled in automatically by the form UI"),
        Option("lock", "Lock fields after filling", kind="checkbox", default=False),
    ),
    category="edit",
))
