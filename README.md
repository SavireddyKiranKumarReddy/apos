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
| 🖼️ | **Images → PDF** | JPG/PNG (alpha handled) into one document |
| 📸 | **PDF → Images** | crisp PNG/JPG at 72/150/300 dpi |
| 📝 | **PDF → Word** | editable `.docx` via pdf2docx |
| 📄 | **Office → PDF** | Word/Excel/PowerPoint/OpenDocument via LibreOffice* |
| 🔍 | **OCR** | make scans searchable via Tesseract + ocrmypdf* |
| 📜 | **Extract text** | the whole document as `.txt` |
| 🔒 | **Protect** | AES-256 password encryption |
| 🔓 | **Unlock** | remove a password you know |
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
    registry.py   Tool dataclass: options schema, availability probe, runner
    basic.py      merge, split, organize, rotate          (pypdf)
    transform.py  watermark, page numbers, compress       (reportlab, pikepdf, gs)
    convert.py    images↔pdf, pdf→word, office→pdf, ocr   (pypdfium2, img2pdf, …)
    secure.py     protect, unlock, repair, metadata       (pikepdf)
  api.py          FastAPI: GET /api/tools, POST /api/tools/{name}
static/           the frontend (no build step)
deploy/DEPLOY.md  Fly.io / Render / Railway / VPS+Caddy recipes
```

Every tool is a pure function `(files, options) → result`, registered with a
schema the frontend renders automatically — adding a tool is one function and
one `register()` call, and it appears in the UI with its options, no
frontend work.

## Tests

51 tests cover every tool (page counts, rotation flags, AES round-trips,
watermark text in extracted output, compression that never returns a bigger
file, alpha-channel images, damaged-file repair) plus the full HTTP layer
(error shapes, upload caps, content-disposition). CI also boots the real
server and merges PDFs over HTTP, then builds the Docker image and asserts
**all 17 tools** report available inside it.

```bash
pip install -e ".[dev]"
pytest
```

## Hosting

See [deploy/DEPLOY.md](deploy/DEPLOY.md) — a $4 VPS with docker-compose and
Caddy gives you HTTPS in ten minutes; Fly.io/Render/Railway recipes included.

## License

MIT
