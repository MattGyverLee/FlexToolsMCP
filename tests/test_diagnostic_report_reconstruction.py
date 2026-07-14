"""CP2 tests for the diagnostic-report feature: reconstruction, rotation
stitching, MAX_REPORT_OPS summarize-not-drop, path-scoped normalization
(E2), seven-section rendering, and the CP2 casting-recurrence precision fix.

Spec: specs/diagnostic-report/SPEC.md sections 3, 5, 7, 8.3; section 12
acceptance criteria under "Reconstruction" and "Privacy / normalization".
"""

import asyncio
import json
from pathlib import Path

import pytest

from flextoolsmcp.server.diagnostic import reconstruct, normalize, render, triggers
from flextoolsmcp.server.handlers import op_telemetry as tel
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server import kernel, project_discovery


# ---------------------------------------------------------------------------
# Fixture helpers: synthesize realistic session-log text matching the
# formatter in server/kernel.py (`_make_file_handler`):
#   '%(asctime)s | %(levelname)-7s | %(message)s'
# ---------------------------------------------------------------------------

def _fmt(level: str, msg: str, ts: str = "2026-07-13 10:00:00") -> str:
    # Mirrors server/kernel.py's formatter:
    # '%(asctime)s | %(levelname)-7s | %(message)s' -- note the literal
    # " | " is a separate token from the width-7 levelname field, so it
    # must always be emitted even when levelname is exactly 7 chars wide
    # (e.g. "WARNING"), not just relied upon as padding.
    return f"{ts} | {level:<7} | {msg}"


def _op_block_lines(
    op_id: str,
    seq: int,
    *,
    project: str = "TestProject",
    write_enabled: bool = False,
    source_kind: str = "bare_snippet",
    user_intent: str = "fix the gloss",
    user_request: str = "please fix the gloss",
    code: str = "print('hello')",
    casting_line: str = None,
    close: str = "ok",
    report_error_line: str = None,
) -> list:
    """Build the raw log lines for one operation Start..End block, matching
    the shape emitted by execution.py's _log_operation_start /
    _log_operation_end_success / _log_preflight_reject / _log_operation_failure.
    """
    lines = [
        _fmt("INFO", f"=== Operation #{seq} Start ({op_id}) ==="),
        _fmt("INFO", f"Project:         {project}"),
        _fmt("INFO", f"Write enabled:   {write_enabled}"),
        _fmt("INFO", f"Source kind:     {source_kind}"),
        _fmt("INFO", f"User intent:     {user_intent}"),
        _fmt("INFO", f"User request:    {user_request}"),
        _fmt("INFO", "Code fingerprint: sha256=abc123def456 bytes=20 lines=1"),
    ]
    if casting_line:
        lines.append(_fmt("INFO", casting_line))
    lines.append(_fmt("DEBUG", "Code:"))
    for code_line in code.split("\n"):
        lines.append(_fmt("DEBUG", code_line))
    if report_error_line:
        lines.append(_fmt("DEBUG", "Report messages:"))
        lines.append(_fmt("ERROR", f"  report.Error: {report_error_line}"))
    if close == "ok":
        lines.append(_fmt("INFO", "[OK] Operation completed successfully"))
        lines.append(_fmt("INFO", "Messages:        0 info, 0 warnings, 0 errors"))
        lines.append(_fmt("INFO", "Duration:        0.100s"))
    elif close == "fail":
        lines.append(_fmt("ERROR", "[FAIL] Operation failed"))
        lines.append(_fmt("ERROR", "Error type:      PolymorphicAttributeError"))
        lines.append(_fmt("INFO", "Messages:        0 info, 0 warnings, 1 errors"))
        lines.append(_fmt("INFO", "Duration:        0.100s"))
    elif close == "reject":
        lines.append(_fmt("WARNING", "[REJECT] Pre-flight validation blocked execution"))
        lines.append(_fmt("WARNING", "Reason code:     casting_issues_detected"))
        lines.append(_fmt("INFO", "Duration:        0.050s"))
    lines.append(_fmt("INFO", f"=== Operation #{seq} End ({op_id}) ==="))
    return lines


