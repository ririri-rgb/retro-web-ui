"""Versioned contracts shared by the CLI, Skill manifest, and tests."""

from __future__ import annotations

from typing import Any, Iterable, Optional

TOOL_NAME = "retro-web-ui"
TOOL_VERSION = "1.1.0"
CLI_API_VERSION = 1
JSON_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
THEME_SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_REVIEW = 1
EXIT_ERROR = 2
EXIT_INCOMPATIBLE = 3
EXIT_EXECUTION_FAILED = 4


def diagnostic(
    code: str,
    severity: str,
    message: str,
    *,
    path: Optional[str] = None,
    hint: Optional[str] = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {"code": code, "severity": severity, "message": message}
    if path is not None:
        item["path"] = path
    if hint is not None:
        item["hint"] = hint
    return item


def envelope(
    command: str,
    status: str,
    result: Any,
    diagnostics: Iterable[dict[str, Any]] = (),
    *,
    target: Optional[str] = None,
    read_only: bool = True,
) -> dict[str, Any]:
    meta: dict[str, Any] = {"read_only": read_only}
    if target is not None:
        meta["target"] = target
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "tool": {
            "name": TOOL_NAME,
            "version": TOOL_VERSION,
            "cli_api_version": CLI_API_VERSION,
        },
        "command": command,
        "status": status,
        "result": result,
        "diagnostics": list(diagnostics),
        "meta": meta,
    }
