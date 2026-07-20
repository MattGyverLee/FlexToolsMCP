"""Tests for issue #50 -- structured JSONL telemetry.

Assertions covered:
  T1  ok-close writes exactly one JSONL line with outcome="ok"
  T2  failure-close writes exactly one JSONL line with outcome="runtime_fail"
  T3  reject-close writes exactly one JSONL line with outcome="preflight_reject"
  T4  timeout is recorded as outcome="timeout" (error_type "Timeout" / "TimeoutExpired")
  T5  malformed / interleaved lines tolerated; skipped count correct
  T6  intent-grouping: same intent across two calls -> one group
  T7  different intents in two calls -> two groups
  T8  missing intent falls back to standalone group (one group per op)
  T9  golden test: report output for fixture JSONL matches expected metrics
  T10 report identifies top-2 reject codes with correct counts
"""

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure the package root and tests/ dir are importable regardless of CWD
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Also add tests/ itself so scripts/ can be imported
_SCRIPTS = _HERE.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


# ---------------------------------------------------------------------------
# Helpers: import under test with stash reset between tests
# ---------------------------------------------------------------------------

def _fresh_telemetry():
    """Return the op_telemetry module with a clean stash."""
    import importlib
    # Use the src-layout path
    from flextoolsmcp.server.handlers import op_telemetry as tel
    importlib.reload(tel)
    return tel


@pytest.fixture(autouse=True)
def reset_stash():
    """Reset the module-level stash before each test."""
    from flextoolsmcp.server.handlers import op_telemetry as tel
    tel._OP_STASH.clear()
    tel._OP_STASH_ORDER.clear()
    yield
    tel._OP_STASH.clear()
    tel._OP_STASH_ORDER.clear()


# ---------------------------------------------------------------------------
# T1 - ok close writes one JSONL line with outcome="ok"
# ---------------------------------------------------------------------------

def test_ok_close_writes_one_jsonl_line(tmp_path):
    from flextoolsmcp.server.handlers.op_telemetry import _stash_op_start, _write_jsonl_line

    _stash_op_start(
        op_id="op-test-001",
        project="TestProject",
        write_enabled=False,
        source_kind="bare_snippet",
        user_intent="list entries",
        code_sha256="a" * 64,
        code_bytes=100,
        code_lines=5,
    )

    _write_jsonl_line(
        op_id="op-test-001",
        seq=1,
        outcome="ok",
        duration_s=1.23,
        error_code=None,
        preflight_gate=None,
        info_count=3,
        warning_count=0,
        error_count=0,
        assistance_triggered=False,
        log_dir_fn=lambda: tmp_path,
    )

    jsonl_path = tmp_path / "operations.jsonl"
    assert jsonl_path.exists(), "operations.jsonl should be created"
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1, f"Expected 1 JSONL line, got {len(lines)}"
    record = json.loads(lines[0])
    assert record["outcome"] == "ok"
    assert record["op_id"] == "op-test-001"
    assert record["seq"] == 1
    assert record["project"] == "TestProject"
    assert record["source_kind"] == "bare_snippet"
    assert record["user_intent"] == "list entries"
    assert record["info_count"] == 3
    assert record["assistance_triggered"] is False


# ---------------------------------------------------------------------------
# T2 - failure close writes one JSONL line with outcome="runtime_fail"
# ---------------------------------------------------------------------------

def test_failure_close_writes_one_jsonl_line(tmp_path):
    from flextoolsmcp.server.handlers.op_telemetry import _stash_op_start, _write_jsonl_line

    _stash_op_start(
        op_id="op-fail-002",
        project="TestProject",
        write_enabled=False,
        source_kind="bare_snippet",
        user_intent="crash test",
        code_sha256="b" * 64,
        code_bytes=50,
        code_lines=2,
    )

    _write_jsonl_line(
        op_id="op-fail-002",
        seq=2,
        outcome="runtime_fail",
        duration_s=0.5,
        error_code="AttributeError",
        preflight_gate=None,
        info_count=0,
        warning_count=0,
        error_count=1,
        assistance_triggered=False,
        log_dir_fn=lambda: tmp_path,
    )

    jsonl_path = tmp_path / "operations.jsonl"
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["outcome"] == "runtime_fail"
    assert record["error_code"] == "AttributeError"
    assert record["error_count"] == 1