def _tool_call_lines(tool: str, args: str = "{}") -> list:
    return [
        _fmt("INFO", f"[TOOL CALL] {tool}"),
        _fmt("INFO", f"[TOOL ARGS] {tool}: {args}"),
    ]


def _session_header_lines(session_id: str = "20260713-100000") -> list:
    return [
        _fmt("INFO", "=== Session Environment ==="),
        _fmt("INFO", f"Session ID:      {session_id}"),
        _fmt("INFO", "FlexToolsMCP:    1.2.3"),
        _fmt("INFO", "Flexicon:    4.1.0"),
        _fmt("INFO", "LibLCM:          8.3.0"),
        _fmt("INFO", "Python:          CPython 3.11.5"),
        _fmt("INFO", "OS:              Windows 11 (AMD64)"),
        _fmt("INFO", "=== End Session Environment ==="),
    ]


def _jsonl_record(op_id, seq, outcome="ok", error_code="", preflight_gate="",
                   user_intent="fix the gloss", user_request="please fix the gloss",
                   casting_signature="", **extra):
    rec = {
        "ts": "2026-07-13T10:00:00Z",
        "op_id": op_id,
        "seq": seq,
        "project": "TestProject",
        "write_enabled": False,
        "source_kind": "bare_snippet",
        "user_intent": user_intent,
        "user_request": user_request,
        "code_sha256": "a" * 64,
        "code_bytes": 20,
        "code_lines": 1,
        "outcome": outcome,
        "error_code": error_code,
        "preflight_gate": preflight_gate,
        "casting_signature": casting_signature,
        "duration_s": 0.1,
        "info_count": 0,
        "warning_count": 0,
        "error_count": 0,
    }
    rec.update(extra)
    return rec


# ---------------------------------------------------------------------------
# 1. JSONL <-> log join by op_id/seq (basic reconstruction).
# ---------------------------------------------------------------------------

def test_reconstruct_joins_jsonl_to_log_blocks_by_op_id(tmp_path):
    session_log = tmp_path / "session_20260713-100000.log"
    text_lines = []
    text_lines += _tool_call_lines("flextools_start", '{"user_request": "please fix the gloss"}')
    text_lines += _op_block_lines("op-1", 1, code="x = 1", close="ok")
    session_log.write_text("\n".join(text_lines), encoding="utf-8")

    records = [_jsonl_record("op-1", 1, outcome="ok")]

    slice_obj = reconstruct.reconstruct_slice(records, session_log)

    assert len(slice_obj.ops) == 1
    op = slice_obj.ops[0]
    assert op.op_id == "op-1"
    assert op.found_in_log is True
    assert op.jsonl["outcome"] == "ok"
    assert any("x = 1" in l for l in op.log_lines)
    # The flextools_start tool call preceding the op's Start block is
    # captured as a discovery call.
    tools_seen = [c["tool"] for c in op.discovery_calls]
    assert "flextools_start" in tools_seen


def test_reconstruct_defaults_to_whole_turn_via_user_intent_grouping(tmp_path):
    session_log = tmp_path / "session_x.log"
    text_lines = []
    text_lines += _op_block_lines("op-1", 1, user_intent="fix gloss", close="fail")
    text_lines += _op_block_lines("op-2", 2, user_intent="fix gloss", close="ok")
    text_lines += _op_block_lines("op-3", 3, user_intent="unrelated task", close="ok")
    session_log.write_text("\n".join(text_lines), encoding="utf-8")

    records = [
        _jsonl_record("op-1", 1, outcome="runtime_fail", error_code="PolymorphicAttributeError",
                       user_intent="fix gloss"),
        _jsonl_record("op-2", 2, outcome="ok", user_intent="fix gloss"),
        _jsonl_record("op-3", 3, outcome="ok", user_intent="unrelated task"),
    ]

    # Default boundary anchored on op-1 (the failing op) -> whole turn is
    # [op-1, op-2], NOT op-3 (different user_intent).
    slice_obj = reconstruct.reconstruct_slice(records, session_log, anchor_op_id="op-1")
    assert [op.op_id for op in slice_obj.ops] == ["op-1", "op-2"]
    assert slice_obj.boundary == "turn"


