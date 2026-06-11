"""Certificate-based digital signatures (PAdES) via pyHanko.

Two ways to sign: upload a PKCS#12 certificate (.p12/.pfx) with its password,
or let pdfsmith generate a self-signed certificate from a name — useful for
tamper-evidence when no CA-issued certificate exists (validators will report
the signature as valid-but-untrusted, which is exactly what it is).
"""

from __future__ import annotations

import datetime
import io
import tempfile
from pathlib import Path

from pdfsmith.tools.helpers import ToolError, read_pdf, safe_stem
from pdfsmith.tools.registry import Option, Tool, ToolResult, UploadedFile, register

SIGNATURE_FIELD = "PdfsmithSignature"


def _split_uploads(files: list[UploadedFile]) -> tuple[UploadedFile, UploadedFile | None]:
    pdfs = [f for f in files if f.name.lower().endswith(".pdf")]
    certs = [f for f in files if f.name.lower().endswith((".p12", ".pfx"))]
    if len(pdfs) != 1:
        raise ToolError("upload exactly one PDF (plus optionally one .p12/.pfx certificate)")
    return pdfs[0], (certs[0] if certs else None)


def _self_signed_signer(name: str, organization: str):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from pyhanko.sign import signers

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization or "pdfsmith"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=730))
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=True, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .sign(key, hashes.SHA256())
    )

    with tempfile.TemporaryDirectory() as tmp:
        key_path = Path(tmp) / "key.pem"
        cert_path = Path(tmp) / "cert.pem"
        key_path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        return signers.SimpleSigner.load(str(key_path), str(cert_path), key_passphrase=None)


def run_sign(files: list[UploadedFile], options: dict) -> ToolResult:
    from pyhanko import stamp
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers

    pdf_file, cert_file = _split_uploads(files)

    if cert_file is not None:
        password = str(options.get("password", ""))
        with tempfile.TemporaryDirectory() as tmp:
            p12_path = Path(tmp) / "cert.p12"
            p12_path.write_bytes(cert_file.data)
            signer = signers.SimpleSigner.load_pkcs12(
                str(p12_path), passphrase=password.encode() if password else None
            )
        if signer is None:
            raise ToolError("could not open the certificate — wrong password?")
    else:
        name = str(options.get("name", "")).strip()
        if not name:
            raise ToolError("provide a signer name (or upload a .p12 certificate)")
        signer = _self_signed_signer(name, str(options.get("organization", "")).strip())

    visible = str(options.get("visible", "")).lower() in ("true", "on", "1", "yes")
    writer = IncrementalPdfFileWriter(io.BytesIO(pdf_file.data))

    if visible:
        page_count = len(read_pdf(pdf_file.data).pages)
        page = min(max(1, int(options.get("page", 1) or 1)), page_count) - 1
        box_page = read_pdf(pdf_file.data).pages[page]
        width = float(box_page.mediabox.width)
        fields.append_signature_field(
            writer,
            fields.SigFieldSpec(SIGNATURE_FIELD, on_page=page,
                                box=(width - 240, 30, width - 30, 96)),
        )

    metadata = signers.PdfSignatureMetadata(
        field_name=SIGNATURE_FIELD,
        reason=str(options.get("reason", "")).strip() or None,
        location=str(options.get("location", "")).strip() or None,
    )
    style = stamp.TextStampStyle(
        stamp_text="Digitally signed by %(signer)s\n%(ts)s",
        background_opacity=0.12,
    ) if visible else None

    try:
        output = signers.PdfSigner(metadata, signer=signer, stamp_style=style).sign_pdf(writer)
    except Exception as exc:
        raise ToolError(f"signing failed: {exc}") from exc
    return ToolResult(f"{safe_stem(pdf_file.name)}_signed.pdf", output.getvalue())


def run_verify(files: list[UploadedFile], options: dict) -> ToolResult:
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    (uploaded,) = files
    try:
        reader = PdfFileReader(io.BytesIO(uploaded.data))
        signatures = reader.embedded_signatures
    except Exception as exc:
        raise ToolError("could not read this PDF") from exc

    lines = [f"Signature report for {uploaded.name}", "=" * 48, ""]
    if not signatures:
        lines.append("No digital signatures found.")
    for index, embedded in enumerate(signatures, start=1):
        lines.append(f"[{index}] field: {embedded.field_name}")
        try:
            signer_cert = embedded.signer_cert
            lines.append(f"    signer: {signer_cert.subject.human_friendly}")
            status = validate_pdf_signature(
                embedded,
                ValidationContext(trust_roots=[signer_cert], allow_fetching=False),
            )
            lines.append(f"    intact (document unmodified): {'yes' if status.intact else 'NO'}")
            lines.append(f"    cryptographically valid:      {'yes' if status.valid else 'NO'}")
            lines.append(f"    summary: {status.summary()}")
        except Exception as exc:
            lines.append(f"    could not validate: {exc}")
        lines.append("")
    lines.append("Note: 'trusted' requires the signer's CA in your trust store; a")
    lines.append("self-signed certificate shows valid + intact but untrusted.")
    return ToolResult(
        f"{safe_stem(uploaded.name)}_signatures.txt",
        ("\n".join(lines) + "\n").encode(),
        "text/plain",
    )


register(Tool(
    name="sign",
    label="Sign PDF",
    description="Real digital signatures: your .p12 certificate, or a generated one.",
    icon="🖋️",
    run=run_sign,
    multiple=True,
    accepts=".pdf,.p12,.pfx",
    options=(
        Option("name", "Signer name", help="used when no certificate is uploaded"),
        Option("organization", "Organization"),
        Option("password", "Certificate password", kind="password",
               help="only for an uploaded .p12/.pfx"),
        Option("reason", "Reason", help="e.g. I approve this document"),
        Option("location", "Location"),
        Option("visible", "Visible signature stamp", kind="checkbox", default=False),
        Option("page", "Stamp on page", kind="number", default=1),
    ),
    category="secure",
))

register(Tool(
    name="verify_signatures",
    produces_pdf=False,
    label="Verify signatures",
    description="Check who signed a PDF and whether it was modified since.",
    icon="🕵️",
    run=run_verify,
    category="secure",
))
