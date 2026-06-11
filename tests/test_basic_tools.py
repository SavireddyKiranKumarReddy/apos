import io
import zipfile

import pypdf
import pytest

from pdfsmith.tools.basic import run_merge, run_organize, run_rotate, run_split
from pdfsmith.tools.helpers import ToolError
from tests.conftest import upload


def pages_of(data: bytes) -> list[str]:
    return [page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(data)).pages]


def test_merge_keeps_order(pdf3, pdf2):
    result = run_merge([upload("a.pdf", pdf3), upload("b.pdf", pdf2)], {})
    texts = pages_of(result.data)
    assert len(texts) == 5
    assert "Alpha" in texts[0]
    assert "Delta" in texts[3]
    assert result.filename == "merged.pdf"


def test_merge_needs_two_files(pdf3):
    with pytest.raises(ToolError):
        run_merge([upload("a.pdf", pdf3)], {})


def test_merge_rejects_garbage(pdf3):
    with pytest.raises(ToolError):
        run_merge([upload("a.pdf", pdf3), upload("b.pdf", b"not a pdf")], {})


def test_split_extracts_range(pdf3):
    result = run_split([upload("doc.pdf", pdf3)], {"mode": "ranges", "pages": "2-3"})
    texts = pages_of(result.data)
    assert len(texts) == 2
    assert "Bravo" in texts[0] and "Charlie" in texts[1]


def test_split_every_page_makes_zip(pdf3):
    result = run_split([upload("doc.pdf", pdf3)], {"mode": "every_page"})
    assert result.media_type == "application/zip"
    with zipfile.ZipFile(io.BytesIO(result.data)) as archive:
        names = archive.namelist()
        assert len(names) == 3
        first = archive.read(names[0])
    assert len(pages_of(first)) == 1


def test_split_rejects_out_of_range(pdf3):
    with pytest.raises(ToolError):
        run_split([upload("doc.pdf", pdf3)], {"mode": "ranges", "pages": "9"})


def test_split_open_ended_range(pdf3):
    result = run_split([upload("doc.pdf", pdf3)], {"mode": "ranges", "pages": "2-"})
    assert len(pages_of(result.data)) == 2


def test_organize_reorders_deletes_duplicates(pdf3):
    result = run_organize([upload("doc.pdf", pdf3)], {"order": "3,1,1"})
    texts = pages_of(result.data)
    assert len(texts) == 3
    assert "Charlie" in texts[0]
    assert "Alpha" in texts[1] and "Alpha" in texts[2]


def test_organize_validates_entries(pdf3):
    with pytest.raises(ToolError):
        run_organize([upload("doc.pdf", pdf3)], {"order": "1,x"})
    with pytest.raises(ToolError):
        run_organize([upload("doc.pdf", pdf3)], {"order": "7"})
    with pytest.raises(ToolError):
        run_organize([upload("doc.pdf", pdf3)], {"order": ""})


def test_rotate_all_pages(pdf3):
    result = run_rotate([upload("doc.pdf", pdf3)], {"angle": "90"})
    reader = pypdf.PdfReader(io.BytesIO(result.data))
    assert all(page.rotation == 90 for page in reader.pages)


def test_rotate_selected_pages(pdf3):
    result = run_rotate([upload("doc.pdf", pdf3)], {"angle": "180", "pages": "1"})
    reader = pypdf.PdfReader(io.BytesIO(result.data))
    assert reader.pages[0].rotation == 180
    assert reader.pages[1].rotation == 0


def test_rotate_rejects_odd_angle(pdf3):
    with pytest.raises(ToolError):
        run_rotate([upload("doc.pdf", pdf3)], {"angle": "45"})
