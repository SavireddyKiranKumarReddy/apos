import datetime
import io

import pytest

from pdfsmith.tools.helpers import ToolError
from pdfsmith.tools.sign import run_sign, run_verify
from tests.conftest import upload


def make_p12(password: bytes | None = b"test-pass") -> bytes:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test Signer")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject).issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    encryption = (
        serialization.BestAvailableEncryption(password)
        if password else serialization.NoEncryption()
    )
    return pkcs12.serialize_key_and_certificates(b"test", key, cert, None, encryption)


def embedded_signatures(data: bytes):
    from pyhanko.pdf_utils.reader import PdfFileReader

    return PdfFileReader(io.BytesIO(data)).embedded_signatures


def assert_intact(data: bytes):
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    (signature,) = embedded_signatures(data)
    status = validate_pdf_signature(
        signature,
        ValidationContext(trust_roots=[signature.signer_cert], allow_fetching=False),
    )
    assert status.intact
    assert status.valid


def test_sign_with_generated_certificate(pdf3):
    result = run_sign([upload("doc.pdf", pdf3)],
                      {"name": "Vishal", "organization": "pdfsmith"})
    assert result.filename.endswith("_signed.pdf")
    assert_intact(result.data)
    (signature,) = embedded_signatures(result.data)
    assert "Vishal" in signature.signer_cert.subject.human_friendly


def test_sign_with_uploaded_p12(pdf3):
    p12 = make_p12(b"test-pass")
    result = run_sign(
        [upload("doc.pdf", pdf3), upload("me.p12", p12)],
        {"password": "test-pass", "reason": "approval"},
    )
    assert_intact(result.data)


def test_sign_wrong_p12_password(pdf3):
    p12 = make_p12(b"test-pass")
    with pytest.raises(ToolError):
        run_sign([upload("doc.pdf", pdf3), upload("me.p12", p12)], {"password": "nope"})


def test_sign_needs_name_or_certificate(pdf3):
    with pytest.raises(ToolError, match="name"):
        run_sign([upload("doc.pdf", pdf3)], {})


def test_visible_signature_stamp(pdf3):
    result = run_sign([upload("doc.pdf", pdf3)],
                      {"name": "Vishal", "visible": "true", "page": "1"})
    assert_intact(result.data)
    import pypdf

    first_page = pypdf.PdfReader(io.BytesIO(result.data)).pages[0]
    assert first_page.get("/Annots")  # the stamp widget is on the page


def test_tampering_breaks_intactness(pdf3):
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    signed = run_sign([upload("doc.pdf", pdf3)], {"name": "Vishal"}).data
    tampered = signed.replace(b"Alpha", b"Delta", 1)
    (signature,) = embedded_signatures(tampered)
    status = validate_pdf_signature(
        signature,
        ValidationContext(trust_roots=[signature.signer_cert], allow_fetching=False),
    )
    assert not status.intact


def test_verify_report(pdf3):
    signed = run_sign([upload("doc.pdf", pdf3)], {"name": "Vishal"}).data
    report = run_verify([upload("signed.pdf", signed)], {}).data.decode()
    assert "intact (document unmodified): yes" in report
    assert "Vishal" in report

    unsigned_report = run_verify([upload("doc.pdf", pdf3)], {}).data.decode()
    assert "No digital signatures found" in unsigned_report