def test_reconstruct_steps_back_and_explicit_op_ids(tmp_path):
    session_log = tmp_path / "session_y.log"
    text_lines = []
    for i in range(1, 5):
        text_lines += _op_block_lines(f"op-{i}", i, user_intent="one turn", close="ok")
    session_log.write_text("\n".join(text_lines), encoding="utf-8")

    records = [_jsonl_record(f"op-{i}", i, user_intent="one turn") for i in range(1, 5)]

    # steps_back=1 anchored on op-4 -> [op-3, op-4]
    sliced = reconstruct.reconstruct_slice(records, session_log, anchor_op_id="op-4", steps_back=1)
    assert [op.op_id for op in sliced.ops] == ["op-3", "op-4"]
    assert sliced.boundary == "explicit"

    # explicit op_ids bypasses turn logic entirely
    sliced2 = reconstruct.reconstruct_slice(records, session_log, op_ids=["op-1", "op-4"])
    assert [op.op_id for op in sliced2.ops] == ["op-1", "op-4"]
    assert sliced2.boundary == "explicit"


# ---------------------------------------------------------------------------
# 2. Rotation stitching across .log / .log.1 / .log.2, incl. recycled-op
#    truncation marker (resolved Q3, "no silent caps").
# ---------------------------------------------------------------------------

def test_rotation_stitch_across_log_and_backups(tmp_path):
    session_log = tmp_path / "session_z.log"
    log1 = tmp_path / "session_z.log.1"
    log2 = tmp_path / "session_z.log.2"

    # Oldest rotation (.log.2): op-1 fully contained (will be "recycled"
    # once we simulate .log.2 no longer existing in a later test).
    log2.write_text("\n".join(_op_block_lines("op-1", 1, close="ok")), encoding="utf-8")

    # .log.1: op-2's Start marker only -- its End lands in the CURRENT file,
    # simulating rotation firing mid-operation.
    op2_lines = _op_block_lines("op-2", 2, code="y = 2", close="ok")
    split_point = 4  # arbitrary mid-block split
    log1.write_text("\n".join(op2_lines[:split_point]), encoding="utf-8")

    # current file: the rest of op-2's block, plus op-3 entirely.
    current_lines = op2_lines[split_point:] + _op_block_lines("op-3", 3, close="ok")
    session_log.write_text("\n".join(current_lines), encoding="utf-8")

    records = [
        _jsonl_record("op-1", 1),
        _jsonl_record("op-2", 2),
        _jsonl_record("op-3", 3),
    ]

    slice_obj = reconstruct.reconstruct_slice(records, session_log, op_ids=["op-1", "op-2", "op-3"])

    by_id = {op.op_id: op for op in slice_obj.ops}
    assert by_id["op-1"].found_in_log is True
    # op-2's block was split across .log.1 / session_z.log -- stitching must
    # recover the FULL block (both the Start half and the "y = 2" / End half).
    assert by_id["op-2"].found_in_log is True
    joined = "\n".join(by_id["op-2"].log_lines)
    assert "Operation #2 Start" in joined
    assert "y = 2" in joined
    assert "Operation #2 End" in joined
    assert by_id["op-3"].found_in_log is True
    assert slice_obj.rotation_truncated == []


def test_rotation_recycled_op_is_flagged_not_silently_omitted(tmp_path):
    session_log = tmp_path / "session_w.log"
    # Only op-2 remains available; op-1's rotation file has already been
    # recycled past backupCount (no .log.1/.log.2/.log.3 file contains it).
    session_log.write_text("\n".join(_op_block_lines("op-2", 2, close="ok")), encoding="utf-8")

    records = [
        _jsonl_record("op-1", 1, outcome="runtime_fail", error_code="PolymorphicAttributeError"),
        _jsonl_record("op-2", 2, outcome="ok"),
    ]

    slice_obj = reconstruct.reconstruct_slice(records, session_log, op_ids=["op-1", "op-2"])

    assert slice_obj.rotation_truncated == ["op-1"]
    op1 = next(op for op in slice_obj.ops if op.op_id == "op-1")
    assert op1.found_in_log is False
    assert op1.log_lines == []

    # And the renderer must surface this explicitly, not drop it silently.
    rendered = render.render_report(slice_obj)
    assert "History truncated by rotation" in rendered
    assert "op-1" in rendered


