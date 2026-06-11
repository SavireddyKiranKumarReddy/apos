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
from fastapi.responses import FileResponse, JSONResponse, Response
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

    @app.post("/api/tools/{name}")
    async def run_tool(name: str, request: Request) -> Response:
        try:
            tool = get_tool(name)
        except KeyError:
            raise HTTPException(404, f"no tool called {name!r}")
        if not tool.available():
            raise HTTPException(503, f"{tool.label} is not available on this server "
                                     f"({tool.unavailable_hint})")

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

        if len(files) < tool.min_files:
            raise HTTPException(400, f"{tool.label} needs at least {tool.min_files} file(s)")
        if not tool.multiple and len(files) > 1:
            raise HTTPException(400, f"{tool.label} takes a single file")

        try:
            result = tool.run(files, options)
        except ToolError as exc:
            raise HTTPException(400, str(exc))

        quoted = urllib.parse.quote(result.filename)
        return Response(
            content=result.data,
            media_type=result.media_type,
            headers={"Content-Disposition": f'attachment; filename="{quoted}"'},
        )

    if STATIC_DIR.exists():
        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    return app


app = create_app()
