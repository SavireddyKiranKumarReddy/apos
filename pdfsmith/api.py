"""The HTTP layer: a thin FastAPI app over the tool registry.

Files are processed in memory and never written to disk on the happy path —
nothing to clean up, nothing left behind. Uploads are capped by
``PDFSMITH_MAX_MB`` (default 50) per request.
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from pdfsmith import __version__
from pdfsmith.tools import all_tools, get_tool
from pdfsmith.tools.helpers import ToolError
from pdfsmith.tools.registry import UploadedFile

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def max_upload_bytes() -> int:
    return int(os.getenv("PDFSMITH_MAX_MB", "50")) * 1024 * 1024


def create_app() -> FastAPI:
    app = FastAPI(title="pdfsmith", version=__version__)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/api/tools")
    def list_tools() -> dict:
        return {
            "tools": [tool.describe() for tool in all_tools()],
            "max_upload_mb": max_upload_bytes() // (1024 * 1024),
        }

    async def collect_form(request: Request) -> tuple[list[UploadedFile], dict[str, str]]:
        form = await request.form()
        files: list[UploadedFile] = []
        options: dict[str, str] = {}
        total = 0
        for key, value in form.multi_items():
            if hasattr(value, "read"):  # an upload
                data = await value.read()
                total += len(data)
                if total > max_upload_bytes():
                    raise HTTPException(413, f"uploads are capped at "
                                             f"{max_upload_bytes() // (1024 * 1024)} MB")
                if data:
                    files.append(UploadedFile(name=value.filename or "file", data=data))
            else:
                options[key] = str(value)
        return files, options

    def file_response(result) -> Response:
        quoted = urllib.parse.quote(result.filename)
        return Response(
            content=result.data,
            media_type=result.media_type,
            headers={"Content-Disposition": f'attachment; filename="{quoted}"'},
        )

    @app.post("/api/tools/{name}")
    async def run_tool(name: str, request: Request) -> Response:
        try:
            tool = get_tool(name)
        except KeyError:
            raise HTTPException(404, f"no tool called {name!r}")
        if not tool.available():
            raise HTTPException(503, f"{tool.label} is not available on this server "
                                     f"({tool.unavailable_hint})")

        files, options = await collect_form(request)
        if len(files) < tool.min_files:
            raise HTTPException(400, f"{tool.label} needs at least {tool.min_files} file(s)")
        if not tool.multiple and len(files) > 1:
            raise HTTPException(400, f"{tool.label} takes a single file")

        try:
            # A worker thread keeps slow tools (LibreOffice, OCR, signing) from
            # blocking the event loop — and pyhanko's internal asyncio.run()
            # requires being off the loop thread entirely.
            result = await run_in_threadpool(tool.run, files, options)
        except ToolError as exc:
            raise HTTPException(400, str(exc))
        return file_response(result)

    @app.post("/api/workflows/run")
    async def run_workflow_endpoint(request: Request) -> Response:
        import json

        from pdfsmith.workflows import run_workflow

        files, options = await collect_form(request)
        try:
            steps = json.loads(options.get("steps", "[]"))
        except json.JSONDecodeError:
            raise HTTPException(400, "steps must be valid JSON")

        try:
            result = await run_in_threadpool(run_workflow, files, steps)
        except ToolError as exc:
            raise HTTPException(400, str(exc))
        return file_response(result)

    @app.post("/api/inspect/words")
    async def inspect_words(request: Request) -> dict:
        from pdfsmith.tools.redact_auto import detect_word_boxes

        form = await request.form()
        for _, value in form.multi_items():
            if hasattr(value, "read"):
                data = await value.read()
                if len(data) > max_upload_bytes():
                    raise HTTPException(413, "file too large")
                try:
                    return {"pages": await run_in_threadpool(detect_word_boxes, data)}
                except ToolError as exc:
                    raise HTTPException(400, str(exc))
        raise HTTPException(400, "upload a PDF to inspect")

    @app.post("/api/inspect/form-fields")
    async def inspect_form_fields(request: Request) -> dict:
        from pdfsmith.tools.forms import list_form_fields

        form = await request.form()
        for _, value in form.multi_items():
            if hasattr(value, "read"):
                data = await value.read()
                if len(data) > max_upload_bytes():
                    raise HTTPException(413, "file too large")
                try:
                    return {"fields": await run_in_threadpool(list_form_fields, data)}
                except ToolError as exc:
                    raise HTTPException(400, str(exc))
        raise HTTPException(400, "upload a PDF to inspect")

    if STATIC_DIR.exists():
        from fastapi.responses import HTMLResponse
        from functools import lru_cache

        @lru_cache(maxsize=1)
        def index_html() -> str:
            # {{v}} on asset URLs busts browser caches on every release — a
            # stale app.css against new markup renders as an unstyled mess.
            return (STATIC_DIR / "index.html").read_text().replace("{{v}}", __version__)

        @app.get("/")
        def index() -> HTMLResponse:
            # never let the shell go stale — it carries the {{v}} that busts
            # every asset; if the HTML is cached, a new release is never seen.
            return HTMLResponse(index_html(), headers={"Cache-Control": "no-cache"})

        js_dir = (STATIC_DIR / "js").resolve()

        @app.get("/static/js/{name}")
        def serve_js(name: str) -> Response:
            # ES-module imports (./editor.js?v=…) need the same {{v}} cache-bust
            # as the HTML, or a fresh app.js loads a stale editor.js and the
            # import bindings break. Templated here; everything else under
            # /static is served untouched by the mount below.
            path = (js_dir / name).resolve()
            if path.parent != js_dir or path.suffix != ".js" or not path.is_file():
                raise HTTPException(404, "not found")
            body = path.read_text().replace("{{v}}", __version__)
            return Response(content=body, media_type="text/javascript")

        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/{path:path}")
        def spa_fallback(path: str) -> HTMLResponse:
            # Client-side routes (/category/…, /tool/…, /workflows, /login)
            # all serve the app shell; real API/static misses stay 404s.
            if path.startswith(("api/", "static/")) or path == "healthz":
                raise HTTPException(404, "not found")
            return HTMLResponse(index_html(), headers={"Cache-Control": "no-cache"})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    return app


app = create_app()