# ---------------------------------------------------------------------------
# 3. MAX_REPORT_OPS summarize-not-drop.
# ---------------------------------------------------------------------------

def test_apply_max_report_ops_summarizes_excess_not_drops():
    records = [
        _jsonl_record(f"op-{i}", i, outcome="ok" if i < 20 else "runtime_fail",
                       error_code="" if i < 20 else "PolymorphicAttributeError")
        for i in range(1, 21)  # 20 records, cap default 12
    ]
    kept, summary = reconstruct.apply_max_report_ops(records, cap=12)

    assert len(kept) == 12
    assert len(summary) == 8
    # Nothing is silently dropped: every excess op_id appears in the summary.
    summarized_ids = {s["op_id"] for s in summary}
    assert summarized_ids == {f"op-{i}" for i in range(1, 9)}
    # Kept records are the most recent (closest to the failure/resolution).
    assert [r["op_id"] for r in kept] == [f"op-{i}" for i in range(9, 21)]
    for s in summary:
        assert s["one_line"]  # non-empty one-line description
        assert "outcome" in s and "error_code" in s


def test_max_report_ops_under_cap_returns_unchanged():
    records = [_jsonl_record(f"op-{i}", i) for i in range(1, 4)]
    kept, summary = reconstruct.apply_max_report_ops(records, cap=12)
    assert kept == records
    assert summary == []


def test_max_report_ops_is_a_module_constant():
    assert reconstruct.MAX_REPORT_OPS == 12


def test_render_surfaces_truncation_summary_not_silent_drop(tmp_path):
    session_log = tmp_path / "session_cap.log"
    text_lines = []
    for i in range(1, 15):
        text_lines += _op_block_lines(f"op-{i}", i, user_intent="long turn", close="ok")
    session_log.write_text("\n".join(text_lines), encoding="utf-8")

    records = [_jsonl_record(f"op-{i}", i, user_intent="long turn") for i in range(1, 15)]
    slice_obj = reconstruct.reconstruct_slice(records, session_log, anchor_op_id="op-14")

    assert len(slice_obj.ops) == 12
    assert len(slice_obj.truncated_summary) == 2

    rendered = render.render_report(slice_obj)
    assert "summarized, not dropped" in rendered
    assert "op-1" in rendered  # the truncated op still named, not vanished
    assert "op-2" in rendered


# ---------------------------------------------------------------------------
# 4. E2 acceptance case: path-scoped normalization only.
# ---------------------------------------------------------------------------

def test_e2_username_substring_in_lexical_data_survives():
    home_path = r"C:\Users\matt"
    username = "matt"
    text = (
        "Project: C:\\Users\\matt\\Projects\\Sena3.fwdata\n"
        "report.Info: gloss = \"Matthew's toolbox\"\n"
    )
    normalized = normalize.normalize_report_text(text, home_path=home_path, username=username)

    # Path token IS normalized.
    assert r"~\Projects\Sena3.fwdata" in normalized
    assert r"C:\Users\matt\Projects" not in normalized

    # Lexical content is UNTOUCHED -- no document-wide find/replace of "matt".
    assert "Matthew's toolbox" in normalized


def test_e2_document_wide_replace_would_have_failed_this_test():
    """Sanity check that our fixture actually would break under a naive
    document-wide (case-insensitive) substring replace, so the previous
    test is meaningful. Real usernames are matched case-insensitively on
    Windows, so a naive implementation would plausibly do exactly this."""
    import re as _re
    text = "Matthew's toolbox"
    naive = _re.sub("matt", "<user>", text, flags=_re.IGNORECASE)  # what we must NOT do
    assert naive != text  # proves a naive replace DOES corrupt this string
    # ... whereas our real normalizer (previous test) leaves it intact.


