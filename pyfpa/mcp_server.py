"""Local stdio MCP server over the package's own forecast and variance functions.

``openfpa mcp-serve <folder>`` reads newline-delimited JSON-RPC 2.0 messages
from stdin and writes one response per request to stdout. It opens no network
listener, and every path a tool reads or writes must resolve inside the folder
the caller named when starting it.
"""
from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, TextIO

import yaml

from pyfpa.analysis.reconcile import reconcile
from pyfpa.cash13.forecast import cash13_forecast
from pyfpa.cash13.runway import runway_summary
from pyfpa.io.loaders import load_cash13_config
from pyfpa.io.reporting import forecast_to_excel

# Revisions that open with the initialize handshake; the first is offered when a
# client asks for one this server does not know.
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602


class ToolError(ValueError):
    """A tool refused its arguments; reported to the caller as a tool error."""


def _server_version() -> str:
    try:
        return version("au-fpa-pack")
    except PackageNotFoundError:
        return "source"


def confined_path(root: Path, relative: object, *, label: str) -> Path:
    """Resolve ``relative`` under ``root``, refusing anything that lands outside it.

    The path is resolved first, so ``..`` segments and symbolic links are
    judged by where they lead, not how they are spelt.
    """
    if not isinstance(relative, str) or not relative:
        raise ToolError(f"{label} must be a non-empty path relative to the server folder")
    candidate = Path(relative)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        raise ToolError(f"{label} must be relative to the server folder, not {relative!r}")
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise ToolError(f"{label} {relative!r} leaves the server folder")
    return resolved


def _cash13_workbook(root: Path, arguments: Mapping[str, Any]) -> dict[str, Any]:
    config = confined_path(root, arguments.get("config"), label="config")
    out = confined_path(root, arguments.get("out"), label="out")
    if out.suffix.lower() != ".xlsx":
        raise ToolError("out must name an .xlsx file")
    if out == config:
        raise ToolError("out must not overwrite the configuration")
    cfg = load_cash13_config(config)
    weekly = cash13_forecast(cfg)
    out.parent.mkdir(parents=True, exist_ok=True)
    forecast_to_excel(weekly, out)
    return {
        "workbook": out.relative_to(root).as_posix(),
        "weeks": cfg.weeks,
        "closing_cash": float(weekly["ending_cash"].iloc[-1]),
        "runway": runway_summary(weekly, cfg.headroom_buffer),
    }


def _amounts(arguments: Mapping[str, Any], key: str) -> dict[str, float]:
    values = arguments.get(key)
    if not isinstance(values, dict):
        raise ToolError(f"{key} must be an object of line name to amount")
    for line, amount in values.items():
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise ToolError(f"{key} line {line!r} must be a number")
    return {str(line): float(amount) for line, amount in values.items()}


def _variance_summary(root: Path, arguments: Mapping[str, Any]) -> dict[str, Any]:
    tolerance = arguments.get("tolerance", 0.01)
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) \
            or not 0 <= tolerance < math.inf:
        raise ToolError("tolerance must be a finite number, not negative")
    table = reconcile(_amounts(arguments, "model"), _amounts(arguments, "actual"),
                      tolerance=float(tolerance))
    lines = [
        {
            "line": str(line),
            "model": row.model,
            "actual": row.actual,
            "variance": row.variance,
            # Undefined against a zero actual: JSON has no NaN, so it is null.
            "variance_pct": None if math.isnan(row.variance_pct) else row.variance_pct,
            "within_tolerance": bool(row.within_tolerance),
        }
        for line, row in table.iterrows()
    ]
    outside = [line["line"] for line in lines if not line["within_tolerance"]]
    largest = max(lines, key=lambda line: abs(line["variance"]), default=None)
    return {
        "tolerance": float(tolerance),
        "lines": lines,
        "outside_tolerance": outside,
        "largest_variance_line": None if largest is None else largest["line"],
        "net_variance": sum(line["variance"] for line in lines),
    }


_PATH = {"type": "string", "description": "Path relative to the server folder."}
_AMOUNTS = {"type": "object", "additionalProperties": {"type": "number"}}
TOOLS: dict[str, tuple[dict[str, Any], Callable[[Path, Mapping[str, Any]], dict[str, Any]]]] = {
    "cash13_workbook": (
        {
            "name": "cash13_workbook",
            "title": "13-week cash flow workbook",
            "description": (
                "Build the 13-week direct-method cash flow from a Cash13Config YAML file "
                "and write it to an .xlsx workbook; returns the cash trough, closing cash "
                "and the weeks below zero."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"config": _PATH, "out": _PATH},
                "required": ["config", "out"],
                "additionalProperties": False,
            },
        },
        _cash13_workbook,
    ),
    "variance_summary": (
        {
            "name": "variance_summary",
            "title": "Variance summary",
            "description": (
                "Compare modelled and actual amounts line by line: variance is model less "
                "actual, its percentage is of the absolute actual, and each line is within "
                "tolerance or not. Both objects must name the same lines."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "model": _AMOUNTS,
                    "actual": _AMOUNTS,
                    "tolerance": {"type": "number", "minimum": 0, "default": 0.01},
                },
                "required": ["model", "actual"],
                "additionalProperties": False,
            },
        },
        _variance_summary,
    ),
}


def _error(message_id: object, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def _call_tool(root: Path, message_id: object, params: Mapping[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    if not isinstance(name, str) or name not in TOOLS:
        return _error(message_id, _INVALID_PARAMS, f"unknown tool: {name!r}")
    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        return _error(message_id, _INVALID_PARAMS, "arguments must be an object")
    try:
        result = TOOLS[name][1](root, arguments)
    except (ValueError, OverflowError, OSError, yaml.YAMLError) as exc:
        # Tool failures go back as results the model can read and act on.
        return {"jsonrpc": "2.0", "id": message_id, "result": {
            "content": [{"type": "text", "text": str(exc)}], "isError": True}}
    text = json.dumps(result, allow_nan=False)
    return {"jsonrpc": "2.0", "id": message_id, "result": {
        "content": [{"type": "text", "text": text}], "structuredContent": result}}


def handle(root: Path, message: object) -> dict[str, Any] | None:
    """Answer one decoded JSON-RPC message; notifications get no answer."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" \
            or not isinstance(message.get("method"), str):
        return _error(message.get("id") if isinstance(message, dict) else None,
                      _INVALID_REQUEST, "not a JSON-RPC 2.0 request")
    if "id" not in message:
        return None
    message_id, method = message["id"], message["method"]
    params = message.get("params", {})
    if not isinstance(params, dict):
        return _error(message_id, _INVALID_PARAMS, "params must be an object")
    if method == "initialize":
        asked = params.get("protocolVersion")
        return {"jsonrpc": "2.0", "id": message_id, "result": {
            "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "openfpa", "version": _server_version()},
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": message_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": message_id,
                "result": {"tools": [spec for spec, _ in TOOLS.values()]}}
    if method == "tools/call":
        return _call_tool(root, message_id, params)
    return _error(message_id, _METHOD_NOT_FOUND, f"method not found: {method}")


def serve(root: str | Path, stdin: TextIO, stdout: TextIO) -> None:
    """Answer messages from ``stdin`` until it closes, confined to ``root``."""
    folder = Path(root).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError(f"server folder does not exist: {folder}")
    for raw in stdin:
        if not raw.strip():
            continue
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            reply: dict[str, Any] | None = _error(None, _PARSE_ERROR, "message is not valid JSON")
        else:
            reply = handle(folder, message)
        if reply is not None:
            stdout.write(json.dumps(reply, allow_nan=False) + "\n")
            stdout.flush()
