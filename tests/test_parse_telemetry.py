"""Tests for issue #167 (parser-check CP6) -- parse-path operation logging.

Assertions covered:
  T1  one call to a covered parse tool writes exactly one JSONL line
  T2  fields on that line are derived from the actual response body, not
      invented (project, run_id, outcome, error_code, duration_s)
  T3  a response carrying no run_id / no project omits those fields as ""
      rather than guessing
  T4  an error envelope's error_code is captured and outcome == "error"
  T5  a non-"ok"/"error" status (e.g. "refused") is passed through verbatim,
      not collapsed to "error" or "ok"
  T6  words_total / words_completed are recorded for parse_text /
      parse_sandbox ONLY when the response actually carries them, and
      words_total falls back to scope.words_resolved for the no-run path
  T7  a tool NOT in PARSE_TOOL_NAMES (e.g. flextools_run_module) is a no-op
      -- no JSONL line written
  T8  a malformed response body (non-JSON text, empty result) never raises
      and still writes a best-effort line
  T9  a write failure (log dir resolution raises) never raises out of
      log_parse_op
  T10 compute_jsonl_statistics ignores "kind": "parse" records entirely --
      a parse-tool error does not get counted into run_module's
      rejects_by_error_code / green-rate stats

Issue #167 follow-up (audit of every OTHER reader of operations.jsonl, so a
parse record can't miscount or crash it):
  T11 op_telemetry.is_run_module_record() is the shared predicate other
      consumers use; it defaults a "kind"-less legacy record to run_module
  T12 scripts/green_report.py's load_jsonl() drops "kind": "parse" records
      at the load point, so total_records/groups/rejects/retry_loop_trips
      are unaffected by an interleaved parse call
  T13 diagnostic_health._build_recent_operations() KEEPS parse records (a
      general "what happened recently" snapshot) but now labels each entry
      with its "kind" so parse activity is never mistaken for a run_module op
  T14 diagnostic_report.build_advisory_for_success_close() / handle_prepare_
      report() filter to run_module records before turn-grouping, so a
      parse call interleaved between two same-intent run_module ops does not
      fragment the turn and break the auto-offer / prepare-report pipeline
"""

import json
import sys
from pathlib import Path

import pytest
from mcp.types import TextContent

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# scripts/ isn't a package; import green_report.py directly (T12), matching
# the existing pattern in tests/test_op_telemetry.py.
_SCRIPTS = _HERE.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def _fresh_parse_telemetry():
    import importlib
    from flextoolsmcp.server.handlers import parse_telemetry as pt
    importlib.reload(pt)
    return pt


def _response(data: dict) -> list:
    return [TextContent(type="text", text=json.dumps(data))]


def _read_jsonl(log_dir: Path) -> list:
    path = log_dir / "operations.jsonl"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ---------------------------------------------------------------------------
# T1 / T2 -- one line, fields derived from the actual response
# ---------------------------------------------------------------------------

def test_one_record_per_call_fields_from_response(tmp_path, monkeypatch):
    pt = _fresh_parse_telemetry()
    monkeypatch.setattr(pt, "_get_log_dir", lambda: tmp_path)

    response = _response({
        "status": "ok",
        "project": "Sena 3",
        "run_id": "run_abc123",
    })
    pt.log_parse_op(
        "flextools_parse_status",
        {"project_name": "Sena 3", "run_id": "run_abc123"},
        response,
        0.1234567,
    )

    records = _read_jsonl(tmp_path)
    assert len(records) == 1
    rec = records[0]
    assert rec["kind"] == "parse"
    assert rec["tool"] == "flextools_parse_status"
    assert rec["project"] == "Sena 3"
    assert rec["run_id"] == "run_abc123"
    assert rec["outcome"] == "ok"
    assert rec["error_code"] == ""
    assert rec["duration_s"] == pytest.approx(0.1235, abs=1e-4)
    # Only two calls -> only one line, never more.
    pt.log_parse_op(
        "flextools_parse_status",
        {"project_name": "Sena 3"},
        response,
        0.01,
    )
    assert len(_read_jsonl(tmp_path)) == 2


