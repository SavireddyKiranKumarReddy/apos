# pdfsmith 🔨

[![ci](https://github.com/vishalblz10/pdfsmith/actions/workflows/ci.yml/badge.svg)](https://github.com/vishalblz10/pdfsmith/actions/workflows/ci.yml)

**Every PDF tool, one tab.** Merge, split, compress, organize, convert,
protect — a fast, self-hostable alternative to the PDF-tools sites, with one
big difference: it runs on *your* server, processes files **in memory**, and
never stores anything.

```bash
pip install -e .
pdfsmith serve          # → http://127.0.0.1:8000
```

or, with every tool enabled (LibreOffice, OCR, Ghostscript included):

```bash
docker compose up --build
```

## The tools

| | Tool | What it does |
|---|---|---|
| 🧩 | **Merge** | combine PDFs in any order |
| ✂️ | **Split** | extract page ranges, or burst into one file per page |
| 🗂️ | **Organize** | reorder / duplicate / delete pages by dragging thumbnails |
| 🔄 | **Rotate** | all pages or just the ones you click |
| 🗜️ | **Compress** | lossless always; balanced/strong via Ghostscript |
| 💧 | **Watermark** | translucent text, diagonal or edges, tunable opacity |
| 🔢 | **Page numbers** | four positions, custom start, `n / total` format |
| ✏️ | **Edit PDF** | type text, stamp images, draw boxes — placed visually on the page |
| 🖊️ | **Fill PDF form** | fields appear as real inputs the moment you add the file |
| 🔲 | **Crop** | trim margins (mm) on all pages or a selection |
| 🗑️ | **Remove pages** | delete the pages you pick |
| 🖼️ | **Images → PDF** | JPG/PNG (alpha handled) into one document |
| 📸 | **PDF → Images** | crisp PNG/JPG at 72/150/300 dpi |
| 📝 | **PDF → Word** | editable `.docx` via pdf2docx |
| 📽️ | **PDF → PowerPoint** | one faithful full-bleed slide per page |
| 📊 | **PDF → Excel** | detected tables into `.xlsx`, one sheet per page |
| 🗄️ | **PDF → PDF/A** | ISO archival format via Ghostscript* |
| 🌐 | **HTML → PDF** | offline rendering, external resources disabled* |
| 📄 | **Office → PDF** | Word/Excel/PowerPoint/OpenDocument via LibreOffice* |
| 🔍 | **OCR** | make scans searchable via Tesseract + ocrmypdf* |
| 📜 | **Extract text** | the whole document as `.txt` |
| 🔒 | **Protect** | AES-256 password encryption |
| 🔓 | **Unlock** | remove a password you know |
| 🖋️ | **Sign PDF** | real PAdES digital signatures: your .p12, or a generated certificate |
| 🕵️ | **Verify signatures** | who signed it, and whether it changed since |
| ⬛ | **Redact** | black boxes that rasterize the page — the text underneath is *gone* |
| ⚖️ | **Compare** | page-by-page text diff plus a visual difference score |
| 🩹 | **Repair** | rebuild damaged cross-reference tables |
| 🏷️ | **Metadata** | set title / author / subject |

\* needs a system binary. The server detects what's installed and the UI
greys out missing tools with an honest hint — the Docker image has
everything, and CI asserts that every tool reports available inside it.

## Why it feels fast

- **No accounts, no upload-to-the-cloud round trip** — your server is the
  cloud, and files live only in RAM for the duration of the request.
- **A no-build frontend** — vanilla JS + modern CSS, dark mode, drag-drop,
  keyboard shortcuts (`/` to search), toast feedback. pdf.js renders page
  thumbnails client-side, so organizing pages is visual: drag to reorder,
  click to select, and the option fields fill themselves in.
- **Honest errors** — "page selection '99' is outside this document (1–2)"
  instead of a spinner that gives up.

## API

The UI is a thin client over a clean API you can script against:

```bash
curl -F "files=@a.pdf" -F "files=@b.pdf" -o merged.pdf \
  localhost:8000/api/tools/merge

curl -F "files=@big.pdf" -F "level=lossless" -o small.pdf \
  localhost:8000/api/tools/compress

curl localhost:8000/api/tools        # tool list + options + availability
```

Errors come back as JSON with a real message; uploads are capped by
`PDFSMITH_MAX_MB` (default 50).

## Architecture

```
pdfsmith/
  tools/
    registry.py      Tool dataclass: options schema, availability probe, runner
    basic.py         merge, split, organize, rotate             (pypdf)
    transform.py     watermark, page numbers, compress          (reportlab, pikepdf, gs)
    convert.py       images↔pdf, pdf→word, office→pdf, ocr      (pypdfium2, img2pdf, …)
    convert_more.py  html→pdf, pdf→pptx, pdf→xlsx, pdf→pdf/a    (weasyprint, python-pptx, pdfplumber)
    edit.py          visual edit overlay, crop, remove, redact  (reportlab, pypdfium2)
    sign.py          PAdES signatures + verification            (pyhanko, cryptography)
    forms.py         AcroForm listing + filling                 (pypdf)
    analyze.py       compare                                    (difflib, pypdfium2)
    secure.py        protect, unlock, repair, metadata          (pikepdf)
  api.py             FastAPI: GET /api/tools, POST /api/tools/{name},
                     POST /api/inspect/form-fields
static/              the frontend (no build step) + the visual page editor
deploy/DEPLOY.md     Fly.io / Render / Railway / VPS+Caddy recipes
```

Every tool is a pure function `(files, options) → result`, registered with a
schema the frontend renders automatically — adding a tool is one function and
one `register()` call, and it appears in the UI with its options, no
frontend work. Tools run on a worker thread pool, so a five-minute LibreOffice
conversion never blocks the next user's merge.

## Honest scoping

Where a capability has hard limits, the tool says so rather than pretending:

- **Edit** is an overlay editor (add text/images/boxes anywhere) — it does not
  rewrite existing content streams like a desktop editor.
- **Redact** rasterizes affected pages, which is *why* the hidden text is
  unrecoverable; redacted pages become images (run OCR after if you need them
  searchable).
- **Sign** produces real, validating PAdES signatures; a generated certificate
  is self-signed, so validators report it valid-but-untrusted unless you
  upload a CA-issued .p12.
- **PDF → PowerPoint** gives one faithful slide image per page; **PDF →
  Excel** extracts ruled tables it can detect and falls back to text rows.

## Tests

82 tests cover every tool (AES and signature round-trips, tamper detection,
redaction that actually removes text, hand-checked crop math, table
extraction, compression that never returns a bigger file) plus the full HTTP
layer (error shapes, upload caps, the event-loop regression for signing). CI
also boots the real server and merges PDFs over HTTP, then builds the Docker
image and asserts **all 29 tools** report available inside it.

```bash
pip install -e ".[dev]"
pytest
```

## Hosting

See [deploy/DEPLOY.md](deploy/DEPLOY.md) — a $4 VPS with docker-compose and
Caddy gives you HTTPS in ten minutes; Fly.io/Render/Railway recipes included.

## License

MIT
