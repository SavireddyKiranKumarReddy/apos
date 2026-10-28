"""Command line entry point: ``apos serve`` or ``pdfsmith serve``."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apos", description="Advanced Professional Suite - Every document tool in one tab.")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true", help="auto-reload (development)")

    args = parser.parse_args(argv)

    import uvicorn

    uvicorn.run("pdfsmith.api:app", host=args.host, port=args.port, reload=args.reload)
    return 0


# Alias for backward compatibility
if __name__ == "__main__":
    main()