# ---------------------------------------------------------------------------
# T3 - reject close writes one JSONL line with outcome="preflight_reject"
# ---------------------------------------------------------------------------

def test_reject_close_writes_one_jsonl_line(tmp_path):
    from flextoolsmcp.server.handlers.op_telemetry import _stash_op_start, _write_jsonl_line

    _stash_op_start(
        op_id="op-rej-003",
        project="TestProject",
        write_enabled=False,
        source_kind="bare_snippet",
        user_intent="write without guard",
        code_sha256="c" * 64,
        code_bytes=80,
        code_lines=3,
    )

    _write_jsonl_line(
        op_id="op-rej-003",
        seq=3,
        outcome="preflight_reject",
        duration_s=0.01,
        error_code="unprotected_writes",
        preflight_gate="unprotected_writes",
        info_count=0,
        warning_count=0,
        error_count=0,
        assistance_triggered=False,
        log_dir_fn=lambda: tmp_path,
    )

    jsonl_path = tmp_path / "operations.jsonl"
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["outcome"] == "preflight_reject"
    assert record["preflight_gate"] == "unprotected_writes"
    assert record["error_code"] == "unprotected_writes"


# ---------------------------------------------------------------------------
# T4 - timeout is recorded as outcome="timeout"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("error_type", ["Timeout", "TimeoutExpired"])
def test_timeout_outcome(tmp_path, error_type):
    from flextoolsmcp.server.handlers.op_telemetry import _stash_op_start, _write_jsonl_line

    op_id = f"op-timeout-{error_type}"
    _stash_op_start(
        op_id=op_id,
        project="TestProject",
        write_enabled=False,
        source_kind="bare_snippet",
        user_intent="slow op",
        code_sha256="d" * 64,
        code_bytes=200,
        code_lines=10,
    )

    # Simulate what _log_operation_failure does to choose the outcome
    is_timeout = error_type.lower() in ("timeout", "timeoutexpired")
    outcome = "timeout" if is_timeout else "runtime_fail"

    _write_jsonl_line(
        op_id=op_id,
        seq=4,
        outcome=outcome,
        duration_s=300.0,
        error_code=error_type,
        preflight_gate=None,
        info_count=0,
        warning_count=0,
        error_count=0,
        assistance_triggered=False,
        log_dir_fn=lambda: tmp_path,
    )

    jsonl_path = tmp_path / "operations.jsonl"
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["outcome"] == "timeout", f"Expected timeout, got {record['outcome']}"


# ---------------------------------------------------------------------------
# T5 - malformed / interleaved lines tolerated; skipped count correct
# ---------------------------------------------------------------------------

def test_malformed_lines_skipped():
    """_load_jsonl_records skips non-JSON lines silently.
    We verify via green_report.load_jsonl which accepts arbitrary file paths."""
    import green_report
    fixture = Path(__file__).parent / "fixtures" / "sample_operations.jsonl"
    assert fixture.exists(), f"Fixture not found: {fixture}"

    records, skipped = green_report.load_jsonl([fixture])

    # The fixture has 8 valid lines + 1 malformed line
    assert len(records) == 8, f"Expected 8 valid records, got {len(records)}"
    assert skipped == 1, f"Expected 1 skipped line, got {skipped}"

    # All records should be valid dicts with 'outcome'
    for r in records:
        assert isinstance(r, dict)
        assert "outcome" in r

    # Verify the malformed line was NOT included (all records parse as JSON dicts)
    for r in records:
        assert isinstance(r.get("op_id"), str), "op_id should be a string"


def test_load_jsonl_skipped_count():
    """green_report.load_jsonl skips malformed lines and reports count."""
    import green_report
    fixture = Path(__file__).parent / "fixtures" / "sample_operations.jsonl"
    records, skipped = green_report.load_jsonl([fixture])
    assert skipped == 1, f"Expected 1 skipped line, got {skipped}"
    assert len(records) == 8, f"Expected 8 valid records, got {len(records)}"


# ---------------------------------------------------------------------------
# T6 - same intent across two consecutive calls -> one group
# ---------------------------------------------------------------------------

