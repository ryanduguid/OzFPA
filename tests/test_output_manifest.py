# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""SHA-256 manifest of an output folder. Every file and its content is invented."""

from __future__ import annotations

import hashlib
import json

import pytest

from pyfpa.io.manifest import FORMAT, NAME, main, verify_manifest, write_manifest


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "briefing.md").write_bytes(b"# Briefing\nCash is $10.\n")
    (tmp_path / "cash.csv").write_bytes(b"week,cash\n1,10.00\n")
    (tmp_path / "detail").mkdir()
    (tmp_path / "detail" / "levers.csv").write_bytes(b"debtor,gain\nA,5.00\n")
    (tmp_path / "book.xlsx").write_bytes(b"not reproducible")
    write_manifest(tmp_path, unhashed=["book.xlsx"])
    return tmp_path


def test_the_manifest_lists_every_file_but_itself_and_the_unhashed(folder):
    manifest = json.loads((folder / NAME).read_text(encoding="utf-8"))
    assert manifest["format"] == FORMAT
    assert manifest["unhashed"] == ["book.xlsx"]
    assert list(manifest["files"]) == ["briefing.md", "cash.csv", "detail/levers.csv"]
    assert manifest["files"]["cash.csv"] == hashlib.sha256(b"week,cash\n1,10.00\n").hexdigest()
    assert verify_manifest(folder) == []


def test_a_changed_missing_or_extra_file_fails(folder):
    (folder / "cash.csv").write_bytes(b"week,cash\n1,10.01\n")
    (folder / "detail" / "levers.csv").unlink()
    (folder / "notes.txt").write_bytes(b"added later")
    assert verify_manifest(folder) == ["missing: detail/levers.csv", "changed: cash.csv", "extra: notes.txt"]


def test_line_endings_alone_do_not_fail_but_any_other_byte_does(folder):
    (folder / "briefing.md").write_bytes(b"# Briefing\r\nCash is $10.\r\n")
    assert verify_manifest(folder) == []
    (folder / "briefing.md").write_bytes(b"# Briefing\r\nCash is $10. \r\n")
    assert verify_manifest(folder) == ["changed: briefing.md"]


def test_a_binary_file_is_hashed_as_raw_bytes(tmp_path):
    (tmp_path / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    write_manifest(tmp_path)
    (tmp_path / "chart.png").write_bytes(b"\x89PNG\n\x1a\n")
    assert verify_manifest(tmp_path) == ["changed: chart.png"]


def test_an_unhashed_output_may_be_present_or_absent(folder):
    (folder / "book.xlsx").unlink()
    assert verify_manifest(folder) == []


def test_a_missing_or_malformed_manifest_fails(folder):
    (folder / NAME).write_text("{not json", encoding="utf-8")
    assert verify_manifest(folder) == [f"{NAME}: not a {FORMAT} manifest"]
    (folder / NAME).write_text(json.dumps({"format": "other", "files": {}, "unhashed": []}), encoding="utf-8")
    assert verify_manifest(folder) == [f"{NAME}: not a {FORMAT} manifest"]
    (folder / NAME).write_text(json.dumps({"format": FORMAT, "files": [], "unhashed": []}), encoding="utf-8")
    assert verify_manifest(folder) == [f"{NAME}: not a {FORMAT} manifest"]
    (folder / NAME).unlink()
    assert verify_manifest(folder) == [f"missing: {NAME}"]


def test_a_listed_path_outside_the_folder_is_missing_and_never_read(folder, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "secret.txt"
    outside.write_bytes(b"x")
    manifest = json.loads((folder / NAME).read_text(encoding="utf-8"))
    manifest["files"]["../outside0/secret.txt"] = hashlib.sha256(b"x").hexdigest()
    (folder / NAME).write_text(json.dumps(manifest), encoding="utf-8")
    assert verify_manifest(folder) == ["missing: ../outside0/secret.txt"]


def test_the_command_prints_the_problems_and_exits_1_on_any(folder, capsys):
    assert main([str(folder)]) == 0
    assert json.loads(capsys.readouterr().out)["problems"] == []
    (folder / "cash.csv").write_bytes(b"changed")
    assert main([str(folder)]) == 1
    assert json.loads(capsys.readouterr().out)["problems"] == ["changed: cash.csv"]
