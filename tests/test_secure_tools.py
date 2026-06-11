import io

import pikepdf
import pypdf
import pytest

from pdfsmith.tools.helpers import ToolError
from pdfsmith.tools.secure import run_metadata, run_protect, run_repair, run_unlock
from tests.conftest import upload


def test_protect_encrypts(pdf3):
    result = run_protect([upload("doc.pdf", pdf3)], {"password": "s3cret"})
    assert pypdf.PdfReader(io.BytesIO(result.data)).is_encrypted
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(io.BytesIO(result.data))
    with pikepdf.open(io.BytesIO(result.data), password="s3cret") as pdf:
        assert len(pdf.pages) == 3


def test_protect_rejects_short_password(pdf3):
    with pytest.raises(ToolError):
        run_protect([upload("doc.pdf", pdf3)], {"password": "ab"})


def test_unlock_roundtrip(pdf3):
    protected = run_protect([upload("doc.pdf", pdf3)], {"password": "s3cret"})
    unlocked = run_unlock([upload("doc.pdf", protected.data)], {"password": "s3cret"})
    reader = pypdf.PdfReader(io.BytesIO(unlocked.data))
    assert not reader.is_encrypted
    assert len(reader.pages) == 3


def test_unlock_wrong_password(pdf3):
    protected = run_protect([upload("doc.pdf", pdf3)], {"password": "s3cret"})
    with pytest.raises(ToolError, match="wrong password"):
        run_unlock([upload("doc.pdf", protected.data)], {"password": "nope"})


def test_encrypted_pdf_in_normal_tool_gives_clean_error(pdf3):
    from pdfsmith.tools.basic import run_merge

    protected = run_protect([upload("doc.pdf", pdf3)], {"password": "s3cret"})
    with pytest.raises(ToolError, match="[Uu]nlock"):
        run_merge([upload("a.pdf", pdf3), upload("b.pdf", protected.data)], {})


def test_repair_fixes_trailing_garbage(pdf3):
    damaged = pdf3 + b"\n%% garbage after EOF " * 200
    result = run_repair([upload("doc.pdf", damaged)], {})
    assert len(pypdf.PdfReader(io.BytesIO(result.data)).pages) == 3


def test_repair_rejects_hopeless_input():
    with pytest.raises(ToolError):
        run_repair([upload("doc.pdf", b"there is no pdf here")], {})


def test_metadata_sets_fields(pdf3):
    result = run_metadata(
        [upload("doc.pdf", pdf3)],
        {"title": "Quarterly Report", "author": "Vishal", "subject": "Numbers"},
    )
    with pikepdf.open(io.BytesIO(result.data)) as pdf:
        with pdf.open_metadata() as meta:
            assert meta["dc:title"] == "Quarterly Report"
            assert "Vishal" in str(meta["dc:creator"])