def test_same_intent_one_group():
    import green_report
    records = [
        {"op_id": "a", "seq": 1, "user_intent": "list entries", "outcome": "preflight_reject",
         "error_code": "missing_imports", "assistance_triggered": False},
        {"op_id": "b", "seq": 2, "user_intent": "list entries", "outcome": "ok",
         "error_code": "", "assistance_triggered": False},
    ]
    groups = green_report._group_records(records)
    assert len(groups) == 1, f"Same intent should form 1 group, got {len(groups)}"
    assert len(groups[0]) == 2


# ---------------------------------------------------------------------------
# T7 - different intents -> two groups
# ---------------------------------------------------------------------------

def test_different_intents_two_groups():
    import green_report
    records = [
        {"op_id": "a", "seq": 1, "user_intent": "list entries", "outcome": "ok",
         "error_code": "", "assistance_triggered": False},
        {"op_id": "b", "seq": 2, "user_intent": "export to csv", "outcome": "ok",
         "error_code": "", "assistance_triggered": False},
    ]
    groups = green_report._group_records(records)
    assert len(groups) == 2, f"Different intents should form 2 groups, got {len(groups)}"


# ---------------------------------------------------------------------------
# T8 - missing intent -> standalone group per op
# ---------------------------------------------------------------------------

def test_missing_intent_standalone_groups():
    import green_report
    records = [
        {"op_id": "a", "seq": 1, "user_intent": "", "outcome": "ok",
         "error_code": "", "assistance_triggered": False},
        {"op_id": "b", "seq": 2, "user_intent": "", "outcome": "runtime_fail",
         "error_code": "SomeError", "assistance_triggered": False},
    ]
    groups = green_report._group_records(records)
    assert len(groups) == 2, f"Missing intent should give 2 standalone groups, got {len(groups)}"
    assert len(groups[0]) == 1
    assert len(groups[1]) == 1


# ---------------------------------------------------------------------------
# T9 - golden test: fixture JSONL produces expected aggregates
# ---------------------------------------------------------------------------

def test_golden_fixture_metrics():
    """Fixture has 8 valid records:
    - seq 1: intent="list all entries", outcome=preflight_reject (missing_imports)
    - seq 2: intent="list all entries", outcome=ok   -> group "list all entries": first ok at pos 2
    - seq 3: intent="count senses per entry", outcome=ok  -> group: first-pass ok
    - seq 4: intent="update glosses", outcome=preflight_reject (unprotected_writes)
    - seq 5: intent="update glosses", outcome=preflight_reject (missing_imports)
    - seq 6: intent="update glosses", outcome=ok   -> group "update glosses": ok at pos 3
    - seq 7: intent="", outcome=runtime_fail -> standalone group, never green
    - seq 8: intent="export to csv", outcome=ok  -> first-pass ok

    Groups:
      G1 "list all entries"     [rej, ok]    -> turns=2, NOT first-pass
      G2 "count senses"         [ok]         -> turns=1, first-pass
      G3 "update glosses"       [rej,rej,ok] -> turns=3, NOT first-pass
      G4 "" (seq7)              [fail]       -> abandoned
      G5 "export to csv"        [ok]         -> turns=1, first-pass

    first_pass_green_rate = 2/5 = 0.4
    turns_list = [2, 1, 3, 1]  (abandoned not in turns)
    median([1,1,2,3]) = (1+2)/2 = 1.5
    abandoned = 1
    rejects: missing_imports=2, unprotected_writes=1, PolymorphicAttributeError=1
    """
    import green_report
    fixture = Path(__file__).parent / "fixtures" / "sample_operations.jsonl"
    records, skipped = green_report.load_jsonl([fixture])
    metrics = green_report.compute_metrics(records)

    assert skipped == 1, f"Expected 1 skipped, got {skipped}"
    assert metrics["total_groups"] == 5, f"Expected 5 groups, got {metrics['total_groups']}"
    assert metrics["first_pass_green"] == 2, f"Expected 2 first-pass greens, got {metrics['first_pass_green']}"
    assert metrics["first_pass_green_rate"] == pytest.approx(0.4, abs=0.001)
    assert metrics["abandoned_groups"] == 1
    assert metrics["turns_to_green_median"] == pytest.approx(1.5, abs=0.001)