def test_e2_sibling_directory_not_falsely_prefix_matched():
    """A directory that merely starts with the same characters as the home
    dir (different actual user) must not be truncated into the home dir."""
    home_path = r"C:\Users\matt"
    username = "matt"
    text = r"Attempted path: C:\Users\matthew\other_project\file.fwdata"
    normalized = normalize.normalize_report_text(text, home_path=home_path, username=username)
    # Must NOT become "~\other_project\..." -- "matthew" != "matt" as a path
    # segment, so the home-dir prefix substitution must not fire here.
    assert r"C:\Users\matthew" in normalized
    assert not normalized.startswith("Attempted path: ~")


def test_e2_username_segment_removed_outside_home_dir():
    home_path = r"C:\Users\matt"
    username = "matt"
    text = r"Discovery call arg: D:\Shares\matt\backup\export.py"
    normalized = normalize.normalize_report_text(text, home_path=home_path, username=username)
    assert r"D:\Shares\<user>\backup\export.py" in normalized


def test_e2_normalize_is_noop_on_text_with_no_path_tokens():
    text = "The user asked to fix the headword 'matt-language-example'."
    normalized = normalize.normalize_report_text(text, home_path=r"C:\Users\matt", username="matt")
    assert normalized == text


# ---------------------------------------------------------------------------
# 5. Seven-section render.
# ---------------------------------------------------------------------------

def test_render_report_has_all_seven_sections_in_order(tmp_path):
    session_log = tmp_path / "session_full.log"
    lines = _session_header_lines()
    lines += _tool_call_lines("flextools_start", '{"user_request": "fix broken gloss casting"}')
    lines += _tool_call_lines("flextools_get_object_api", '{"object_type": "ILexSense"}')
    lines += _op_block_lines(
        "op-fail", 1,
        user_intent="fix broken gloss casting",
        user_request="fix broken gloss casting",
        code="bad = sense.Owner.HeadWord",
        casting_line="Preflight casting: issues=1 tier=full helpers=['safe_get_property']",
        close="fail",
        report_error_line="AttributeError: 'ICmObject' object has no attribute 'HeadWord'",
    )
    lines += _op_block_lines(
        "op-ok", 2,
        user_intent="fix broken gloss casting",
        user_request="fix broken gloss casting",
        code="good = safe_get_property(sense.Owner, 'HeadWord')",
        close="ok",
    )
    session_log.write_text("\n".join(lines), encoding="utf-8")

    records = [
        _jsonl_record("op-fail", 1, outcome="runtime_fail", error_code="PolymorphicAttributeError",
                       user_intent="fix broken gloss casting", user_request="fix broken gloss casting"),
        _jsonl_record("op-ok", 2, outcome="ok",
                       user_intent="fix broken gloss casting", user_request="fix broken gloss casting"),
    ]

    slice_obj = reconstruct.reconstruct_slice(records, session_log, anchor_op_id="op-fail")
    rendered = render.render_report(slice_obj)

    for heading in (
        "## 1. Header",
        "## 2. Request",
        "## 3. Interpretation",
        "## 4. What was tried",
        "## 5. The error",
        "## 6. The resolution",
        "## 7. Structured JSONL appendix",
    ):
        assert heading in rendered

    # Sections appear in spec order.
    positions = [rendered.index(f"## {i}.") for i in range(1, 8)]
    assert positions == sorted(positions)

    # Header carries the captured session environment.
    assert "FlexToolsMCP:" in rendered
    assert "Report schema version: 1" in rendered

    # Request carries verbatim user_request + flextools_start args.
    assert "fix broken gloss casting" in rendered
    assert "flextools_start" in rendered

    # Interpretation carries discovery calls + preflight casting line.
    assert "flextools_get_object_api" in rendered
    assert "Preflight casting: issues=1" in rendered

    # What-was-tried carries both ops' code.
    assert "bad = sense.Owner.HeadWord" in rendered
    assert "good = safe_get_property" in rendered

    # The error carries the report.Error line + joined codes.
    assert "PolymorphicAttributeError" in rendered
    assert "AttributeError: 'ICmObject'" in rendered

    # Resolution names the green follow-up op.
    assert "op-ok" in rendered
    assert "closed `ok`" in rendered

    # Appendix is valid JSONL and includes user_request/user_intent.
    appendix_start = rendered.index("## 7. Structured JSONL appendix")
    appendix_text = rendered[appendix_start:]
    json_lines = [
        l for l in appendix_text.splitlines()
        if l.strip().startswith("{") and l.strip().endswith("}")
    ]
    assert len(json_lines) == 2
    parsed = [json.loads(l) for l in json_lines]
    assert {p["op_id"] for p in parsed} == {"op-fail", "op-ok"}
    for p in parsed:
        assert p["user_request"] == "fix broken gloss casting"
        assert p["user_intent"] == "fix broken gloss casting"


