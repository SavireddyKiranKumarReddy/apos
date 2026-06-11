"""Importing this package registers every tool."""

from pdfsmith.tools import (  # noqa: F401
    analyze,
    basic,
    convert,
    convert_more,
    edit,
    forms,
    secure,
    sign,
    transform,
)
from pdfsmith.tools.registry import all_tools, get_tool

__all__ = ["all_tools", "get_tool"]
