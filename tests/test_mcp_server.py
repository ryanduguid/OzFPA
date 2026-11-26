import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook

from pyfpa import mcp_server
from pyfpa.cli import main
from pyfpa.mcp_server import PROTOCOL_VERSIONS, confined_path, handle, serve

ROOT = Path(__file__).resolve().parents[1]
CASH13 = ROOT / "examples/ridgeline/cash13.yaml"


def _session(folder, *messages):
    out = io.StringIO()
    lines = [m if isinstance(m, str) else json.dumps(m) for m in messages]
    serve(folder, io.StringIO("\n".join(lines) + "\n"), out)
    return [json.loads(line) for line in out.getvalue().splitlines()]


def _call(folder, name, arguments):
    reply = handle(Path(folder).resolve(), {
        "jsonrpc": "2.0", "id": 7, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert reply is not None
    return reply["result"]


@pytest.fixture
def folder(tmp_path):
    shutil.copy(CASH13, tmp_path / "cash13.yaml")
    return tmp_path


def test_handshake_lists_both_tools_and_ignores_notifications(folder):
    replies = _session(
        folder,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        "",
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "ping"},
    )
    assert [r["id"] for r in replies] == [1, 2, 3]
    init = replies[0]["result"]
    assert init["protocolVersion"] == "2025-06-18"
    assert init["capabilities"] == {"tools": {}}
    assert init["serverInfo"]["name"] == "openfpa"
    assert [t["name"] for t in replies[1]["result"]["tools"]] == ["cash13_workbook", "variance_summary"]
    assert replies[2]["result"] == {}


def test_an_unknown_protocol_version_gets_the_latest(folder):
    reply = handle(folder, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                            "params": {"protocolVersion": "1999-01-01"}})
    assert reply is not None
    assert reply["result"]["protocolVersion"] == PROTOCOL_VERSIONS[0]


def test_server_version_falls_back_outside_an_installed_package(monkeypatch):
    from importlib.metadata import PackageNotFoundError

    def missing(_name):
        raise PackageNotFoundError

    monkeypatch.setattr(mcp_server, "version", missing)
    assert mcp_server._server_version() == "source"


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("{not json", -32700),
        ([{"jsonrpc": "2.0", "id": 1, "method": "ping"}], -32600),
        ({"jsonrpc": "1.0", "id": 1, "method": "ping"}, -32600),
        ({"jsonrpc": "2.0", "id": 1, "method": "resources/list"}, -32601),
        ({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": [1]}, -32602),
        ({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "rm"}}, -32602),
        ({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
          "params": {"name": "variance_summary", "arguments": [1]}}, -32602),
    ],
)
def test_protocol_errors_get_json_rpc_error_codes(folder, message, code):
    (reply,) = _session(folder, message)
    assert reply["error"]["code"] == code


def test_cash13_tool_writes_the_workbook_and_returns_the_runway(folder):
    result = _call(folder, "cash13_workbook", {"config": "cash13.yaml", "out": "out/cash13.xlsx"})
    assert "isError" not in result
    data = result["structuredContent"]
    assert json.loads(result["content"][0]["text"]) == data
    assert data["workbook"] == "out/cash13.xlsx"
    assert data["weeks"] == 13
    assert data["runway"]["min_week"] in range(1, 14)
    ws = load_workbook(folder / "out/cash13.xlsx")["Forecast"]
    assert ws.max_row == 14
    assert ws.cell(row=14, column=1).value == 13


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"config": "../cash13.yaml", "out": "a.xlsx"}, "leaves the server folder"),
        ({"config": str(CASH13), "out": "a.xlsx"}, "must be relative"),
        ({"config": "/etc/passwd", "out": "a.xlsx"}, "must be relative"),
        ({"config": "", "out": "a.xlsx"}, "non-empty path"),
        ({"out": "a.xlsx"}, "non-empty path"),
        ({"config": "cash13.yaml", "out": "sub/../../a.xlsx"}, "leaves the server folder"),
        ({"config": "cash13.yaml", "out": "a.csv"}, ".xlsx"),
        ({"config": "missing.yaml", "out": "a.xlsx"}, "missing.yaml"),
    ],
)
def test_cash13_tool_refuses_paths_outside_the_folder_and_bad_files(folder, arguments, message):
    result = _call(folder, "cash13_workbook", arguments)
    assert result["isError"] is True
    assert message in result["content"][0]["text"]
    assert not list(folder.glob("*.xlsx"))


def test_cash13_tool_refuses_to_overwrite_its_config(folder):
    (folder / "c.xlsx").write_bytes((folder / "cash13.yaml").read_bytes())
    result = _call(folder, "cash13_workbook", {"config": "c.xlsx", "out": "c.xlsx"})
    assert result["isError"] is True
    assert "overwrite" in result["content"][0]["text"]