def test_render_abandoned_turn_notes_no_resolution(tmp_path):
    session_log = tmp_path / "session_abandoned.log"
    lines = _op_block_lines("op-only-fail", 1, close="fail")
    session_log.write_text("\n".join(lines), encoding="utf-8")

    records = [_jsonl_record("op-only-fail", 1, outcome="runtime_fail",
                              error_code="PolymorphicAttributeError")]
    slice_obj = reconstruct.reconstruct_slice(records, session_log)
    rendered = render.render_report(slice_obj)
    assert "abandoned" in rendered.lower()


# ---------------------------------------------------------------------------
# 6. Casting-recurrence signature precision (deferred cycle-2 QC P1).
# ---------------------------------------------------------------------------

def test_compute_casting_signature_differs_for_unrelated_issues():
    issues_gloss = [{"property": "Gloss", "missing_on": ["ICmObject"], "cast_interface": "ILexSense"}]
    issues_definition = [{"property": "Definition", "missing_on": ["ICmObject"], "cast_interface": "ILexSense"}]

    sig_gloss = triggers.compute_casting_signature(issues_gloss)
    sig_definition = triggers.compute_casting_signature(issues_definition)

    assert sig_gloss != sig_definition
    assert sig_gloss and sig_definition


def test_compute_casting_signature_stable_for_same_issue_reordered():
    issues_a = [
        {"property": "Gloss", "missing_on": ["ICmObject"], "cast_interface": "ILexSense"},
        {"property": "Definition", "missing_on": ["ICmObject"], "cast_interface": "ILexSense"},
    ]
    issues_b = list(reversed(issues_a))
    assert triggers.compute_casting_signature(issues_a) == triggers.compute_casting_signature(issues_b)


def test_two_unrelated_casting_issues_in_same_turn_no_longer_collapse():
    """Regression for the deferred cycle-2 QC P1 (triggers.py:62-77): the
    CP1 fallback treated ANY two same-turn casting_issues_detected closes as
    a recurrence when casting_signature/preflight_gate were both blank
    (preflight_gate was always the same literal string, "casting_issues_
    detected" -- never a real discriminator). With a real per-issue
    casting_signature threaded in, two UNRELATED casting issues (different
    property + interface) must NOT be treated as a recurrence of each
    other.
    """
    sig_gloss = triggers.compute_casting_signature(
        [{"property": "Gloss", "missing_on": ["ICmObject"], "cast_interface": "ILexSense"}]
    )
    sig_definition = triggers.compute_casting_signature(
        [{"property": "Definition", "missing_on": ["ICmObject"], "cast_interface": "ILexSense"}]
    )
    assert sig_gloss != sig_definition

    turn = [
        {
            "op_id": "op-1", "outcome": "preflight_reject",
            "error_code": "casting_issues_detected", "preflight_gate": "casting_issues_detected",
            "casting_signature": sig_gloss,
        },
        {
            "op_id": "op-2", "outcome": "preflight_reject",
            "error_code": "casting_issues_detected", "preflight_gate": "casting_issues_detected",
            "casting_signature": sig_definition,
        },
    ]
    # Neither is a recurrence of the other -- different underlying issues.
    assert triggers.detect_casting_recurrence(turn) == set()
    assert triggers.find_reportable_closes(turn) == []


