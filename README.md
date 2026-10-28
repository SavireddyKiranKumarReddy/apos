# Advanced Professional Suite

**Every document tool, one tab.** Convert, edit, merge, split, compress, protect, sign, redact and more — a fast, self-hostable alternative to iLovePDF with advanced capabilities.

```bash
pip install -e .
aps serve          # → http://127.0.0.1:8000
```

or with all tools enabled (LibreOffice, OCR, Ghostscript):

```bash
docker compose up --build
```

## Features

### Organize
- **Merge PDF** - Combine PDFs in any order
- **Split PDF** - Extract page ranges or burst into separate files
- **Organize** - Reorder, duplicate, or delete pages visually
- **Rotate** - Rotate pages individually or all at once
- **Remove pages** - Delete unwanted pages
- **Crop** - Trim page margins

### Convert
- **Images → PDF** - JPG, PNG to PDF
- **PDF → Images** - Export as PNG/JPG at various resolutions
- **PDF → Word/Excel/PowerPoint** - Convert to editable formats
- **Office → PDF** - Word, Excel, PowerPoint, OpenDocument
- **HTML → PDF** - Convert web pages to PDF
- **PDF → PDF/A** - Archive-ready format

### Optimize & Edit
- **Compress PDF** - Reduce file size with lossless/balanced/strong options
- **Edit PDF** - Add text, images, shapes with visual editor
- **Watermark** - Add text watermarks
- **Page numbers** - Add page numbers with custom formatting
- **Crop & Resize** - Adjust page dimensions
- **Metadata** - Edit document properties

### Security & Signatures
- **Protect PDF** - AES-256 password encryption
- **Unlock PDF** - Remove passwords
- **Sign PDF** - PAdES digital signatures
- **Verify signatures** - Validate digital signatures
- **Redact** - Permanently remove sensitive content
- **Auto-redact** - Detect and redact PII (emails, phones, SSNs, etc.)

### Analyze & More
- **Compare PDFs** - Side-by-side comparison
- **OCR** - Make scanned documents searchable
- **Extract text** - Get plain text
- **Repair PDF** - Fix corrupted PDFs
- **Fill forms** - Fill PDF forms
- **AI Summarize/Translate** - AI-powered features
- **Workflows** - Chain multiple tools together

## Why Choose Advanced Professional Suite

- **🔒 Privacy First** - Files processed in memory, never stored. No accounts required.
- **⚡ Lightning Fast** - Optimized for speed with minimal overhead
- **🌐 Self-Hostable** - Run on your own server with full control
- **🔌 API Ready** - Clean REST API for automation and integration
- **🎨 Modern UI** - Clean, intuitive interface
- **🛠️ Extensible** - Easy to add custom tools
- **📦 All-in-One** - 30+ tools in a single application

## Quick Start

### Docker (Recommended)
```bash
docker compose up -d
# Open http://localhost:8000
```

### Local Development
```bash
pip install -e ".[dev,ocr,ai]"
aps serve
```

## API Usage

```bash
# Merge PDFs
curl -F "files=@a.pdf" -F "files=@b.pdf" -o merged.pdf \
  http://localhost:8000/api/tools/merge

# Compress PDF
curl -F "files=@big.pdf" -F "level=balanced" -o small.pdf \
  http://localhost:8000/api/tools/compress

# List all tools
curl http://localhost:8000/api/tools

# Run workflow
curl -F "files=@doc.pdf" -o result.pdf \
  -F 'steps=[{"tool":"watermark","options":{"text":"CONFIDENTIAL"}},{"tool":"compress"}]' \
  http://localhost:8000/api/workflows/run
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PDFSMITH_MAX_MB` or `MAX_UPLOAD_MB` | `50` | Max upload size in MB |
| `RATE_LIMIT_ENABLED` | `true` | Enable rate limiting |
| `RATE_LIMIT_REQUESTS` | `60` | Requests per window |
| `RATE_LIMIT_WINDOW` | `60` | Window in seconds |
| `MAX_WORKERS` | `4` | Thread pool size |
| `ALLOW_AI_TOOLS` | `true` | Enable AI features |

## Architecture

Built on FastAPI with a clean tool registry pattern. Each tool is self-contained and auto-discovered. Frontend is vanilla JS/CSS with no build step for simplicity.

## License

MIT License - see [LICENSE](LICENSE) for details.

*Based on [pdfsmith](https://github.com/vishalblz10/pdfsmith) by Vishal.*
