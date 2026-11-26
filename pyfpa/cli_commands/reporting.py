from __future__ import annotations

import argparse
import hashlib
import io
import sys
from datetime import date
from pathlib import Path
from typing import cast

import yaml

from pyfpa.cli_helpers import _failure, _require_initialized, _root, _success
from pyfpa.memory.workspace import Workspace


def command_model_assumptions(args: argparse.Namespace) -> int:
    from pyfpa.analysis.assumptions import assumption_report
    from pyfpa.config.loader import config_from_bytes

    root = Workspace.open(args.path).root
    if (failure := _require_initialized('model-assumptions', args, 'reviewing model assumptions')) is not None:
        return failure
    try:
        paths = [Path(args.config)] + ([Path(args.previous_config)] if args.previous_config else [])
        # Each file is read once, so its digest describes exactly the bytes that were parsed.
        original = [path.read_bytes() for path in paths]
        configs = [config_from_bytes(raw) for raw in original]
        report = assumption_report(configs[0], configs[1] if len(configs) == 2 else None)
        report['config_sha256'] = hashlib.sha256(original[0]).hexdigest()
        report['previous_config_sha256'] = hashlib.sha256(original[1]).hexdigest() if len(original) == 2 else None
    except (OSError, ValueError, RecursionError, yaml.YAMLError) as exc:
        return _failure('model-assumptions', root, 'invalid_config', str(exc))
    return _success('model-assumptions', root, report)


def command_model_export(args: argparse.Namespace) -> int:
    from pyfpa.config.loader import load_config
    from pyfpa.excel.model_workbook import model_to_excel

    opened = Workspace.open(args.path)
    root = opened.root
    if (failure := _require_initialized("model-export", args, "exporting a model workbook")) is not None:
        return failure
    try:
        cfg = load_config(args.config)
    except Exception as exc:
        return _failure("model-export", root, "invalid_config", str(exc))
    try:
        out_path = _root(args.out)
        if out_path.suffix.lower() != ".xlsx":
            raise ValueError("model export requires an .xlsx output path")
        if out_path.exists() and out_path.samefile(args.config):
            raise ValueError("model export must not overwrite the source configuration")
        # The configuration file's own modification date is when the inputs last changed.
        inputs_updated = date.fromtimestamp(Path(args.config).stat().st_mtime)
        model_to_excel(cfg, out_path, inputs_updated=inputs_updated)
    except Exception as exc:
        return _failure("model-export", root, "export_failed", str(exc))
    return _success(
        "model-export",
        root,
        {
            "workbook_path": str(out_path),
            "sheets": ["Assumptions", "Model", "Checks"],
            "config": str(args.config),
            "inputs_updated": inputs_updated.isoformat(),
            "entity": cfg.name,
        },
    )


def command_mcp_serve(args: argparse.Namespace) -> int:
    """Serve the MCP tools over stdin and stdout until stdin closes."""
    from pyfpa.mcp_server import serve

    root = _root(args.path)
    if not root.is_dir():
        return _failure("mcp-serve", root, "invalid_folder", f"server folder does not exist: {root}")
    # MCP's stdio transport is UTF-8 with bare newlines, whatever the platform's defaults.
    # Undecodable bytes reach serve as surrogates, which it answers as a parse error.
    cast(io.TextIOWrapper, sys.stdin).reconfigure(encoding="utf-8", errors="surrogateescape")
    cast(io.TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8", newline="\n")
    serve(root, sys.stdin, sys.stdout)
    return 0
