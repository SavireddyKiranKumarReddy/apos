import io
import zipfile

import pypdf
import pytest

from pdfsmith.tools.helpers import ToolError
from pdfsmith.workflows import run_workflow
from tests.conftest import make_png, upload


def pages_of(data: bytes) -> list[str]:
    return [page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(data)).pages]


def test_merge_watermark_compress_chain(pdf3, pdf2):
    result = run_workflow(
        [upload("a.pdf", pdf3), upload("b.pdf", pdf2)],
        [
            {"tool": "merge"},
            {"tool": "watermark", "options": {"text": "PIPELINE"}},
            {"tool": "compress", "options": {"level": "lossless"}},
        ],
    )
    texts = pages_of(result.data)
    assert len(texts) == 5
    assert all("PIPELINE" in text for text in texts)


def test_image_entry_then_page_numbers():
    result = run_workflow(
        [upload("a.png", make_png()), upload("b.png", make_png(color=(10, 80, 160)))],
        [
            {"tool": "images_to_pdf"},
            {"tool": "page_numbers", "options": {"show_total": "true"}},
        ],
    )
    texts = pages_of(result.data)
    assert len(texts) == 2
    assert "1 / 2" in texts[0]


def test_single_file_steps_map_over_every_file(pdf3, pdf2):
    result = run_workflow(
        [upload("a.pdf", pdf3), upload("b.pdf", pdf2)],
        [{"tool": "watermark", "options": {"text": "EACH"}}],
    )
    assert result.media_type == "application/zip"
    with zipfile.ZipFile(io.BytesIO(result.data)) as archive:
        names = archive.namelist()
        assert len(names) == 2
        assert all("EACH" in text for text in pages_of(archive.read(names[0])))


def test_non_pdf_step_must_be_last(pdf3):
    with pytest.raises(ToolError, match="last step"):
        run_workflow(
            [upload("a.pdf", pdf3)],
            [{"tool": "extract_text"}, {"tool": "compress"}],
        )


def test_non_pdf_final_step_is_fine(pdf3):
    result = run_workflow(
        [upload("a.pdf", pdf3)],
        [{"tool": "watermark", "options": {"text": "X"}}, {"tool": "extract_text"}],
    )
    assert result.media_type == "text/plain"
    assert b"X" in result.data


def test_image_tool_cannot_be_mid_chain(pdf3):
    with pytest.raises(ToolError, match="first step"):
        run_workflow(
            [upload("a.pdf", pdf3)],
            [{"tool": "compress"}, {"tool": "images_to_pdf"}],
        )


def test_unknown_tool_and_shape_errors(pdf3):
    with pytest.raises(ToolError, match="no tool called"):
        run_workflow([upload("a.pdf", pdf3)], [{"tool": "teleport"}])
    with pytest.raises(ToolError, match="at least one step"):
        run_workflow([upload("a.pdf", pdf3)], [])
    with pytest.raises(ToolError, match="capped"):
        run_workflow([upload("a.pdf", pdf3)], [{"tool": "compress"}] * 11)
    with pytest.raises(ToolError, match="step 1"):
        run_workflow([upload("a.pdf", pdf3)], ["compress"])


def test_step_errors_carry_their_position(pdf3):
    with pytest.raises(ToolError, match=r"step 1 \(Split PDF\)"):
        run_workflow(
            [upload("a.pdf", pdf3)],
            [{"tool": "split", "options": {"mode": "ranges", "pages": "99"}}],
        )


def test_workflow_over_http(client_module, pdf3, pdf2):
    import json

    response = client_module.post(
        "/api/workflows/run",
        data={"steps": json.dumps([
            {"tool": "merge"},
            {"tool": "watermark", "options": {"text": "HTTP"}},
        ])},
        files=[("files", ("a.pdf", pdf3, "application/pdf")),
               ("files", ("b.pdf", pdf2, "application/pdf"))],
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert all("HTTP" in text for text in pages_of(response.content))


def test_workflow_http_error_shapes(client_module, pdf3):
    response = client_module.post(
        "/api/workflows/run",
        data={"steps": "not json"},
        files=[("files", ("a.pdf", pdf3, "application/pdf"))],
    )
    assert response.status_code == 400
    response = client_module.post(
        "/api/workflows/run",
        data={"steps": "[]"},
        files=[("files", ("a.pdf", pdf3, "application/pdf"))],
    )
    assert response.status_code == 400
