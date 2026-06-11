import io

import pypdf
import pytest

from pdfsmith.tools.helpers import ToolError
from pdfsmith.tools.transform import ghostscript_path, run_compress, run_page_numbers, run_watermark
from tests.conftest import upload


def pages_of(data: bytes) -> list[str]:
    return [page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(data)).pages]


def test_watermark_stamps_every_page(pdf3):
    result = run_watermark([upload("doc.pdf", pdf3)], {"text": "DRAFT", "opacity": "20"})
    assert all("DRAFT" in text for text in pages_of(result.data))


def test_watermark_placements(pdf3):
    for placement in ("diagonal", "top", "bottom"):
        result = run_watermark(
            [upload("doc.pdf", pdf3)], {"text": "X-RAY", "placement": placement}
        )
        assert "X-RAY" in pages_of(result.data)[0]


def test_watermark_rejects_empty_text(pdf3):
    with pytest.raises(ToolError):
        run_watermark([upload("doc.pdf", pdf3)], {"text": "   "})


def test_watermark_validates_opacity(pdf3):
    with pytest.raises(ToolError):
        run_watermark([upload("doc.pdf", pdf3)], {"text": "X", "opacity": "200"})


def test_page_numbers(pdf3):
    result = run_page_numbers([upload("doc.pdf", pdf3)], {})
    texts = pages_of(result.data)
    assert "1" in texts[0] and "2" in texts[1] and "3" in texts[2]


def test_page_numbers_with_total_and_start(pdf3):
    result = run_page_numbers(
        [upload("doc.pdf", pdf3)], {"start": "5", "show_total": "true"}
    )
    assert "5 / 7" in pages_of(result.data)[0]


def test_compress_lossless_shrinks_uncompressed(pdf3):
    result = run_compress([upload("doc.pdf", pdf3)], {"level": "lossless"})
    assert len(result.data) < len(pdf3)
    assert len(pages_of(result.data)) == 3


def test_compress_never_returns_bigger_file(pdf3):
    once = run_compress([upload("doc.pdf", pdf3)], {"level": "lossless"})
    twice = run_compress([upload("doc.pdf", once.data)], {"level": "lossless"})
    assert len(twice.data) <= len(once.data)


def test_compress_rejects_garbage():
    with pytest.raises(ToolError):
        run_compress([upload("doc.pdf", b"hello")], {"level": "lossless"})


@pytest.mark.skipif(ghostscript_path() is None, reason="ghostscript not installed")
def test_compress_strong_with_ghostscript(pdf3):
    result = run_compress([upload("doc.pdf", pdf3)], {"level": "strong"})
    assert len(pages_of(result.data)) == 3


@pytest.mark.skipif(ghostscript_path() is not None, reason="ghostscript installed")
def test_compress_strong_without_ghostscript_explains(pdf3):
    with pytest.raises(ToolError, match="Ghostscript"):
        run_compress([upload("doc.pdf", pdf3)], {"level": "strong"})