# ---------------------------------------------------------------------------
# T3 -- missing fields are omitted/"" rather than guessed
# ---------------------------------------------------------------------------

def test_missing_run_id_and_project_are_not_invented(tmp_path, monkeypatch):
    pt = _fresh_parse_telemetry()
    monkeypatch.setattr(pt, "_get_log_dir", lambda: tmp_path)

    response = _response({"status": "ok"})
    pt.log_parse_op("flextools_try_word", {}, response, 0.02)

    rec = _read_jsonl(tmp_path)[0]
    assert rec["run_id"] == ""
    assert rec["project"] == ""
    # word-count fields never appear for a tool outside _WORD_COUNT_TOOLS
    assert "words_total" not in rec
    assert "words_completed" not in rec


def test_project_falls_back_to_argument_when_response_omits_it(tmp_path, monkeypatch):
    pt = _fresh_parse_telemetry()
    monkeypatch.setattr(pt, "_get_log_dir", lambda: tmp_path)

    response = _response({"status": "ok"})
    pt.log_parse_op(
        "flextools_try_word", {"project_name": "Target"}, response, 0.02
    )
    rec = _read_jsonl(tmp_path)[0]
    assert rec["project"] == "Target"


# ---------------------------------------------------------------------------
# T4 -- error envelope
# ---------------------------------------------------------------------------

def test_error_envelope_captures_error_code(tmp_path, monkeypatch):
    pt = _fresh_parse_telemetry()
    monkeypatch.setattr(pt, "_get_log_dir", lambda: tmp_path)

    response = _response({
        "status": "error",
        "error_code": "parser_core_missing",
        "message": "The parser is not available",
    })
    pt.log_parse_op("flextools_try_word", {"project_name": "Target"}, response, 0.5)

    rec = _read_jsonl(tmp_path)[0]
    assert rec["outcome"] == "error"
    assert rec["error_code"] == "parser_core_missing"


def test_deprecated_nested_error_shape_still_yields_error_code(tmp_path, monkeypatch):
    pt = _fresh_parse_telemetry()
    monkeypatch.setattr(pt, "_get_log_dir", lambda: tmp_path)

    response = _response({
        "status": "error",
        "error": {"code": "project_locked", "message": "busy"},
    })
    pt.log_parse_op("flextools_parse_cancel", {}, response, 0.01)

    rec = _read_jsonl(tmp_path)[0]
    assert rec["error_code"] == "project_locked"
    assert rec["outcome"] == "error"


# ---------------------------------------------------------------------------
# T5 -- non-ok/error status passed through verbatim
# ---------------------------------------------------------------------------

def test_non_binary_status_passed_through_verbatim(tmp_path, monkeypatch):
    pt = _fresh_parse_telemetry()
    monkeypatch.setattr(pt, "_get_log_dir", lambda: tmp_path)

    response = _response({"status": "refused", "refusal": {"error_code": "project_locked"}})
    pt.log_parse_op("flextools_parse_sandbox", {}, response, 0.01)

    rec = _read_jsonl(tmp_path)[0]
    # "refused" must NOT be collapsed to "error" -- the response never
    # said error, it said refused; those are different, real statuses.
    assert rec["outcome"] == "refused"
    # No top-level error_code in this envelope shape -> "" not invented.
    assert rec["error_code"] == ""


# ---------------------------------------------------------------------------
# T6 -- word counts only for the two tools that can carry them
# ---------------------------------------------------------------------------

def test_word_counts_recorded_for_parse_text_when_present(tmp_path, monkeypatch):
    pt = _fresh_parse_telemetry()
    monkeypatch.setattr(pt, "_get_log_dir", lambda: tmp_path)

    response = _response({
        "status": "ok",
        "run_id": "run_1",
        "words_completed": 3,
        "words_total": 42,
    })
    pt.log_parse_op("flextools_parse_text", {}, response, 1.0)

    rec = _read_jsonl(tmp_path)[0]
    assert rec["words_total"] == 42
    assert rec["words_completed"] == 3


