"""The workflow engine: chain tools into reusable pipelines.

A workflow is a list of steps, each naming a tool and its options. Files flow
through the chain: single-file tools map over every current file, multi-file
tools (merge, compare) consume the whole set and produce one result. Every
step except the last must produce PDFs — converters that leave PDF-land
(images, Word, text) are only valid as the final step. The first step may
accept non-PDF input (images → PDF, Office → PDF), which is how a workflow
like "convert, watermark, compress, merge" starts from a stack of documents.
"""

from __future__ import annotations

from pdfsmith.tools import get_tool
from pdfsmith.tools.helpers import ToolError, zip_files
from pdfsmith.tools.registry import Tool, ToolResult, UploadedFile

MAX_STEPS = 10


def _validate_steps(steps: list) -> list[tuple[Tool, dict]]:
    if not isinstance(steps, list) or not steps:
        raise ToolError("a workflow needs at least one step")
    if len(steps) > MAX_STEPS:
        raise ToolError(f"workflows are capped at {MAX_STEPS} steps")

    resolved: list[tuple[Tool, dict]] = []
    for position, step in enumerate(steps, start=1):
        if not isinstance(step, dict) or "tool" not in step:
            raise ToolError(f"step {position} must look like "
                            '{"tool": "watermark", "options": {...}}')
        try:
            tool = get_tool(str(step["tool"]))
        except KeyError:
            raise ToolError(f"step {position}: no tool called {step['tool']!r}") from None
        if not tool.available():
            raise ToolError(f"step {position}: {tool.label} is not available on this "
                            f"server ({tool.unavailable_hint})")

        is_last = position == len(steps)
        if not is_last and not tool.produces_pdf:
            raise ToolError(
                f"step {position}: {tool.label} produces a non-PDF result, so it can "
                f"only be the last step of a workflow"
            )
        if position > 1 and ".pdf" not in tool.accepts and tool.accepts != "image/*":
            raise ToolError(
                f"step {position}: {tool.label} does not take PDF input, so it can "
                f"only be the first step of a workflow"
            )
        if position > 1 and tool.accepts == "image/*":
            raise ToolError(
                f"step {position}: {tool.label} takes images, so it can only be the "
                f"first step of a workflow"
            )

        options = step.get("options") or {}
        if not isinstance(options, dict):
            raise ToolError(f"step {position}: options must be an object")
        resolved.append((tool, {str(k): str(v) for k, v in options.items()}))
    return resolved


def run_workflow(files: list[UploadedFile], steps: list) -> ToolResult:
    if not files:
        raise ToolError("add at least one file to run a workflow on")
    chain = _validate_steps(steps)

    current = list(files)
    results: list[ToolResult] = []
    for position, (tool, options) in enumerate(chain, start=1):
        try:
            if tool.multiple:
                results = [tool.run(current, options)]
            else:
                results = [tool.run([single], options) for single in current]
        except ToolError as exc:
            raise ToolError(f"step {position} ({tool.label}): {exc}") from exc
        current = [
            UploadedFile(name=result.filename, data=result.data) for result in results
        ]

    if len(results) == 1:
        return results[0]

    entries = []
    seen: set[str] = set()
    for index, result in enumerate(results, start=1):
        name = result.filename if result.filename not in seen else f"{index:02d}_{result.filename}"
        seen.add(name)
        entries.append((name, result.data))
    return ToolResult("workflow_results.zip", zip_files(entries), "application/zip")
