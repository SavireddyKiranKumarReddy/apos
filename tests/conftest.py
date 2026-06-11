import io

import pytest
from reportlab.pdfgen import canvas as rl_canvas

from pdfsmith.tools.registry import UploadedFile

PAGE_WORDS = ("Alpha", "Bravo", "Charlie")


def make_text_pdf(words=PAGE_WORDS, compress: bool = False) -> bytes:
    """A simple multi-page PDF with one marker word per page.

    ``compress=False`` leaves content streams uncompressed, which gives the
    compression tests something real to shrink.
    """
    buffer = io.BytesIO()
    canvas = rl_canvas.Canvas(buffer, pagesize=(612, 792), pageCompression=1 if compress else 0)
    for index, word in enumerate(words, start=1):
        canvas.setFont("Helvetica", 24)
        canvas.drawString(72, 700, f"{word} marker page {index}")
        canvas.setFont("Helvetica", 11)
        for line in range(28):
            canvas.drawString(72, 640 - line * 18, f"{word} body line {line} " * 3)
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def make_png(size=(220, 140), color=(200, 40, 60), mode="RGB") -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new(mode, size, color if mode == "RGB" else (*color, 128)).save(buffer, format="PNG")
    return buffer.getvalue()


def upload(name: str, data: bytes) -> UploadedFile:
    return UploadedFile(name=name, data=data)


@pytest.fixture(scope="session")
def client_module():
    from fastapi.testclient import TestClient

    from pdfsmith.api import create_app

    return TestClient(create_app())


@pytest.fixture(scope="session")
def pdf3() -> bytes:
    return make_text_pdf()


@pytest.fixture(scope="session")
def pdf2() -> bytes:
    return make_text_pdf(("Delta", "Echo"))
