"""Two-layer no-transmission guard for the diagnostic-report feature
(spec section 8.1; section 12 acceptance criteria).

Layer 1 (static): AST-scan every module under
`flextoolsmcp/server/diagnostic/` PLUS the `flextools_prepare_report`
handler module (`flextoolsmcp/server/handlers/diagnostic_report.py`) for
any import or call that reaches a transmission-capable surface:
`subprocess`, `os.system`/`os.popen`, `smtplib`, `webbrowser.open`,
network-capable `urllib`/`requests`/`http.client`, or a raw `socket`.
Building a STRING that merely contains "gh" or "mailto:" is fine -- the
guard forbids INVOKING transports, not describing them.

Layer 2 (dynamic): monkeypatch those same surfaces to raise on invocation,
then drive the real pipeline (`prepare_report_bundle` / the
`flextools_prepare_report` tool handler) through the gh-present, gh-absent,
and mailto branches. Assert zero invocations of any banned surface and
exactly ONE local file write per prepared report.
"""

import ast
import asyncio
import json
import os
import smtplib
import subprocess
import webbrowser
from pathlib import Path

import pytest

from flextoolsmcp.server import diagnostic as diagnostic_pkg
from flextoolsmcp.server.diagnostic import transports as transports_mod
from flextoolsmcp.server.handlers import diagnostic_report


# ---------------------------------------------------------------------------
# Layer 1: static AST scan.
# ---------------------------------------------------------------------------

_DIAGNOSTIC_DIR = Path(diagnostic_pkg.__file__).resolve().parent
_HANDLER_FILE = Path(diagnostic_report.__file__).resolve()

# Root modules that are transmission-capable and have NO legitimate use in
# this tree (string-building / local file I/O only).
_BANNED_ROOT_MODULES = frozenset({
    "subprocess", "smtplib", "webbrowser", "socket", "requests", "http",
})
# Submodules banned even though their PARENT package has a legitimate,
# non-networking sibling (e.g. `urllib.parse` is pure string encoding and
# is used by transports.py; `urllib.request`/`urllib.error` are the
# network-capable submodules and are banned).
_BANNED_SUBMODULES = frozenset({"urllib.request", "urllib.error", "http.client"})


def _target_files():
    files = sorted(_DIAGNOSTIC_DIR.glob("*.py"))
    files.append(_HANDLER_FILE)
    return files


def _root_module(dotted_name: str) -> str:
    return dotted_name.split(".")[0]