def test_two_same_casting_issue_attempts_do_recur_with_real_signature():
    sig = triggers.compute_casting_signature(
        [{"property": "Gloss", "missing_on": ["ICmObject"], "cast_interface": "ILexSense"}]
    )
    turn = [
        {
            "op_id": "op-1", "outcome": "preflight_reject",
            "error_code": "casting_issues_detected", "preflight_gate": "casting_issues_detected",
            "casting_signature": sig,
        },
        {
            "op_id": "op-2", "outcome": "preflight_reject",
            "error_code": "casting_issues_detected", "preflight_gate": "casting_issues_detected",
            "casting_signature": sig,
        },
    ]
    assert triggers.detect_casting_recurrence(turn) == {"op-2"}
    reportable = triggers.find_reportable_closes(turn)
    assert [r["op_id"] for r in reportable] == ["op-2"]


def test_old_jsonl_records_without_casting_signature_field_still_work():
    """Backward compatibility: records written before this field existed
    simply lack the key -- `casting_recurrence_signature()` must fall
    through to `preflight_gate`, never raise."""
    old_style = {"error_code": "casting_issues_detected", "preflight_gate": "cast:Gloss"}
    assert "casting_signature" not in old_style
    sig = triggers.casting_recurrence_signature(old_style)
    assert sig == "cast:Gloss"


def test_casting_signature_round_trips_into_jsonl_record(tmp_path):
    """End-to-end wiring check: op_telemetry._write_jsonl_line accepts and
    persists the new casting_signature field."""
    tel._OP_STASH.clear()
    tel._OP_STASH_ORDER.clear()
    tel._stash_op_start(
        op_id="op-cast-001",
        project="TestProject",
        write_enabled=False,
        source_kind="bare_snippet",
        user_intent="fix gloss",
        user_request=None,
        code_sha256="d" * 64,
        code_bytes=10,
        code_lines=1,
    )
    log_dir = tmp_path
    tel._write_jsonl_line(
        op_id="op-cast-001",
        seq=1,
        outcome="preflight_reject",
        duration_s=0.05,
        error_code="casting_issues_detected",
        preflight_gate="casting_issues_detected",
        info_count=0,
        warning_count=0,
        error_count=0,
        assistance_triggered=False,
        log_dir_fn=lambda: log_dir,
        casting_signature="deadbeefcafefeed",
    )
    lines = (log_dir / "operations.jsonl").read_text(encoding="utf-8").strip().splitlines()
    record = json.loads(lines[0])
    assert record["casting_signature"] == "deadbeefcafefeed"


def test_casting_signature_defaults_to_empty_string_when_not_passed(tmp_path):
    tel._OP_STASH.clear()
    tel._OP_STASH_ORDER.clear()
    tel._stash_op_start(
        op_id="op-cast-002",
        project="TestProject",
        write_enabled=False,
        source_kind="bare_snippet",
        user_intent="fix gloss",
        user_request=None,
        code_sha256="e" * 64,
        code_bytes=10,
        code_lines=1,
    )
    log_dir = tmp_path
    tel._write_jsonl_line(
        op_id="op-cast-002",
        seq=1,
        outcome="ok",
        duration_s=0.05,
        error_code=None,
        preflight_gate=None,
        info_count=0,
        warning_count=0,
        error_count=0,
        assistance_triggered=False,
        log_dir_fn=lambda: log_dir,
    )
    lines = (log_dir / "operations.jsonl").read_text(encoding="utf-8").strip().splitlines()
    record = json.loads(lines[0])
    assert record["casting_signature"] == ""


# ---------------------------------------------------------------------------
# 7. CP2 correctness fix: `issues` must be re-derived after the Issue #46
# partial auto-fix reruns detect_casting_needs, not left bound to the
# stale pre-fix list (execution.py:2077 vs :2108).
# ---------------------------------------------------------------------------

