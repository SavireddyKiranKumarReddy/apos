"""Importing this package registers every tool."""

from pdfsmith.tools import basic, convert, secure, transform  # noqa: F401
from pdfsmith.tools.registry import all_tools, get_tool

__all__ = ["all_tools", "get_tool"]
