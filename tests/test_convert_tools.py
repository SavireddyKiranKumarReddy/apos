import io
import zipfile

import pypdf
import pytest

from pdfsmith.tools.convert import (
    ocr_available,
    run_extract_text,
    run_images_to_pdf,
    run_ocr,
    run_office_to_pdf,
    run_pdf_to_images,
    run_pdf_to_word,
    soffice_path,
)
from pdfsmith.tools.helpers import ToolError
from tests.conftest import make_png, upload


def test_images_to_pdf(pdf3):
    result = run_images_to_pdf(
        [upload("a.png", make_png()), upload("b.png", make_png(color=(20, 90, 200)))], {}
    )
    reader = pypdf.PdfReader(io.BytesIO(result.data))
    assert len(reader.pages) == 2


def test_images_to_pdf_handles_alpha_channel():
    result = run_images_to_pdf([upload("a.png", make_png(mode="RGBA"))], {})
    assert len(pypdf.PdfReader(io.BytesIO(result.data)).pages) == 1


def test_images_to_pdf_rejects_non_image():
    with pytest.raises(ToolError):
        run_images_to_pdf([upload("a.png", b"definitely not an image")], {})


def test_pdf_to_images_zip(pdf3):
    result = run_pdf_to_images([upload("doc.pdf", pdf3)], {"format": "png", "dpi": "72"})
    assert result.media_type == "application/zip"
    with zipfile.ZipFile(io.BytesIO(result.data)) as archive:
        names = sorted(archive.namelist())
        assert len(names) == 3
        assert archive.read(names[0]).startswith(b"\x89PNG")


def test_pdf_to_images_single_page_jpg(pdf3):
    single = pypdf.PdfWriter()
    single.add_page(pypdf.PdfReader(io.BytesIO(pdf3)).pages[0])
    buffer = io.BytesIO()
    single.write(buffer)

    result = run_pdf_to_images([upload("one.pdf", buffer.getvalue())], {"format": "jpg", "dpi": "72"})
    assert result.media_type == "image/jpeg"
    assert result.data.startswith(b"\xff\xd8")


def test_pdf_to_images_validates_dpi(pdf3):
    with pytest.raises(ToolError):
        run_pdf_to_images([upload("doc.pdf", pdf3)], {"dpi": "9999"})


def test_extract_text(pdf3):
    result = run_extract_text([upload("doc.pdf", pdf3)], {})
    text = result.data.decode()
    assert "Alpha" in text and "Charlie" in text
    assert "page break" in text
    assert result.media_type == "text/plain"


def test_pdf_to_word(pdf3):
    result = run_pdf_to_word([upload("doc.pdf", pdf3)], {})
    with zipfile.ZipFile(io.BytesIO(result.data)) as archive:
        document = archive.read("word/document.xml")
    assert b"Alpha" in document


@pytest.mark.skipif(soffice_path() is None, reason="LibreOffice not installed")
def test_office_to_pdf_roundtrip(pdf3):
    docx = run_pdf_to_word([upload("doc.pdf", pdf3)], {})
    result = run_office_to_pdf([upload("doc.docx", docx.data)], {})
    assert b"%PDF" in result.data[:8]


@pytest.mark.skipif(not ocr_available(), reason="ocrmypdf/tesseract not installed")
def test_ocr_makes_scan_searchable(pdf3):
    images = run_pdf_to_images([upload("doc.pdf", pdf3)], {"format": "png", "dpi": "150"})
    with zipfile.ZipFile(io.BytesIO(images.data)) as archive:
        first_page = archive.read(sorted(archive.namelist())[0])
    scanned = run_images_to_pdf([upload("scan.png", first_page)], {})
    assert "Alpha" not in run_extract_text([upload("s.pdf", scanned.data)], {}).data.decode()

    result = run_ocr([upload("s.pdf", scanned.data)], {"language": "eng"})
    assert "Alpha" in run_extract_text([upload("o.pdf", result.data)], {}).data.decode()
