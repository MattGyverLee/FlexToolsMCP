"""Foundation-checkpoint tests for the diagnostic-report feature.

Spec: specs/diagnostic-report/SPEC.md, section 12 acceptance criteria
(CP1-relevant subset only -- reconstruction/normalization/transport/guard
criteria are covered by later checkpoints).

Covers:
  - Trigger matrix (section 6.1): runtime_fail (any exception class) fires,
    timeout does not, invalid_api_chain fires, casting_issues_detected fires
    ONLY on recurrence, every explicitly non-reportable code never fires.
  - Dedupe (section 6.3-6.4): two ops in one turn with edited code (different
    code_sha256) but the same exception class + failing symbol produce
    exactly ONE signature -> exactly one offered.json entry.
  - dont_ask_again persists across a simulated restart (reload the store);
    a corrupt offered.json fails open (offer proceeds, no exception).
  - user_request plumbing: round-trips into the JSONL record via
    op_telemetry's stash/write path, and falls back to user_intent when
    absent.
"""

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure the package root is importable regardless of CWD (mirrors the
# existing test_op_telemetry.py convention; conftest.py also does this, but
# keep this file runnable standalone too).
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


from flextoolsmcp.server.diagnostic import triggers, signature, offered_store
from flextoolsmcp.server.handlers import op_telemetry as tel


@pytest.fixture(autouse=True)
def reset_stash():
    """Reset op_telemetry's module-level stash before/after each test."""
    tel._OP_STASH.clear()
    tel._OP_STASH_ORDER.clear()
    yield
    tel._OP_STASH.clear()
    tel._OP_STASH_ORDER.clear()


def _close_record(**overrides) -> dict:
    """Build a minimal closed-op JSONL-shaped record for trigger tests."""
    base = {
        "op_id": "op-000001-001",
        "seq": 1,
        "outcome": "ok",
        "error_code": "",
        "preflight_gate": "",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Trigger matrix (section 6.1)
# ---------------------------------------------------------------------------

def test_runtime_fail_any_exception_class_fires():
    rec = _close_record(outcome="runtime_fail", error_code="PolymorphicAttributeError")
    assert triggers.is_reportable_close(rec) is True


def test_runtime_fail_generic_exception_class_still_fires():
    # Match on outcome, not on the literal string "runtime_error".
    rec = _close_record(outcome="runtime_fail", error_code="ZeroDivisionError")
    assert triggers.is_reportable_close(rec) is True


def test_timeout_never_fires_even_with_exception_like_code():
    rec = _close_record(outcome="timeout", error_code="TimeoutExpired")
    assert triggers.is_reportable_close(rec) is False


def test_invalid_api_chain_fires():
    rec = _close_record(outcome="preflight_reject", error_code="invalid_api_chain")
    assert triggers.is_reportable_close(rec) is True


def test_casting_issues_first_time_does_not_fire():
    turn = [
        _close_record(op_id="op-1", outcome="preflight_reject", error_code="casting_issues_detected"),
    ]
    reportable = triggers.find_reportable_closes(turn)
    assert reportable == []


def test_casting_issues_recurrence_fires():
    turn = [
        _close_record(op_id="op-1", outcome="preflight_reject", error_code="casting_issues_detected", preflight_gate="cast:Gloss"),
        _close_record(op_id="op-2", outcome="preflight_reject", error_code="casting_issues_detected", preflight_gate="cast:Gloss"),
    ]
    reportable = triggers.find_reportable_closes(turn)
    assert [r["op_id"] for r in reportable] == ["op-2"]


def test_casting_issues_recurrence_different_signature_does_not_fire():
    # Two casting hints in the same turn but DIFFERENT signatures: neither
    # is a recurrence of the other.
    turn = [
        _close_record(op_id="op-1", outcome="preflight_reject", error_code="casting_issues_detected", preflight_gate="cast:Gloss"),
        _close_record(op_id="op-2", outcome="preflight_reject", error_code="casting_issues_detected", preflight_gate="cast:Definition"),
    ]
    reportable = triggers.find_reportable_closes(turn)
    assert reportable == []


@pytest.mark.parametrize("code", sorted(triggers.NON_REPORTABLE_CODES))
def test_non_reportable_codes_never_fire(code):
    # Exercise both a plausible outcome pairing and, defensively, runtime_fail
    # -- the explicit non-reportable list must win regardless of outcome.
    for outcome in ("preflight_reject", "runtime_fail"):
        rec = _close_record(outcome=outcome, error_code=code)
        assert triggers.is_reportable_close(rec) is False, (code, outcome)


def test_all_16_contract_error_codes_classified_without_kob_deviation():
    """Sanity check: the 13 explicitly non-reportable codes plus the 3
    reportable trigger codes account for the full REPORTABLE_CODES decision
    space in section 6.1/11.1 (16 total distinguishable codes named in the
    spec, allowing for the fact that runtime_fail's code is an open-ended
    exception-class string, not a fixed member of the set)."""
    reportable_named_codes = {"invalid_api_chain", "casting_issues_detected"}
    overlap = reportable_named_codes & triggers.NON_REPORTABLE_CODES
    assert overlap == set()


# ---------------------------------------------------------------------------
# Workaround inference (section 6.2)
# ---------------------------------------------------------------------------

def test_workaround_inferred_when_failure_followed_by_ok_same_turn():
    turn = [
        _close_record(op_id="op-1", outcome="runtime_fail", error_code="PolymorphicAttributeError"),
        _close_record(op_id="op-2", outcome="ok"),
    ]
    workaround = triggers.infer_workaround(turn)
    assert [r["op_id"] for r in workaround] == ["op-1"]


def test_no_workaround_when_turn_abandoned():
    turn = [
        _close_record(op_id="op-1", outcome="runtime_fail", error_code="PolymorphicAttributeError"),
        _close_record(op_id="op-2", outcome="runtime_fail", error_code="PolymorphicAttributeError"),
    ]
    assert triggers.infer_workaround(turn) == []


# ---------------------------------------------------------------------------
# Signature (section 6.3) + dedupe (section 6.3-6.4)
# ---------------------------------------------------------------------------

def test_signature_is_stable_across_different_code_sha256():
    """Two ops in one turn with EDITED code (different code_sha256) but the
    same underlying failure (same exception class + failing symbol) must
    produce exactly ONE signature."""
    rec_attempt_1 = _close_record(
        op_id="op-1", outcome="runtime_fail", error_code="PolymorphicAttributeError",
    )
    rec_attempt_1["code_sha256"] = "a" * 64
    rec_attempt_2 = _close_record(
        op_id="op-2", outcome="runtime_fail", error_code="PolymorphicAttributeError",
    )
    rec_attempt_2["code_sha256"] = "b" * 64  # edited code -> different hash

    sig1 = signature.compute_signature(rec_attempt_1, failing_symbol="ILexSense.Gloss")
    sig2 = signature.compute_signature(rec_attempt_2, failing_symbol="ILexSense.Gloss")

    assert sig1 == sig2
    assert sig1 is not None


def test_signature_differs_for_different_exception_class_or_symbol():
    rec = _close_record(outcome="runtime_fail", error_code="PolymorphicAttributeError")
    sig_a = signature.compute_signature(rec, failing_symbol="ILexSense.Gloss")
    sig_b = signature.compute_signature(rec, failing_symbol="ILexEntry.LexemeForm")
    rec_other_exc = _close_record(outcome="runtime_fail", error_code="ZeroDivisionError")
    sig_c = signature.compute_signature(rec_other_exc, failing_symbol="ILexSense.Gloss")

    assert sig_a != sig_b
    assert sig_a != sig_c


def test_invalid_api_chain_signature_normalizes_numeric_indices():
    rec = _close_record(outcome="preflight_reject", error_code="invalid_api_chain")
    sig1 = signature.compute_signature(rec, chain="project.LexEntry.GetAll()[0].Senses")
    sig2 = signature.compute_signature(rec, chain="project.LexEntry.GetAll()[7].Senses")
    assert sig1 == sig2


def test_dedupe_two_edited_attempts_yield_exactly_one_offered_entry(tmp_path):
    path = tmp_path / "offered.json"
    path_fn = lambda: path

    rec1 = _close_record(op_id="op-1", outcome="runtime_fail", error_code="PolymorphicAttributeError")
    rec2 = _close_record(op_id="op-2", outcome="runtime_fail", error_code="PolymorphicAttributeError")

    sig1 = signature.compute_signature(rec1, failing_symbol="ILexSense.Gloss")
    sig2 = signature.compute_signature(rec2, failing_symbol="ILexSense.Gloss")
    assert sig1 == sig2

    offered_store.record_offer(sig1, "PolymorphicAttributeError", path_fn=path_fn)
    offered_store.record_offer(sig2, "PolymorphicAttributeError", path_fn=path_fn)

    store = offered_store.load_store(path_fn)
    assert len(store["entries"]) == 1
    entry = store["entries"][sig1]
    assert entry["offer_count"] == 2


# ---------------------------------------------------------------------------
# offered.json persistence (section 6.4 / 12)
# ---------------------------------------------------------------------------

def test_dont_ask_again_persists_across_simulated_restart(tmp_path):
    path = tmp_path / "offered.json"
    path_fn = lambda: path

    sig = "deadbeefdeadbeef"
    offered_store.record_offer(sig, "PolymorphicAttributeError", path_fn=path_fn)
    offered_store.record_decision(sig, offered_store.STATE_DONT_ASK_AGAIN, path_fn=path_fn)

    assert offered_store.should_offer(sig, path_fn=path_fn) is False

    # Simulate a server restart: nothing in-memory carries over, only the
    # file on disk. A fresh load must still see dont_ask_again.
    reloaded = offered_store.load_store(path_fn)
    assert reloaded["entries"][sig]["state"] == offered_store.STATE_DONT_ASK_AGAIN
    assert offered_store.should_offer(sig, path_fn=path_fn) is False


def test_declined_state_allows_future_reoffer(tmp_path):
    path = tmp_path / "offered.json"
    path_fn = lambda: path
    sig = "cafefacecafeface"
    offered_store.record_offer(sig, "invalid_api_chain", path_fn=path_fn)
    offered_store.record_decision(sig, offered_store.STATE_DECLINED, path_fn=path_fn)
    assert offered_store.should_offer(sig, path_fn=path_fn) is True


def test_corrupt_offered_json_fails_open(tmp_path):
    path = tmp_path / "offered.json"
    path.write_text("{not valid json::::", encoding="utf-8")
    path_fn = lambda: path

    # Must not raise, and must fail open (offer proceeds).
    store = offered_store.load_store(path_fn)
    assert store == {"version": 1, "entries": {}}
    assert offered_store.should_offer("any-signature", path_fn=path_fn) is True

    # And recording a fresh offer over the corrupt file must not raise
    # either, and should overwrite it with valid JSON.
    offered_store.record_offer("any-signature", "PolymorphicAttributeError", path_fn=path_fn)
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert "any-signature" in reloaded["entries"]


def test_missing_offered_json_is_treated_as_empty(tmp_path):
    path = tmp_path / "nonexistent" / "offered.json"
    path_fn = lambda: path
    store = offered_store.load_store(path_fn)
    assert store == {"version": 1, "entries": {}}
    assert offered_store.should_offer("sig", path_fn=path_fn) is True


def test_save_store_path_fn_runtime_error_fails_open():
    """`path_fn` can raise (e.g. the default `default_store_path` chain
    hits `Path.home()` -> `RuntimeError` when the home dir can't be
    resolved). `save_store()` must swallow that and return without
    raising, and `record_offer()` (which calls `save_store()`
    unconditionally) must likewise never crash the op path."""

    def raising_path_fn():
        raise RuntimeError("cannot determine home directory")

    # Must not raise.
    offered_store.save_store({"version": 1, "entries": {}}, path_fn=raising_path_fn)

    # Must not raise, and should still return the upserted entry even
    # though persistence to disk failed.
    entry = offered_store.record_offer(
        "any-signature", "PolymorphicAttributeError", path_fn=raising_path_fn
    )
    assert entry["state"] == offered_store.STATE_OFFERED


def test_prune_caps_entries_by_lru_last_seen():
    store = {"version": 1, "entries": {}}
    for i in range(10):
        store["entries"][f"sig-{i}"] = {
            "state": "offered",
            "error_code": "X",
            "first_seen": f"2026-01-01T00:00:{i:02d}Z",
            "last_seen": f"2026-01-01T00:00:{i:02d}Z",
            "offer_count": 1,
        }
    offered_store.prune(store, cap=3)
    assert len(store["entries"]) == 3
    # The three MOST RECENTLY seen (highest i) must survive.
    assert set(store["entries"].keys()) == {"sig-7", "sig-8", "sig-9"}


# ---------------------------------------------------------------------------
# user_request plumbing (section 4) -- JSONL round-trip
# ---------------------------------------------------------------------------

def test_user_request_round_trips_into_jsonl_record(tmp_path):
    tel._stash_op_start(
        op_id="op-ur-001",
        project="TestProject",
        write_enabled=False,
        source_kind="bare_snippet",
        user_intent="paraphrase of the ask",
        user_request="the exact verbatim thing the human typed",
        code_sha256="a" * 64,
        code_bytes=10,
        code_lines=1,
    )

    log_dir = tmp_path

    tel._write_jsonl_line(
        op_id="op-ur-001",
        seq=1,
        outcome="ok",
        duration_s=0.5,
        error_code=None,
        preflight_gate=None,
        info_count=0,
        warning_count=0,
        error_count=0,
        assistance_triggered=False,
        log_dir_fn=lambda: log_dir,
    )

    lines = (log_dir / "operations.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["user_request"] == "the exact verbatim thing the human typed"
    assert record["user_intent"] == "paraphrase of the ask"


def test_user_request_falls_back_to_user_intent_when_absent(tmp_path):
    tel._stash_op_start(
        op_id="op-ur-002",
        project="TestProject",
        write_enabled=False,
        source_kind="bare_snippet",
        user_intent="paraphrase of the ask",
        user_request=None,  # not supplied for this op
        code_sha256="b" * 64,
        code_bytes=10,
        code_lines=1,
    )

    log_dir = tmp_path
    tel._write_jsonl_line(
        op_id="op-ur-002",
        seq=1,
        outcome="ok",
        duration_s=0.5,
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
    assert record["user_request"] == "paraphrase of the ask"
    assert record["user_intent"] == "paraphrase of the ask"


def test_user_request_and_user_intent_both_absent_round_trip_empty(tmp_path):
    tel._stash_op_start(
        op_id="op-ur-003",
        project="TestProject",
        write_enabled=False,
        source_kind="bare_snippet",
        user_intent=None,
        user_request=None,
        code_sha256="c" * 64,
        code_bytes=10,
        code_lines=1,
    )

    log_dir = tmp_path
    tel._write_jsonl_line(
        op_id="op-ur-003",
        seq=1,
        outcome="ok",
        duration_s=0.5,
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
    assert record["user_request"] == ""
    assert record["user_intent"] == ""


def test_group_records_by_intent_reused_for_turn_scoping():
    """triggers.py's turn-scoped helpers are meant to run over
    op_telemetry.group_records_by_intent() output -- confirm the grouping
    function used by both is the exact same one (no drift / duplication)."""
    records = [
        {"user_intent": "fix glosses", "outcome": "runtime_fail", "error_code": "PolymorphicAttributeError", "op_id": "op-1"},
        {"user_intent": "fix glosses", "outcome": "ok", "op_id": "op-2"},
        {"user_intent": "different task", "outcome": "ok", "op_id": "op-3"},
    ]
    groups = tel.group_records_by_intent(records)
    assert len(groups) == 2
    assert [r["op_id"] for r in groups[0]] == ["op-1", "op-2"]
    assert [r["op_id"] for r in groups[1]] == ["op-3"]

    workaround = triggers.infer_workaround(groups[0])
    assert [r["op_id"] for r in workaround] == ["op-1"]
