"""The tool registry: one place that knows every tool, its options and
whether it can run in this environment.

Each tool is a function ``(files: list[UploadedFile], options: dict) ->
ToolResult``. Tools that need a system binary (LibreOffice, Ghostscript,
Tesseract) register an availability probe instead of failing at call time —
the API exposes the flag so the UI can grey the tool out with an honest
explanation rather than erroring after an upload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class UploadedFile:
    name: str
    data: bytes


@dataclass(frozen=True)
class ToolResult:
    filename: str
    data: bytes
    media_type: str = "application/pdf"


@dataclass(frozen=True)
class Option:
    """A single tool option, described well enough for the UI to render it."""

    name: str
    label: str
    kind: str = "text"  # text | number | select | checkbox | password
    default: str | int | bool | None = None
    choices: tuple[tuple[str, str], ...] = ()  # (value, label)
    help: str = ""

    def describe(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "kind": self.kind,
            "default": self.default,
            "choices": [{"value": v, "label": l} for v, l in self.choices],
            "help": self.help,
        }


@dataclass(frozen=True)
class Tool:
    name: str
    label: str
    description: str
    icon: str  # emoji used by the UI
    run: Callable[[list[UploadedFile], dict], ToolResult]
    accepts: str = ".pdf"  # accept attribute for the file input
    multiple: bool = False
    min_files: int = 1
    options: tuple[Option, ...] = ()
    wants_pages: bool = False  # UI shows the page-thumbnail picker
    available: Callable[[], bool] = lambda: True
    unavailable_hint: str = ""
    category: str = "core"
    produces_pdf: bool = True  # False → only valid as the last step of a workflow
    interactive: bool = False  # needs per-file UI state; hidden from the workflow builder

    def describe(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "icon": self.icon,
            "accepts": self.accepts,
            "multiple": self.multiple,
            "min_files": self.min_files,
            "options": [option.describe() for option in self.options],
            "wants_pages": self.wants_pages,
            "available": bool(self.available()),
            "unavailable_hint": self.unavailable_hint,
            "category": self.category,
            "produces_pdf": self.produces_pdf,
            "interactive": self.interactive,
        }


_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    if tool.name in _REGISTRY:
        raise ValueError(f"duplicate tool name {tool.name!r}")
    _REGISTRY[tool.name] = tool
    return tool


def get_tool(name: str) -> Tool:
    if name not in _REGISTRY:
        raise KeyError(f"unknown tool {name!r}")
    return _REGISTRY[name]


def all_tools() -> list[Tool]:
    return list(_REGISTRY.values())