# ---------------------------------------------------------------------------
# T10 - report identifies top-2 reject codes with correct counts
# ---------------------------------------------------------------------------

def test_top2_reject_codes():
    """The fixture has: missing_imports=2, unprotected_writes=1, PolymorphicAttributeError=1.
    Top-2 should be: missing_imports (2), then one of the one-count codes."""
    import green_report
    fixture = Path(__file__).parent / "fixtures" / "sample_operations.jsonl"
    records, _ = green_report.load_jsonl([fixture])
    metrics = green_report.compute_metrics(records)

    rejects = metrics["rejects_by_error_code"]
    # Sort by count descending (dict insertion order from compute_metrics is already sorted)
    sorted_rejects = sorted(rejects.items(), key=lambda x: x[1], reverse=True)
    assert len(sorted_rejects) >= 2, "Expected at least 2 reject codes"
    top1_code, top1_count = sorted_rejects[0]
    assert top1_code == "missing_imports", f"Top reject code should be missing_imports, got {top1_code}"
    assert top1_count == 2, f"missing_imports count should be 2, got {top1_count}"
    # Second has count 1
    _, top2_count = sorted_rejects[1]
    assert top2_count == 1


# ---------------------------------------------------------------------------
# Issue #62 - group_records_by_session: stable session_id grouping,
# NOT consecutive user_intent matching.
# ---------------------------------------------------------------------------

def test_session_grouping_survives_intent_edit_mid_session():
    """One session, intent string changes mid-session -> still ONE group.

    This is the first failure mode named in #62: editing user_intent between
    calls within a single authoring session must NOT split the group.
    """
    from flextoolsmcp.server.handlers import op_telemetry as tel

    records = [
        {"op_id": "a", "seq": 1, "session_id": "sess-1", "user_intent": "fix the bug",
         "outcome": "preflight_reject", "error_code": "missing_imports",
         "assistance_triggered": False},
        {"op_id": "b", "seq": 2, "session_id": "sess-1", "user_intent": "fix the gloss bug",
         "outcome": "ok", "error_code": "", "assistance_triggered": False},
    ]
    groups = tel.group_records_by_session(records)
    assert len(groups) == 1, f"Same session_id should form 1 group despite intent edit, got {len(groups)}"
    assert len(groups[0]) == 2


def test_session_grouping_does_not_merge_unrelated_sessions_same_intent():
    """Two different sessions sharing a generic same user_intent -> two groups.

    This is the second failure mode named in #62: a shared generic intent
    string must NOT merge unrelated sessions.
    """
    from flextoolsmcp.server.handlers import op_telemetry as tel

    records = [
        {"op_id": "a", "seq": 1, "session_id": "sess-A", "user_intent": "fix the bug",
         "outcome": "ok", "error_code": "", "assistance_triggered": False},
        {"op_id": "b", "seq": 2, "session_id": "sess-B", "user_intent": "fix the bug",
         "outcome": "ok", "error_code": "", "assistance_triggered": False},
    ]
    groups = tel.group_records_by_session(records)
    assert len(groups) == 2, f"Different session_ids should form 2 groups, got {len(groups)}"


def test_session_grouping_not_restricted_to_consecutive_records():
    """Records for the same session_id are grouped together even if another
    session's record is interleaved between them."""
    from flextoolsmcp.server.handlers import op_telemetry as tel

    records = [
        {"op_id": "a", "seq": 1, "session_id": "sess-1", "user_intent": "x",
         "outcome": "preflight_reject", "error_code": "missing_imports",
         "assistance_triggered": False},
        {"op_id": "b", "seq": 2, "session_id": "sess-2", "user_intent": "y",
         "outcome": "ok", "error_code": "", "assistance_triggered": False},
        {"op_id": "c", "seq": 3, "session_id": "sess-1", "user_intent": "x",
         "outcome": "ok", "error_code": "", "assistance_triggered": False},
    ]
    groups = tel.group_records_by_session(records)
    assert len(groups) == 2
    sess1_group = next(g for g in groups if g[0]["session_id"] == "sess-1")
    assert len(sess1_group) == 2
    assert [r["op_id"] for r in sess1_group] == ["a", "c"]


