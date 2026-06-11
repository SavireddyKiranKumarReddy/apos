import io
import json

import pypdf
import pytest

from pdfsmith.tools.edit import run_crop, run_edit, run_redact, run_remove_pages
from pdfsmith.tools.helpers import ToolError
from tests.conftest import make_png, upload


def pages_of(data: bytes) -> list[str]:
    return [page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(data)).pages]


def test_edit_adds_text(pdf3):
    elements = [{"type": "text", "page": 2, "x": 0.1, "y": 0.1, "size": 18,
                 "color": "#d00000", "text": "APPROVED BY VK"}]
    result = run_edit([upload("doc.pdf", pdf3)], {"elements": json.dumps(elements)})
    texts = pages_of(result.data)
    assert "APPROVED BY VK" in texts[1]
    assert "APPROVED BY VK" not in texts[0]
    assert "Bravo" in texts[1]  # original content survives


def test_edit_stamps_image_and_rect(pdf3):
    elements = [
        {"type": "image", "page": 1, "file": 0, "x": 0.6, "y": 0.7, "w": 0.25, "h": 0.1},
        {"type": "rect", "page": 1, "x": 0.1, "y": 0.4, "w": 0.3, "h": 0.05,
         "color": "#ffffff", "opacity": 1.0},
    ]
    result = run_edit(
        [upload("doc.pdf", pdf3), upload("sig.png", make_png())],
        {"elements": json.dumps(elements)},
    )
    page = pypdf.PdfReader(io.BytesIO(result.data)).pages[0]
    assert "/XObject" in page["/Resources"]  # the stamped image landed


def test_edit_validates(pdf3):
    with pytest.raises(ToolError):
        run_edit([upload("doc.pdf", pdf3)], {"elements": "not json"})
    with pytest.raises(ToolError):
        run_edit([upload("doc.pdf", pdf3)], {"elements": "[]"})
    with pytest.raises(ToolError):
        run_edit([upload("doc.pdf", pdf3)],
                 {"elements": json.dumps([{"type": "text", "page": 99, "text": "x"}])})
    with pytest.raises(ToolError):
        run_edit([upload("doc.pdf", pdf3)],
                 {"elements": json.dumps([{"type": "image", "page": 1, "file": 0}])})


def test_crop_shrinks_boxes(pdf3):
    result = run_crop([upload("doc.pdf", pdf3)],
                      {"top": "10", "right": "10", "bottom": "10", "left": "10"})
    page = pypdf.PdfReader(io.BytesIO(result.data)).pages[0]
    margin_pt = 10 * 72 / 25.4
    assert float(page.mediabox.width) == pytest.approx(612 - 2 * margin_pt, abs=0.5)
    assert float(page.mediabox.height) == pytest.approx(792 - 2 * margin_pt, abs=0.5)


def test_crop_rejects_zero_and_overcrop(pdf3):
    with pytest.raises(ToolError):
        run_crop([upload("doc.pdf", pdf3)], {"top": "0", "right": "0", "bottom": "0", "left": "0"})
    with pytest.raises(ToolError):
        run_crop([upload("doc.pdf", pdf3)], {"top": "150", "right": "0", "bottom": "150", "left": "0"})


def test_remove_pages(pdf3):
    result = run_remove_pages([upload("doc.pdf", pdf3)], {"pages": "2"})
    texts = pages_of(result.data)
    assert len(texts) == 2
    assert "Alpha" in texts[0] and "Charlie" in texts[1]


def test_remove_all_pages_rejected(pdf3):
    with pytest.raises(ToolError):
        run_remove_pages([upload("doc.pdf", pdf3)], {"pages": "1-3"})


def test_redact_removes_text_for_real(pdf3):
    # the marker word sits at the top-left of the page; black it out
    regions = [{"page": 1, "x": 0.0, "y": 0.0, "w": 1.0, "h": 0.25}]
    result = run_redact([upload("doc.pdf", pdf3)], {"regions": json.dumps(regions)})
    texts = pages_of(result.data)
    assert len(texts) == 3
    assert "Alpha" not in texts[0]          # gone, not hidden
    assert "Bravo" in texts[1]              # untouched pages keep their text


def test_redact_keeps_page_size(pdf3):
    regions = [{"page": 1, "x": 0.4, "y": 0.4, "w": 0.2, "h": 0.1}]
    result = run_redact([upload("doc.pdf", pdf3)], {"regions": json.dumps(regions)})
    page = pypdf.PdfReader(io.BytesIO(result.data)).pages[0]
    assert float(page.mediabox.width) == pytest.approx(612, abs=1.5)
    assert float(page.mediabox.height) == pytest.approx(792, abs=1.5)
