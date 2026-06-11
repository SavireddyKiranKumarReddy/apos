"""Command line entry point: ``pdfsmith serve``."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdfsmith", description="Every PDF tool in one tab.")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true", help="auto-reload (development)")

    args = parser.parse_args(argv)

    import uvicorn

    uvicorn.run("pdfsmith.api:app", host=args.host, port=args.port, reload=args.reload)
    return 0
