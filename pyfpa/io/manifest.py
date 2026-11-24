# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""A SHA-256 manifest of an output folder, and a check that fails on a changed, missing or extra file.

`write_manifest(folder, unhashed)` hashes every file under the folder except
`manifest.json` itself and the relative paths in `unhashed`, which are outputs
rebuilt locally that are not byte for byte reproducible, such as a workbook.
In text files (.csv, .json, .md, .txt, .yaml, .yml) CRLF is read as LF before
hashing, because Git may check text out with CRLF on Windows; every other file
is hashed as raw bytes, and any other changed byte changes the hash.

`verify_manifest(folder)` lists each listed file that is missing, each whose
hash changed and each file present but not listed. Only files found inside the
folder are read, so a listed path that points outside it is reported missing.

    python -m pyfpa.io.manifest <folder>

prints the problems as JSON and exits 1 if there is one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Sequence
from pathlib import Path

NAME = "manifest.json"
FORMAT = "ozfpa-output-manifest/1"
TEXT_SUFFIXES = (".csv", ".json", ".md", ".txt", ".yaml", ".yml")


def _digest(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha256(data.replace(b"\r\n", b"\n") if path.suffix.lower() in TEXT_SUFFIXES else data).hexdigest()


def _files(folder: Path, unhashed: Iterable[str]) -> list[str]:
    skip = {NAME, *unhashed}
    names = (path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file())
    return sorted(name for name in names if name not in skip)


def write_manifest(folder: str | Path, unhashed: Iterable[str] = ()) -> dict[str, object]:
    """Hash the folder's files into `manifest.json` and return what was written."""
    root = Path(folder)
    skip = sorted(set(unhashed))
    manifest: dict[str, object] = {
        "format": FORMAT,
        "line_endings": f"CRLF is read as LF in {', '.join(TEXT_SUFFIXES)} files; other files are raw bytes",
        "unhashed": skip,
        "files": {name: _digest(root / name) for name in _files(root, skip)},
    }
    (root / NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _read(root: Path) -> tuple[dict[str, object], list[object]] | str:
    """The manifest's files and unhashed paths, or the problem that stops the check."""
    try:
        manifest = json.loads((root / NAME).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return f"missing: {NAME}"
    except json.JSONDecodeError:
        manifest = None
    if isinstance(manifest, dict) and manifest.get("format") == FORMAT:
        files, unhashed = manifest.get("files"), manifest.get("unhashed")
        if isinstance(files, dict) and isinstance(unhashed, list):
            return files, unhashed
    return f"{NAME}: not a {FORMAT} manifest"


def verify_manifest(folder: str | Path) -> list[str]:
    """Each missing, changed or extra file; empty when the folder matches its manifest."""
    root = Path(folder)
    read = _read(root)
    if isinstance(read, str):
        return [read]
    files, unhashed = read
    present = set(_files(root, (str(name) for name in unhashed)))
    problems = [f"missing: {name}" for name in sorted(files) if name not in present]
    problems += [f"changed: {name}" for name in sorted(files) if name in present and _digest(root / name) != files[name]]
    return problems + [f"extra: {name}" for name in sorted(present - set(files))]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check an output folder against its manifest.json")
    parser.add_argument("folder", type=Path)
    args = parser.parse_args(argv)
    problems = verify_manifest(args.folder)
    print(json.dumps({"folder": str(args.folder), "problems": problems}, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