def test_a_symlink_out_of_the_folder_is_refused(tmp_path):
    inside, outside = tmp_path / "inside", tmp_path / "outside"
    inside.mkdir()
    outside.mkdir()
    shutil.copy(CASH13, outside / "cash13.yaml")
    try:
        os.symlink(outside, inside / "link", target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links need privileges on this platform")
    result = _call(inside, "cash13_workbook", {"config": "link/cash13.yaml", "out": "a.xlsx"})
    assert result["isError"] is True
    assert "leaves the server folder" in result["content"][0]["text"]


def test_confined_path_accepts_a_nested_path(tmp_path):
    root = tmp_path.resolve()
    assert confined_path(root, "a/b/../c.yaml", label="x") == root / "a" / "c.yaml"


def test_cash13_tool_reports_an_invalid_config(folder):
    (folder / "bad.yaml").write_text("opening_cash: [\n", encoding="utf-8")
    (folder / "wrong.yaml").write_text("opening_cash: 1\nweekz: 13\n", encoding="utf-8")
    for name in ("bad.yaml", "wrong.yaml"):
        result = _call(folder, "cash13_workbook", {"config": name, "out": "a.xlsx"})
        assert result["isError"] is True


def test_variance_summary_ranks_and_flags_lines(folder):
    result = _call(folder, "variance_summary", {
        "model": {"revenue": 110.0, "opex": 50, "other": 5},
        "actual": {"revenue": 100.0, "opex": 50.2, "other": 0},
        "tolerance": 0.05,
    })
    data = result["structuredContent"]
    by_line = {line["line"]: line for line in data["lines"]}
    assert by_line["revenue"]["variance"] == pytest.approx(10.0)
    assert by_line["revenue"]["variance_pct"] == pytest.approx(0.1)
    assert by_line["revenue"]["within_tolerance"] is False
    assert by_line["opex"]["within_tolerance"] is True
    assert by_line["other"]["variance_pct"] is None
    assert data["outside_tolerance"] == ["revenue", "other"]
    assert data["largest_variance_line"] == "revenue"
    assert data["net_variance"] == pytest.approx(14.8)
    assert data["tolerance"] == 0.05


def test_variance_summary_of_no_lines_is_empty(folder):
    data = _call(folder, "variance_summary", {"model": {}, "actual": {}})["structuredContent"]
    assert data == {"tolerance": 0.01, "lines": [], "outside_tolerance": [],
                    "largest_variance_line": None, "net_variance": 0}


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"model": {"a": 1}}, "actual must be an object"),
        ({"model": {"a": "1"}, "actual": {"a": 1}}, "must be a number"),
        ({"model": {"a": True}, "actual": {"a": 1}}, "must be a number"),
        ({"model": {"a": 1}, "actual": {"b": 1}}, "line sets differ"),
        ({"model": {"a": 1}, "actual": {"a": 1}, "tolerance": -1}, "tolerance"),
        ({"model": {"a": 1}, "actual": {"a": 1}, "tolerance": True}, "tolerance"),
        ({"model": {"a": 1e308}, "actual": {"a": -1e308}}, "finite"),
    ],
)
def test_variance_summary_refuses_bad_arguments(folder, arguments, message):
    result = _call(folder, "variance_summary", arguments)
    assert result["isError"] is True
    assert message in result["content"][0]["text"]


def test_malformed_calls_leave_the_session_running(folder):
    huge = "1" + "0" * 400  # a JSON integer too large for a float
    replies = _session(
        folder,
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": ["variance_summary"]}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": {"a": 1}}},
        '{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "variance_summary",'
        f' "arguments": {{"model": {{"a": {huge}}}, "actual": {{"a": 1}}}}}}}}',
        '{"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "variance_summary",'
        f' "arguments": {{"model": {{"a": 1}}, "actual": {{"a": 1}}, "tolerance": {huge}}}}}}}',
        {"jsonrpc": "2.0", "id": 5, "method": "ping"},
    )
    assert [r["id"] for r in replies] == [1, 2, 3, 4, 5]
    assert [r["error"]["code"] for r in replies[:2]] == [-32602, -32602]
    assert [r["result"]["isError"] for r in replies[2:4]] == [True, True]
    assert replies[4]["result"] == {}