def _stub_execution_preflight(monkeypatch, tmp_path, *, detect_casting_needs, try_auto_fix, validate_patched):
    """Wire handle_run_module's dependencies so only the casting-preflight /
    auto-fix section under test runs with real logic; every other pre-flight
    gate is stubbed to "pass"."""
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})
    monkeypatch.setattr(
        execution_mod, "certify_script_readonly",
        lambda code, api_idx, tree: {"is_certified_readonly": True},
    )
    monkeypatch.setattr(execution_mod, "detect_casting_needs", detect_casting_needs)
    monkeypatch.setattr(execution_mod, "_try_auto_fix_casting", try_auto_fix)
    monkeypatch.setattr(execution_mod, "_validate_patched_code", validate_patched)


def test_partial_auto_fix_reports_only_residual_casting_issue(monkeypatch, tmp_path):
    """Regression for the CP2 P1: when Issue #46 auto-fix resolves ONE of TWO
    distinct casting issues (Gloss fixed, Definition still unresolved), the
    still-has-issues rejection branch must report ONLY the residual
    (Definition) issue -- not the already-fixed (Gloss) one from the stale
    pre-fix `issues` binding.
    """
    resolved_issue = {
        "property": "Gloss", "line": 3, "found_at": "sense.Gloss",
        "severity": "error", "cast_interface": "ILexSense",
        "rewrite": "ILexSense(sense).Gloss", "missing_on": ["ICmObject"],
        "imports_needed": ["from SIL.LCModel import ILexSense"],
    }
    residual_issue = {
        "property": "Definition", "line": 5, "found_at": "sense.Definition",
        "severity": "warning", "cast_interface": "ILexSense",
        "rewrite": "ILexSense(sense).Definition", "missing_on": ["ICmObject"],
        "imports_needed": ["from SIL.LCModel import ILexSense"],
    }

    calls = {"n": 0}

    def fake_detect_casting_needs(code, casting_index, code_tree):
        calls["n"] += 1
        if calls["n"] == 1:
            # Original submission: both issues present.
            return {
                "has_casting_issues": True,
                "casting_issues": [resolved_issue, residual_issue],
                "severity": "error",
            }
        # Re-run on the patched code: only the residual issue remains.
        return {
            "has_casting_issues": True,
            "casting_issues": [residual_issue],
            "severity": "warning",
        }

    def fake_try_auto_fix_casting(code, issues, api_idx, code_tree):
        return {
            "patched_code": code + "\n# auto-fixed\n",
            "fixes": [{
                "kind": "casting", "line": 3, "original": "sense.Gloss",
                "replacement": "ILexSense(sense).Gloss", "cast_interface": "ILexSense",
            }],
        }

    _stub_execution_preflight(
        monkeypatch, tmp_path,
        detect_casting_needs=fake_detect_casting_needs,
        try_auto_fix=fake_try_auto_fix_casting,
        validate_patched=lambda *a, **k: True,
    )

    args = {
        "code": (
            "sense = None\n"
            "x = 1\n"
            "print(sense.Gloss)\n"
            "x = 2\n"
            "print(sense.Definition)\n"
        ),
        "project_name": "TestProject",
        "write_enabled": False,
        "auto_fix": True,
        "skip_module_check": True,
    }

    result = asyncio.run(execution_mod.handle_run_module(args))
    payload = json.loads(result[0].text)

    assert payload["error_code"] == "casting_issues_detected"
    reported_properties = {ci["property"] for ci in payload["casting_issues"]}
    # Only the residual issue -- the already-fixed Gloss issue must NOT
    # reappear in the rejection payload.
    assert reported_properties == {"Definition"}

    expected_signature = triggers.compute_casting_signature([residual_issue])
    stale_signature = triggers.compute_casting_signature([resolved_issue, residual_issue])
    assert expected_signature != stale_signature

    jsonl_path = tmp_path / "operations.jsonl"
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    record = json.loads(lines[-1])
    assert record["casting_signature"] == expected_signature
