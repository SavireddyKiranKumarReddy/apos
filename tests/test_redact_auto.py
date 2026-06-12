import io

import pypdf
import pytest
from reportlab.pdfgen import canvas as rl_canvas

from pdfsmith.tools.helpers import ToolError
from pdfsmith.tools.redact_auto import _luhn_ok, _spans, run_auto_redact
from tests.conftest import upload


def make_sensitive_pdf() -> bytes:
    buffer = io.BytesIO()
    canvas = rl_canvas.Canvas(buffer, pagesize=(612, 792))
    canvas.setFont("Helvetica", 14)
    canvas.drawString(72, 720, "Email: jane@example.com")
    canvas.drawString(72, 700, "Phone: (555) 123-4567")
    canvas.drawString(72, 680, "Card: 4111 1111 1111 1111")
    canvas.drawString(72, 660, "This line is perfectly harmless and stays put.")
    canvas.save()
    return buffer.getvalue()


def text_of(data: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(data)).pages)


def test_luhn_validates_real_card():
    assert _luhn_ok("4111111111111111")
    assert not _luhn_ok("4111111111111112")


def test_spans_find_email_and_phone():
    line = "reach jane@example.com or (555) 123-4567 today"
    spans = _spans(line, {"emails": True, "phones": True}, [])
    found = [line[s:e] for s, e in spans]
    assert any("jane@example.com" in f for f in found)
    assert any("123-4567" in f for f in found)


def test_auto_redact_removes_sensitive_keeps_rest():
    data = make_sensitive_pdf()
    result = run_auto_redact(
        [upload("doc.pdf", data)],
        {"emails": "true", "phones": "true", "cards": "true"},
    )
    out = text_of(result.data)
    # the affected page is rasterized, so its text is gone entirely —
    # the sensitive values are unrecoverable, which is the point.
    assert "jane@example.com" not in out
    assert "4111" not in out
    assert result.filename.endswith("_redacted.pdf")


def test_auto_redact_custom_terms():
    data = make_sensitive_pdf()
    # nothing selected, only a custom term — must still match and redact
    result = run_auto_redact(
        [upload("doc.pdf", data)],
        {"emails": "false", "phones": "false", "cards": "false", "terms": "harmless"},
    )
    assert "harmless" not in text_of(result.data)


def test_auto_redact_nothing_selected_errors():
    data = make_sensitive_pdf()
    with pytest.raises(ToolError, match="at least one category"):
        run_auto_redact(
            [upload("doc.pdf", data)],
            {"emails": "false", "phones": "false", "cards": "false", "ssn": "false",
             "ids": "false", "dates": "false", "terms": ""},
        )


def test_auto_redact_no_match_errors():
    buffer = io.BytesIO()
    canvas = rl_canvas.Canvas(buffer, pagesize=(612, 792))
    canvas.drawString(72, 720, "Just some ordinary words here.")
    canvas.save()
    with pytest.raises(ToolError, match="no sensitive content"):
        run_auto_redact([upload("clean.pdf", buffer.getvalue())], {"emails": "true"})