def test_numbers_json_cannot_echo_leave_the_session_running(folder):
    replies = _session(
        folder,
        '{"jsonrpc": "2.0", "id": 1e400, "method": "ping"}',
        '{"jsonrpc": "2.0", "id": NaN, "method": "ping"}',
        '{"jsonrpc": "2.0", "id": ' + "1" * 5000 + ', "method": "ping"}',
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
            "name": "variance_summary",
            "arguments": {"model": {"a": 1e308, "b": 1e308}, "actual": {"a": 0, "b": 0}}}},
        {"jsonrpc": "2.0", "id": 5, "method": "ping"},
    )
    assert [r["id"] for r in replies] == [None, None, None, 4, 5]
    assert [r["error"]["code"] for r in replies[:3]] == [-32700] * 3
    assert replies[3]["result"]["isError"] is True
    assert replies[4]["result"] == {}


def test_nesting_and_odd_ids_leave_the_session_running(folder, monkeypatch):
    deep = "[" * 100_000 + "]" * 100_000
    nested_id = '{"jsonrpc": "2.0", "id": ' + "[" * 900 + "]" * 900 + ', "method": "ping"}'
    replies = _session(
        folder,
        deep,
        nested_id,
        {"jsonrpc": "2.0", "id": True, "method": "ping"},
        {"jsonrpc": "2.0", "id": 1.5, "method": "ping"},
        {"jsonrpc": "2.0", "id": {"a": 1}, "method": 3},
        {"jsonrpc": "2.0", "id": "s", "method": "ping"},
    )
    codes = [r.get("error", {}).get("code") for r in replies]
    # Whether 100,000 levels exceed the parser's stack depends on the platform's
    # stack size: a parse error where they do, an invalid request where they do not.
    assert codes[0] in (-32700, -32600)
    assert codes[1:] == [-32600, -32600, -32600, -32600, None]
    assert [r["id"] for r in replies] == [None, None, None, None, None, "s"]

    def too_deep(*args, **kwargs):
        raise RecursionError("maximum recursion depth exceeded")

    with monkeypatch.context() as patch:
        patch.setattr(json, "loads", too_deep)
        out = io.StringIO()
        serve(folder, io.StringIO('{"jsonrpc": "2.0", "id": 8, "method": "ping"}\n'), out)
    assert json.loads(out.getvalue())["error"]["code"] == -32700

    def broken(root, message):
        raise RuntimeError("boom")

    monkeypatch.setattr(mcp_server, "handle", broken)
    (crash, again) = _session(folder, {"jsonrpc": "2.0", "id": 9, "method": "ping"},
                              {"jsonrpc": "2.0", "id": 10, "method": "ping"})
    assert crash == {"jsonrpc": "2.0", "id": 9,
                     "error": {"code": -32603, "message": "internal error: boom"}}
    assert again["id"] == 10


def test_serve_refuses_a_missing_folder(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        serve(tmp_path / "nope", io.StringIO(""), io.StringIO())


def test_cli_refuses_a_missing_folder(tmp_path, run_cli):
    result = run_cli("mcp-serve", str(tmp_path / "nope"))
    assert result.returncode != 0
    assert json.loads(result.stdout)["error"]["type"] == "invalid_folder"


def test_cli_serves_utf8_lines_in_process(folder, monkeypatch):
    request = {"jsonrpc": "2.0", "id": "é", "method": "ping"}
    stdin = io.TextIOWrapper(io.BytesIO((json.dumps(request, ensure_ascii=False) + "\n").encode()))
    stdout_bytes = io.BytesIO()
    stdout = io.TextIOWrapper(stdout_bytes)
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    assert main(["mcp-serve", str(folder)]) == 0
    stdout.flush()
    raw = stdout_bytes.getvalue()
    assert raw.endswith(b"}\n") and b"\r" not in raw
    assert json.loads(raw.decode("utf-8"))["id"] == "é"


def test_stdio_session_in_a_real_process(folder):
    """The console contract: a separate process speaking MCP over its pipes."""
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "cash13_workbook",
                    "arguments": {"config": "cash13.yaml", "out": "cash13.xlsx"}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "variance_summary",
                    "arguments": {"model": {"cash": 2.0}, "actual": {"cash": 1.0}}}},
    ]
    done = subprocess.run(  # nosec B603: fixed argv, this interpreter, no shell
        [sys.executable, "-m", "pyfpa.cli", "mcp-serve", str(folder)],
        input="".join(json.dumps(m) + "\n" for m in messages).encode(),
        capture_output=True, timeout=120, cwd=ROOT, check=True,
    )
    replies = [json.loads(line) for line in done.stdout.decode("utf-8").splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3]
    assert replies[0]["result"]["protocolVersion"] == "2025-11-25"
    assert replies[1]["result"]["structuredContent"]["workbook"] == "cash13.xlsx"
    assert replies[2]["result"]["structuredContent"]["outside_tolerance"] == ["cash"]
    assert (folder / "cash13.xlsx").exists()