def test_word_total_falls_back_to_scope_words_resolved(tmp_path, monkeypatch):
    pt = _fresh_parse_telemetry()
    monkeypatch.setattr(pt, "_get_log_dir", lambda: tmp_path)

    # The "scope yielded no words, no run started" shape from
    # handle_flextools_parse_text: no top-level words_total/words_completed.
    response = _response({
        "status": "ok",
        "run_id": None,
        "run_started": False,
        "scope": {"words_resolved": 7},
    })
    pt.log_parse_op("flextools_parse_text", {}, response, 0.3)

    rec = _read_jsonl(tmp_path)[0]
    assert rec["words_total"] == 7
    assert "words_completed" not in rec
    assert rec["run_id"] == ""  # run_id was null -> omitted, not "None"


def test_word_counts_not_recorded_for_unrelated_tool(tmp_path, monkeypatch):
    pt = _fresh_parse_telemetry()
    monkeypatch.setattr(pt, "_get_log_dir", lambda: tmp_path)

    # Even if some unrelated tool's response happened to carry these keys,
    # they must not leak into the record -- only parse_text/parse_sandbox do.
    response = _response({"status": "ok", "words_total": 99, "words_completed": 5})
    pt.log_parse_op("flextools_parse_status", {}, response, 0.1)

    rec = _read_jsonl(tmp_path)[0]
    assert "words_total" not in rec
    assert "words_completed" not in rec


# ---------------------------------------------------------------------------
# T7 -- non-parse tool is a no-op
# ---------------------------------------------------------------------------

def test_non_parse_tool_writes_nothing(tmp_path, monkeypatch):
    pt = _fresh_parse_telemetry()
    monkeypatch.setattr(pt, "_get_log_dir", lambda: tmp_path)

    response = _response({"status": "ok"})
    pt.log_parse_op("flextools_run_module", {}, response, 0.1)

    assert _read_jsonl(tmp_path) == []


# ---------------------------------------------------------------------------
# T8 / T9 -- never raises
# ---------------------------------------------------------------------------

def test_malformed_response_never_raises(tmp_path, monkeypatch):
    pt = _fresh_parse_telemetry()
    monkeypatch.setattr(pt, "_get_log_dir", lambda: tmp_path)

    not_json = [TextContent(type="text", text="not json at all")]
    pt.log_parse_op("flextools_try_word", {"project_name": "Target"}, not_json, 0.1)
    # Best-effort line still written, with empty derived fields.
    rec = _read_jsonl(tmp_path)[0]
    assert rec["project"] == "Target"
    assert rec["outcome"] == "unknown"

    # Empty result list.
    pt.log_parse_op("flextools_try_word", {}, [], 0.1)
    assert len(_read_jsonl(tmp_path)) == 2


def test_log_dir_failure_never_raises(monkeypatch):
    pt = _fresh_parse_telemetry()

    def _boom():
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(pt, "_get_log_dir", _boom)
    response = _response({"status": "ok"})
    # Must not raise.
    pt.log_parse_op("flextools_try_word", {}, response, 0.1)


# ---------------------------------------------------------------------------
# T10 -- run_module report/statistics is not miscounted by parse records
# ---------------------------------------------------------------------------