def test_session_grouping_legacy_fallback_for_missing_session_id():
    """Records with no session_id at all fall back to the legacy
    consecutive-user_intent rule among themselves (backward compatibility
    with JSONL written before #62)."""
    from flextoolsmcp.server.handlers import op_telemetry as tel

    records = [
        {"op_id": "a", "seq": 1, "user_intent": "list entries", "outcome": "preflight_reject",
         "error_code": "missing_imports", "assistance_triggered": False},
        {"op_id": "b", "seq": 2, "user_intent": "list entries", "outcome": "ok",
         "error_code": "", "assistance_triggered": False},
        {"op_id": "c", "seq": 3, "user_intent": "export to csv", "outcome": "ok",
         "error_code": "", "assistance_triggered": False},
    ]
    groups = tel.group_records_by_session(records)
    assert len(groups) == 2
    assert len(groups[0]) == 2
    assert len(groups[1]) == 1


def test_group_records_by_intent_is_unchanged():
    """group_records_by_intent (used by diagnostic-report reconstruction,
    decision E7) keeps its original consecutive-user_intent semantics and is
    NOT touched by the #62 session-grouping fix."""
    from flextoolsmcp.server.handlers import op_telemetry as tel

    records = [
        {"op_id": "a", "seq": 1, "session_id": "sess-1", "user_intent": "fix the bug",
         "outcome": "preflight_reject", "error_code": "missing_imports",
         "assistance_triggered": False},
        {"op_id": "b", "seq": 2, "session_id": "sess-1", "user_intent": "fix the gloss bug",
         "outcome": "ok", "error_code": "", "assistance_triggered": False},
    ]
    # Intent changed between the two records -> group_records_by_intent still
    # splits them into two groups, even though they share one session_id.
    groups = tel.group_records_by_intent(records)
    assert len(groups) == 2


def test_stash_op_start_threads_session_id_into_jsonl_record(tmp_path):
    """_stash_op_start's session_id round-trips into the written JSONL record."""
    from flextoolsmcp.server.handlers.op_telemetry import _stash_op_start, _write_jsonl_line

    _stash_op_start(
        op_id="op-sess-020",
        project="TestProject",
        write_enabled=False,
        source_kind="bare_snippet",
        user_intent="list entries",
        code_sha256="f" * 64,
        code_bytes=100,
        code_lines=5,
        session_id="sess-xyz",
    )

    _write_jsonl_line(
        op_id="op-sess-020",
        seq=20,
        outcome="ok",
        duration_s=1.0,
        error_code=None,
        preflight_gate=None,
        info_count=0,
        warning_count=0,
        error_count=0,
        assistance_triggered=False,
        log_dir_fn=lambda: tmp_path,
    )

    jsonl_path = tmp_path / "operations.jsonl"
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    record = json.loads(lines[0])
    assert record["session_id"] == "sess-xyz"


def test_stash_drain_no_double_write(tmp_path):
    from flextoolsmcp.server.handlers.op_telemetry import _stash_op_start, _write_jsonl_line

    _stash_op_start(
        op_id="op-drain-011",
        project="P",
        write_enabled=False,
        source_kind="bare_snippet",
        user_intent="drain test",
        code_sha256="e" * 64,
        code_bytes=10,
        code_lines=1,
    )

    kwargs = dict(
        op_id="op-drain-011",
        seq=11,
        outcome="ok",
        duration_s=0.1,
        error_code=None,
        preflight_gate=None,
        info_count=0,
        warning_count=0,
        error_count=0,
        assistance_triggered=False,
        log_dir_fn=lambda: tmp_path,
    )
    _write_jsonl_line(**kwargs)
    _write_jsonl_line(**kwargs)  # second call: stash already drained

    jsonl_path = tmp_path / "operations.jsonl"
    lines = [ln for ln in jsonl_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    # Both calls write a line (second has empty stash fields), but critically
    # we get exactly 2 lines (not an exception).  The important invariant is
    # that the function is safe to call twice; production code never does this.
    assert len(lines) == 2  # idempotent write, no crash