class _BannedSurfaceVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if _root_module(alias.name) in _BANNED_ROOT_MODULES:
                self.violations.append(f"import {alias.name}")
            if alias.name in _BANNED_SUBMODULES:
                self.violations.append(f"import {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            if _root_module(node.module) in _BANNED_ROOT_MODULES:
                self.violations.append(f"from {node.module} import ...")
            if node.module in _BANNED_SUBMODULES:
                self.violations.append(f"from {node.module} import ...")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id == "os" and func.attr in ("system", "popen"):
                self.violations.append(f"os.{func.attr}(...)")
            if func.value.id == "webbrowser" and func.attr == "open":
                self.violations.append("webbrowser.open(...)")
        self.generic_visit(node)


@pytest.mark.parametrize("path", _target_files(), ids=lambda p: p.name)
def test_static_ast_scan_finds_no_transmission_surface(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    visitor = _BannedSurfaceVisitor()
    visitor.visit(tree)
    assert visitor.violations == [], (
        f"{path}: banned transmission surface(s) found: {visitor.violations}"
    )


def test_static_scan_covers_the_whole_diagnostic_tree_and_the_handler():
    """Sanity check that the parametrization above isn't accidentally empty
    (e.g. glob pattern typo silently scanning zero files)."""
    files = _target_files()
    names = {p.name for p in files}
    assert "transports.py" in names
    assert "sensitivity.py" in names
    assert "reconstruct.py" in names
    assert "render.py" in names
    assert "normalize.py" in names
    assert "triggers.py" in names
    assert "signature.py" in names
    assert "offered_store.py" in names
    assert "diagnostic_report.py" in names
    assert len(files) >= 9


def test_transport_strings_may_legitimately_contain_the_words_gh_and_mailto():
    """Guard against an overzealous fix: the STRINGS transports.py builds
    are supposed to contain "gh"/"mailto:" -- only INVOKING is forbidden."""
    bundle = transports_mod.build_transports(
        title="[auto-report] test",
        summary="summary text",
        report_path=Path("C:/fake/report_1.md"),
        gh_available_fn=lambda: True,
    )
    assert bundle["gh"]["argv"][0] == "gh"
    assert bundle["mailto"]["uri"].startswith("mailto:")


# ---------------------------------------------------------------------------
# Fixture helpers (mirrors tests/test_diagnostic_report_reconstruction.py).
# ---------------------------------------------------------------------------

def _fmt(level: str, msg: str, ts: str = "2026-07-13 10:00:00") -> str:
    return f"{ts} | {level:<7} | {msg}"


def _op_block_lines(op_id, seq, *, user_intent="fix the gloss",
                     user_request="please fix the gloss", code="print('hello')",
                     close="ok") -> list:
    lines = [
        _fmt("INFO", f"=== Operation #{seq} Start ({op_id}) ==="),
        _fmt("INFO", "Project:         TestProject"),
        _fmt("INFO", "Write enabled:   False"),
        _fmt("INFO", "Source kind:     bare_snippet"),
        _fmt("INFO", f"User intent:     {user_intent}"),
        _fmt("INFO", f"User request:    {user_request}"),
        _fmt("INFO", "Code fingerprint: sha256=abc123 bytes=20 lines=1"),
        _fmt("DEBUG", "Code:"),
    ]
    for code_line in code.split("\n"):
        lines.append(_fmt("DEBUG", code_line))
    if close == "ok":
        lines.append(_fmt("INFO", "[OK] Operation completed successfully"))
        lines.append(_fmt("INFO", "Messages:        0 info, 0 warnings, 0 errors"))
        lines.append(_fmt("INFO", "Duration:        0.100s"))
    else:
        lines.append(_fmt("ERROR", "[FAIL] Operation failed"))
        lines.append(_fmt("ERROR", "Error type:      PolymorphicAttributeError"))
        lines.append(_fmt("ERROR", "  report.Error: 'ICmObject' object has no attribute 'HeadWord'"))
        lines.append(_fmt("INFO", "Messages:        0 info, 0 warnings, 1 errors"))
        lines.append(_fmt("INFO", "Duration:        0.100s"))
    lines.append(_fmt("INFO", f"=== Operation #{seq} End ({op_id}) ==="))
    return lines


def _jsonl_record(op_id, seq, outcome="ok", error_code="", user_intent="fix the gloss",
                   user_request="please fix the gloss", **extra):
    rec = {
        "ts": "2026-07-13T10:00:00Z", "op_id": op_id, "seq": seq,
        "project": "TestProject", "write_enabled": False, "source_kind": "bare_snippet",
        "user_intent": user_intent, "user_request": user_request,
        "code_sha256": "a" * 64, "code_bytes": 20, "code_lines": 1,
        "outcome": outcome, "error_code": error_code, "preflight_gate": "",
        "casting_signature": "", "duration_s": 0.1,
        "info_count": 0, "warning_count": 0, "error_count": 0,
    }
    rec.update(extra)
    return rec


def _make_turn(tmp_path):
    """A same-turn [runtime_fail, ok] pair -- the workaround-taken signal
    (spec section 6.2) that triggers a diagnostic-report offer."""
    session_log = tmp_path / "session_test.log"
    lines = []
    lines += _op_block_lines(
        "op-1", 1, code="bad = sense.Owner.HeadWord", close="fail",
    )
    lines += _op_block_lines(
        "op-2", 2, code="good = safe_get_property(sense.Owner, 'HeadWord')", close="ok",
    )
    session_log.write_text("\n".join(lines), encoding="utf-8")

    records = [
        _jsonl_record("op-1", 1, outcome="runtime_fail", error_code="PolymorphicAttributeError"),
        _jsonl_record("op-2", 2, outcome="ok"),
    ]
    return records, session_log


# ---------------------------------------------------------------------------
# Layer 2: dynamic monkeypatch-and-drive.
# ---------------------------------------------------------------------------

def _boom(name):
    def _raise(*args, **kwargs):
        raise AssertionError(f"Transmission surface invoked: {name}")
    return _raise


def _patch_all_transmission_surfaces(monkeypatch):
    """Patch every transmission-capable surface to raise on invocation.

    `socket.socket` is deliberately NOT globally replaced -- on Windows,
    asyncio's own event-loop bring-up (`asyncio.run()`, used to drive the
    async tool handler in these tests) creates an internal loopback
    socketpair for its self-pipe, so patching the constructor unconditionally
    would break the TEST HARNESS itself, not just catch a genuine violation.
    Instead we assert (elsewhere) that no code under test imports/uses
    `socket` at all -- the static AST scan already enforces that -- and here
    we patch the higher-level, unambiguously network-only entry points that
    diagnostic-report code has no reason to ever call directly.
    """
    monkeypatch.setattr(subprocess, "run", _boom("subprocess.run"))
    monkeypatch.setattr(subprocess, "Popen", _boom("subprocess.Popen"))
    monkeypatch.setattr(subprocess, "call", _boom("subprocess.call"))
    monkeypatch.setattr(subprocess, "check_call", _boom("subprocess.check_call"))
    monkeypatch.setattr(subprocess, "check_output", _boom("subprocess.check_output"))
    monkeypatch.setattr(os, "system", _boom("os.system"))
    monkeypatch.setattr(os, "popen", _boom("os.popen"))
    monkeypatch.setattr(smtplib, "SMTP", _boom("smtplib.SMTP"))
    monkeypatch.setattr(smtplib, "SMTP_SSL", _boom("smtplib.SMTP_SSL"))
    monkeypatch.setattr(webbrowser, "open", _boom("webbrowser.open"))
    try:
        import urllib.request as _urlreq
        monkeypatch.setattr(_urlreq, "urlopen", _boom("urllib.request.urlopen"))
    except ImportError:
        pass


def _count_writes(monkeypatch):
    counter = {"n": 0}
    orig_write_text = Path.write_text

    def counting_write_text(self, *args, **kwargs):
        counter["n"] += 1
        return orig_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", counting_write_text)
    return counter


@pytest.mark.parametrize("gh_present", [True, False])
def test_dynamic_prepare_report_bundle_no_invocation_and_one_write(
    tmp_path, monkeypatch, gh_present,
):
    """gh-present and gh-absent branches (spec section 12, decision E6)."""
    # Build fixtures (writes the session-log fixture file) BEFORE starting
    # the write counter -- we only want to count writes made by the
    # pipeline under test, not test setup.
    records, session_log = _make_turn(tmp_path)
    reports_dir = tmp_path / "reports"

    _patch_all_transmission_surfaces(monkeypatch)
    write_counter = _count_writes(monkeypatch)

    bundle = diagnostic_report.prepare_report_bundle(
        records, session_log,
        anchor_op_id="op-2",
        gh_available_fn=lambda: gh_present,
        reports_dir_fn=lambda: reports_dir,
    )

    assert bundle is not None
    assert bundle["transports"]["gh_available"] is gh_present
    # gh argv/display always built regardless of availability -- callers
    # decide whether to PRESENT it.
    assert bundle["transports"]["gh"]["argv"][0] == "gh"
    assert bundle["transports"]["github_url"]["url"].startswith("https://github.com/")
    assert bundle["transports"]["mailto"]["uri"].startswith("mailto:")

    assert write_counter["n"] == 1
    assert Path(bundle["report_path"]).exists()


def test_dynamic_mailto_branch_no_invocation(tmp_path, monkeypatch):
    """Email/mailto branch explicitly (neither gh nor a browser is invoked
    to build or "send" the mailto: URI -- it is pure string construction)."""
    records, session_log = _make_turn(tmp_path)
    reports_dir = tmp_path / "reports"

    _patch_all_transmission_surfaces(monkeypatch)
    write_counter = _count_writes(monkeypatch)

    bundle = diagnostic_report.prepare_report_bundle(
        records, session_log,
        anchor_op_id="op-2",
        gh_available_fn=lambda: False,
        reports_dir_fn=lambda: reports_dir,
    )
    assert bundle is not None
    mailto = bundle["transports"]["mailto"]
    assert mailto["uri"].startswith("mailto:matthew_lee@sil.org")
    assert write_counter["n"] == 1


def test_dynamic_flextools_prepare_report_tool_end_to_end(tmp_path, monkeypatch):
    """Drive the actual `flextools_prepare_report` tool handler end-to-end
    (not just the shared bundle helper) with the session-log resolution
    points monkeypatched to tmp_path -- this is the real MCP tool entry
    point, so covering it here is the strongest form of the dynamic guard."""
    records, session_log = _make_turn(tmp_path)
    jsonl_dir = tmp_path / "jsonl_dir"
    jsonl_dir.mkdir()
    jsonl_path = jsonl_dir / "operations.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")

    reports_dir = tmp_path / "reports"
    monkeypatch.setattr(diagnostic_report, "get_log_dir", lambda: jsonl_dir)
    monkeypatch.setattr(diagnostic_report, "get_current_session_log_path", lambda: session_log)
    monkeypatch.setattr(diagnostic_report, "_default_reports_dir", lambda: reports_dir)

    _patch_all_transmission_surfaces(monkeypatch)
    write_counter = _count_writes(monkeypatch)

    result = asyncio.run(diagnostic_report.handle_prepare_report({"op_id": "op-2"}))
    payload = json.loads(result[0].text)

    assert payload["status"] == "ok"
    assert "transports" in payload
    assert payload["transports"]["gh"]["argv"][0] == "gh"
    assert payload["transports"]["github_url"]["url_bytes"] <= 8192
    assert payload["transports"]["mailto"]["uri"].startswith("mailto:")
    assert "likely_contains_lexical_data" in payload
    assert write_counter["n"] == 1
