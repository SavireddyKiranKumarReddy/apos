"""AI tool tests — the Claude API is stubbed; no network calls happen here."""

from types import SimpleNamespace

import pytest

from pdfsmith.tools import ai
from pdfsmith.tools.helpers import ToolError
from tests.conftest import upload


class StubMessages:
    def __init__(self, reply: str = "stub reply", raises: Exception | None = None):
        self.raises = raises
        self.reply = reply
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.reply)]
        )


@pytest.fixture()
def stub_api(monkeypatch):
    """Pretend the key is set and route client construction to a stub."""
    import anthropic

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    stub = StubMessages()
    monkeypatch.setattr(
        anthropic, "Anthropic", lambda *a, **k: SimpleNamespace(messages=stub)
    )
    return stub


def test_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert not ai.ai_available()
    with pytest.raises(ToolError, match="ANTHROPIC_API_KEY"):
        ai.run_summarize([upload("doc.pdf", b"%PDF-fake")], {})


def test_summarize(stub_api, pdf3):
    stub_api.reply = "# Summary\n\n- Alpha happens\n- Bravo follows"
    result = ai.run_summarize([upload("doc.pdf", pdf3)], {"length": "brief"})
    assert result.filename.endswith("_summary.md")
    assert b"Alpha happens" in result.data

    (call,) = stub_api.calls
    assert call["model"] == "claude-opus-4-8"
    assert call["thinking"] == {"type": "adaptive"}
    assert "Alpha" in call["messages"][0]["content"]  # the extracted text went up
    assert "very short" in call["system"]  # the brief instruction landed


def test_translate(stub_api, pdf3):
    stub_api.reply = "अनुवादित पाठ"
    result = ai.run_translate([upload("doc.pdf", pdf3)], {"language": "Hindi"})
    assert result.filename.endswith("_hindi.txt")
    assert "अनुवादित" in result.data.decode()
    assert "Hindi" in stub_api.calls[0]["system"]


def test_translate_needs_language(stub_api, pdf3):
    with pytest.raises(ToolError, match="language"):
        ai.run_translate([upload("doc.pdf", pdf3)], {"language": "  "})


def test_model_override(stub_api, monkeypatch, pdf3):
    monkeypatch.setenv("PDFSMITH_AI_MODEL", "claude-sonnet-4-6")
    ai.run_summarize([upload("doc.pdf", pdf3)], {})
    assert stub_api.calls[0]["model"] == "claude-sonnet-4-6"


def test_scanned_pdf_without_text(stub_api):
    import pypdf

    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    import io

    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(ToolError, match="OCR"):
        ai.run_summarize([upload("scan.pdf", buffer.getvalue())], {})


def test_oversized_document_is_refused(stub_api, monkeypatch, pdf3):
    monkeypatch.setattr(ai, "MAX_INPUT_CHARS", 10)
    with pytest.raises(ToolError, match="too large"):
        ai.run_summarize([upload("doc.pdf", pdf3)], {})
    assert not stub_api.calls  # refused before any API call


def test_api_errors_map_to_friendly_messages(monkeypatch, pdf3):
    import anthropic
    import httpx

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response_401 = httpx.Response(401, request=request)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    stub = StubMessages(raises=anthropic.AuthenticationError(
        "bad key", response=response_401, body=None
    ))
    monkeypatch.setattr(
        anthropic, "Anthropic", lambda *a, **k: SimpleNamespace(messages=stub)
    )
    with pytest.raises(ToolError, match="rejected"):
        ai.run_summarize([upload("doc.pdf", pdf3)], {})


def test_empty_reply_is_an_error(stub_api, pdf3):
    stub_api.reply = "   "
    with pytest.raises(ToolError, match="empty"):
        ai.run_summarize([upload("doc.pdf", pdf3)], {})