def test_report_ignores_parse_kind_records(tmp_path, monkeypatch):
    from flextoolsmcp.server.handlers import op_telemetry as tel

    pt = _fresh_parse_telemetry()
    monkeypatch.setattr(pt, "_get_log_dir", lambda: tmp_path)

    # One parse-tool error (should NOT show up in run_module's stats)...
    err_response = _response({"status": "error", "error_code": "parser_core_missing"})
    pt.log_parse_op("flextools_try_word", {}, err_response, 0.1)

    # ...and one genuine run_module success/failure pair, written the way
    # execution.py actually writes them (kind defaults to "run_module").
    tel._write_jsonl_line(
        op_id="op1", seq=1, outcome="ok", duration_s=1.0, error_code=None,
        preflight_gate=None, info_count=0, warning_count=0, error_count=0,
        assistance_triggered=False, log_dir_fn=lambda: tmp_path,
    )
    tel._write_jsonl_line(
        op_id="op2", seq=2, outcome="runtime_fail", duration_s=1.0,
        error_code="some_run_module_error", preflight_gate=None,
        info_count=0, warning_count=0, error_count=1,
        assistance_triggered=False, log_dir_fn=lambda: tmp_path,
    )

    records = _read_jsonl(tmp_path)
    assert len(records) == 3  # all three really were written to one file
    kinds = sorted(r["kind"] for r in records)
    assert kinds == ["parse", "run_module", "run_module"]

    stats = tel.compute_jsonl_statistics(tmp_path)
    # The parse tool's error_code must not appear among run_module's rejects.
    codes = [row["error_code"] for row in stats["rejects_by_error_code"]]
    assert "parser_core_missing" not in codes
    assert "some_run_module_error" in codes
    # Green rate is computed over the 2 run_module ops only (1 ok / 2 -> 0.5),
    # not diluted or corrupted by the 3rd (parse) record.
    assert stats["first_pass_green_rate"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# T11 -- op_telemetry.is_run_module_record() is the shared predicate
# ---------------------------------------------------------------------------

def test_is_run_module_record_shared_predicate():
    from flextoolsmcp.server.handlers import op_telemetry as tel

    assert tel.is_run_module_record({"kind": "run_module"}) is True
    assert tel.is_run_module_record({"kind": "parse"}) is False
    # A pre-#167 legacy record has no "kind" key at all -- defaults to
    # run_module for backward compatibility (same default
    # compute_jsonl_statistics already used before this helper existed).
    assert tel.is_run_module_record({"outcome": "ok"}) is True


# ---------------------------------------------------------------------------
# T12 -- scripts/green_report.py drops "kind": "parse" records at load time
# ---------------------------------------------------------------------------

def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def test_green_report_load_jsonl_excludes_parse_records(tmp_path):
    import green_report

    parse_rec = {
        "ts": "2026-09-27T00:00:00Z", "kind": "parse", "tool": "flextools_try_word",
        "project": "Target", "run_id": "", "outcome": "error",
        "error_code": "parser_core_missing", "duration_s": 0.1,
    }
    run_module_ok = {
        "ts": "2026-09-27T00:00:01Z", "kind": "run_module", "op_id": "op1",
        "seq": 1, "session_id": "sess-a", "user_intent": "fix the bug",
        "outcome": "ok", "error_code": "", "assistance_triggered": False,
    }
    run_module_fail = {
        "ts": "2026-09-27T00:00:02Z", "kind": "run_module", "op_id": "op2",
        "seq": 2, "session_id": "sess-b", "user_intent": "fix the bug",
        "outcome": "runtime_fail", "error_code": "SomeError",
        "assistance_triggered": False,
    }
    jsonl_path = tmp_path / "operations.jsonl"
    _write_jsonl(jsonl_path, [parse_rec, run_module_ok, run_module_fail])

    records, skipped = green_report.load_jsonl([jsonl_path])

    assert skipped == 0
    assert len(records) == 2
    assert all(r["kind"] == "run_module" for r in records)

    metrics = green_report.compute_metrics(records)
    # Only the 2 run_module ops feed the metrics -- 2 groups (different
    # session_ids), 1 first-pass green, and only run_module's error_code
    # among the rejects.
    assert metrics["total_records"] == 2
    assert metrics["total_groups"] == 2
    assert metrics["first_pass_green"] == 1
    assert metrics["rejects_by_error_code"] == {"SomeError": 1}
    assert "parser_core_missing" not in metrics["rejects_by_error_code"]


# ---------------------------------------------------------------------------
# T13 -- diagnostic_health._build_recent_operations() keeps parse activity
# but labels each entry with its "kind"
# ---------------------------------------------------------------------------

def test_diagnostic_health_recent_operations_labels_kind(tmp_path, monkeypatch):
    from flextoolsmcp.server.handlers import diagnostic_health as dh

    parse_rec = {
        "ts": "2026-09-27T00:00:00Z", "kind": "parse", "tool": "flextools_try_word",
        "project": "Target", "outcome": "ok", "error_code": "",
    }
    run_module_rec = {
        "ts": "2026-09-27T00:00:01Z", "kind": "run_module", "op_id": "op1",
        "seq": 1, "project": "Target", "outcome": "ok", "error_code": "",
    }
    legacy_rec = {  # pre-#167: no "kind" key at all
        "ts": "2026-09-27T00:00:02Z", "op_id": "op0", "seq": 0,
        "project": "Target", "outcome": "ok", "error_code": "",
    }
    log_dir = tmp_path
    _write_jsonl(log_dir / "operations.jsonl", [parse_rec, run_module_rec, legacy_rec])

    monkeypatch.setattr(dh, "get_log_dir", lambda: log_dir)

    recent = dh._build_recent_operations(limit=5)

    assert len(recent) == 3
    kinds = [r["kind"] for r in recent]
    assert kinds == ["parse", "run_module", "run_module"]  # legacy defaults


# ---------------------------------------------------------------------------
# T14 -- diagnostic_report filters to run_module records before turn-grouping
# ---------------------------------------------------------------------------

def _fmt(level: str, msg: str, ts: str = "2026-09-27 09:15:00") -> str:
    return f"{ts} | {level:<7} | {msg}"


def _dr_fail_block():
    return [
        _fmt("INFO", "=== Operation #1 Start (op-1) ==="),
        _fmt("INFO", "Project:         DemoProject"),
        _fmt("INFO", "Write enabled:   False"),
        _fmt("INFO", "Source kind:     bare_snippet"),
        _fmt("INFO", "User intent:     fix the parse issue"),
        _fmt("INFO", "User request:    fix the parse issue"),
        _fmt("INFO", "Code fingerprint: sha256=abc123 bytes=42 lines=2"),
        _fmt("ERROR", "[FAIL] Operation failed"),
        _fmt("ERROR", "Error type:      PolymorphicAttributeError"),
        _fmt("ERROR", "  report.Error: 'ICmObject' object has no attribute 'HeadWord'"),
        _fmt("INFO", "Messages:        0 info, 0 warnings, 1 errors"),
        _fmt("INFO", "Duration:        0.120s"),
        _fmt("INFO", "=== Operation #1 End (op-1) ==="),
    ]


def _dr_ok_block():
    return [
        _fmt("INFO", "=== Operation #2 Start (op-2) ==="),
        _fmt("INFO", "Project:         DemoProject"),
        _fmt("INFO", "Write enabled:   False"),
        _fmt("INFO", "Source kind:     bare_snippet"),
        _fmt("INFO", "User intent:     fix the parse issue"),
        _fmt("INFO", "User request:    fix the parse issue"),
        _fmt("INFO", "Code fingerprint: sha256=def456 bytes=61 lines=2"),
        _fmt("INFO", "[OK] Operation completed successfully"),
        _fmt("INFO", "Messages:        3 info, 0 warnings, 0 errors"),
        _fmt("INFO", "Duration:        0.090s"),
        _fmt("INFO", "=== Operation #2 End (op-2) ==="),
    ]


def _dr_records_with_interleaved_parse():
    common = {
        "ts": "2026-09-27T09:15:00Z", "kind": "run_module", "project": "DemoProject",
        "write_enabled": False, "source_kind": "bare_snippet",
        "user_intent": "fix the parse issue",
        "user_request": "fix the parse issue",
        "code_bytes": 42, "code_lines": 2, "preflight_gate": "",
        "casting_signature": "", "duration_s": 0.1,
        "info_count": 0, "warning_count": 0, "error_count": 0,
    }
    fail = dict(common, op_id="op-1", seq=1, outcome="runtime_fail",
                error_code="PolymorphicAttributeError", code_sha256="a" * 64,
                error_count=1)
    # A parse-tool call the user made BETWEEN op-1 and op-2 in the same turn
    # (e.g. flextools_try_word while investigating the failure). It has no
    # op_id/session_id/user_intent at all.
    parse_call = {
        "ts": "2026-09-27T09:15:30Z", "kind": "parse", "tool": "flextools_try_word",
        "project": "DemoProject", "run_id": "", "outcome": "ok", "error_code": "",
        "duration_s": 0.05,
    }
    ok = dict(common, op_id="op-2", seq=2, outcome="ok", error_code="",
              code_sha256="b" * 64, info_count=3)
    return [fail, parse_call, ok]


@pytest.fixture
def dr_env_with_parse_interleaved(tmp_path, monkeypatch):
    from flextoolsmcp.server.handlers import diagnostic_report
    from flextoolsmcp.server.diagnostic import offered_store

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    session_log = log_dir / "session_demo.log"
    session_log.write_text(
        "\n".join(_dr_fail_block() + _dr_ok_block()), encoding="utf-8"
    )

    records = _dr_records_with_interleaved_parse()
    _write_jsonl(log_dir / "operations.jsonl", records)

    reports_dir = tmp_path / "reports"
    offered_dir = tmp_path / "offered_state"

    monkeypatch.setattr(diagnostic_report, "get_log_dir", lambda: log_dir)
    monkeypatch.setattr(
        diagnostic_report, "get_current_session_log_path", lambda: session_log
    )
    monkeypatch.setattr(diagnostic_report, "_default_reports_dir", lambda: reports_dir)
    monkeypatch.setattr(offered_store, "get_reports_dir", lambda: offered_dir)
    return {"records": records}


def test_diagnostic_report_advisory_not_fragmented_by_interleaved_parse_call(
    dr_env_with_parse_interleaved,
):
    """A parse-tool call interleaved between op-1 (failure) and op-2 (its
    same-turn `ok` resolution) must NOT split them into two turns -- the
    auto-offer at op-2's success close should still find op-1's reportable
    failure and build a bundle for it, exactly as it would with no parse
    call in between (see tests/test_diagnostic_report_demo.py)."""
    from flextoolsmcp.server.handlers import diagnostic_report

    advisory = diagnostic_report.build_advisory_for_success_close("op-2")

    assert advisory is not None
    assert advisory["error_code"] == "PolymorphicAttributeError"
    assert "PolymorphicAttributeError" in advisory["title"]
    assert Path(advisory["report_path"]).exists()


def test_diagnostic_report_prepare_report_excludes_parse_from_slice(
    dr_env_with_parse_interleaved,
):
    """flextools_prepare_report's explicit path (prepare_report_bundle) must
    reconstruct the run_module turn (op-1, op-2) without the interleaved
    parse record ever entering turn_records -- it has no op_id/seq and would
    otherwise be a spurious standalone group or ops entry."""
    from flextoolsmcp.server.handlers import diagnostic_report

    log_dir = diagnostic_report.get_log_dir()
    session_log_path = diagnostic_report.get_current_session_log_path()
    all_records = [
        r for r in diagnostic_report._load_jsonl_records(log_dir)
        if diagnostic_report.is_run_module_record(r)
    ]

    bundle = diagnostic_report.prepare_report_bundle(
        all_records, session_log_path, anchor_op_id="op-2",
    )

    assert bundle is not None
    # turn_records is not directly on the bundle dict; verify via the
    # rendered markdown instead, which lists every op in the slice.
    assert "op-1" in bundle["report_markdown"]
    assert "op-2" in bundle["report_markdown"]
    assert "flextools_try_word" not in bundle["report_markdown"]
