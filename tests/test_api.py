import io

import pypdf
import pytest
from fastapi.testclient import TestClient

from pdfsmith.api import create_app
from pdfsmith.tools.convert import soffice_path


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_tool_listing(client):
    payload = client.get("/api/tools").json()
    names = {tool["name"] for tool in payload["tools"]}
    assert {"merge", "split", "compress", "protect", "pdf_to_images"} <= names
    for tool in payload["tools"]:
        assert {"name", "label", "description", "icon", "options", "available"} <= set(tool)
    assert isinstance(payload["max_upload_mb"], int)


def test_merge_over_http(client, pdf3, pdf2):
    response = client.post(
        "/api/tools/merge",
        files=[("files", ("a.pdf", pdf3, "application/pdf")),
               ("files", ("b.pdf", pdf2, "application/pdf"))],
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert 'filename="merged.pdf"' in response.headers["content-disposition"]
    assert len(pypdf.PdfReader(io.BytesIO(response.content)).pages) == 5


def test_unknown_tool_is_404(client, pdf3):
    response = client.post("/api/tools/teleport",
                           files=[("files", ("a.pdf", pdf3, "application/pdf"))])
    assert response.status_code == 404
    assert "error" in response.json()


def test_too_few_files_is_400(client, pdf3):
    response = client.post("/api/tools/merge",
                           files=[("files", ("a.pdf", pdf3, "application/pdf"))])
    assert response.status_code == 400


def test_tool_error_surfaces_as_400(client, pdf3):
    response = client.post(
        "/api/tools/split",
        data={"mode": "ranges", "pages": "99"},
        files=[("files", ("a.pdf", pdf3, "application/pdf"))],
    )
    assert response.status_code == 400
    assert "99" in response.json()["error"]


def test_upload_cap_is_413(client, pdf3, monkeypatch):
    monkeypatch.setenv("PDFSMITH_MAX_MB", "0")
    response = client.post("/api/tools/compress",
                           files=[("files", ("a.pdf", pdf3, "application/pdf"))])
    assert response.status_code == 413


def test_single_file_tool_rejects_two(client, pdf3, pdf2):
    response = client.post(
        "/api/tools/compress",
        files=[("files", ("a.pdf", pdf3, "application/pdf")),
               ("files", ("b.pdf", pdf2, "application/pdf"))],
    )
    assert response.status_code == 400


@pytest.mark.skipif(soffice_path() is not None, reason="LibreOffice installed")
def test_unavailable_tool_is_503(client, pdf3):
    response = client.post("/api/tools/office_to_pdf",
                           files=[("files", ("a.docx", b"x", "application/octet-stream"))])
    assert response.status_code == 503


def test_index_serves_frontend(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "pdfsmith" in response.text


def test_sign_runs_inside_the_event_loop(client, pdf3):
    # pyhanko calls asyncio.run() internally; this would explode if the tool
    # executed on the event-loop thread instead of a worker thread.
    response = client.post(
        "/api/tools/sign",
        data={"name": "Vishal", "visible": "true"},
        files=[("files", ("doc.pdf", pdf3, "application/pdf"))],
    )
    assert response.status_code == 200
    assert response.content[:5] == b"%PDF-"


def test_inspect_form_fields_endpoint(client):
    from tests.test_more_tools import make_form_pdf

    response = client.post(
        "/api/inspect/form-fields",
        files=[("file", ("form.pdf", make_form_pdf(), "application/pdf"))],
    )
    assert response.status_code == 200
    names = {field["name"] for field in response.json()["fields"]}
    assert names == {"full_name", "agree"}


def test_inspect_form_fields_needs_a_file(client):
    response = client.post("/api/inspect/form-fields")
    assert response.status_code == 400
