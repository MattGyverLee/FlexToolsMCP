"""Tests for issue #28 -- detect retry loops and code-size oscillation;
surface _assistance hint on the rejection that completes the pattern.

Two patterns must trigger:

1. same_error_retry_loop:
   5 consecutive ops with identical error_code within a 5-minute window.
   (4 prior + the current op == 5 in the deque.)

2. size_oscillation:
   5 consecutive failing ops whose code_size deltas alternate sign
   (up/down/up/down or down/up/down/up).

A success in between must reset the detector.
"""
from datetime import datetime, timedelta



def _new_state():
    """Fresh SessionState for each test (don't pollute the singleton)."""
    from server.session import SessionState
    return SessionState()


def test_same_error_4_prior_plus_current_triggers():
    """4 prior + current op all == 'casting_issues_detected' within 5min
    => 5th rejection carries _assistance.pattern_detected = same_error_retry_loop."""
    state = _new_state()
    base = datetime.now()

    # 4 prior failures (i = 0..3) and the "current" failure (i = 4)
    for i in range(5):
        state.record_op_signal(
            error_code="casting_issues_detected",
            code_size_bytes=200 + i * 10,  # increasing, NOT oscillating
            timestamp=base + timedelta(seconds=i * 30),
        )

    pattern = state.detect_retry_loop_pattern()
    assert pattern is not None, "5 same-error ops should trigger the detector"
    assert pattern["pattern_detected"] == "same_error_retry_loop"
    assert pattern["error_code"] == "casting_issues_detected"
    # Issue #28 follow-up: hint now points at the #21 inlined rewrite as
    # the primary fix path; resolve_property is the fallback for chained
    # receivers. Both substrings must appear.
    assert "rewrite" in pattern["message"], (
        "casting_issues_detected hint should mention the inlined rewrite; "
        f"got: {pattern['message']!r}"
    )
    assert "resolve_property" in pattern["message"], (
        "casting_issues_detected hint should still mention resolve_property "
        f"as the fallback for chained receivers; got: {pattern['message']!r}"
    )


def test_same_error_outside_window_does_not_trigger():
    """5 same-error ops spread over > 5min should NOT fire the loop detector."""
    state = _new_state()
    base = datetime.now()
    # Spread 5 ops over 10 minutes (well past the 5-minute window).
    for i in range(5):
        state.record_op_signal(
            error_code="casting_issues_detected",
            code_size_bytes=200,
            timestamp=base + timedelta(minutes=i * 3),  # 0, 3, 6, 9, 12 mins
        )
    assert state.detect_retry_loop_pattern() is None


def test_under_5_signals_does_not_trigger():
    """Fewer than 5 signals can't trigger the loop detector."""
    state = _new_state()
    base = datetime.now()
    for i in range(4):
        state.record_op_signal(
            error_code="casting_issues_detected",
            code_size_bytes=200,
            timestamp=base + timedelta(seconds=i),
        )
    assert state.detect_retry_loop_pattern() is None


def test_success_resets_detector():
    """A success between failures clears the deque so the loop never fires."""
    state = _new_state()
    base = datetime.now()
    for i in range(4):
        state.record_op_signal(
            error_code="undiscovered_entity",
            code_size_bytes=300,
            timestamp=base + timedelta(seconds=i * 30),
        )
    # Success resets
    state.reset_op_signals()
    # Now record one more failure -- only 1 in the deque, no pattern
    state.record_op_signal(
        error_code="undiscovered_entity",
        code_size_bytes=300,
        timestamp=base + timedelta(seconds=300),
    )
    assert state.detect_retry_loop_pattern() is None


def test_size_oscillation_pattern_triggers():
    """5 consecutive failing ops with sizes that alternate up/down/up/down
    should trigger size_oscillation (deltas signs == [+,-,+,-])."""
    state = _new_state()
    base = datetime.now()
    sizes = [100, 200, 100, 200, 100]  # deltas: +100, -100, +100, -100
    # Use DIFFERENT error codes so the same_error path can't grab it first
    error_codes = ["err_a", "err_b", "err_a", "err_b", "err_a"]
    for i, (sz, ec) in enumerate(zip(sizes, error_codes)):
        state.record_op_signal(
            error_code=ec,
            code_size_bytes=sz,
            timestamp=base + timedelta(seconds=i * 10),
        )
    pattern = state.detect_retry_loop_pattern()
    assert pattern is not None
    assert pattern["pattern_detected"] == "size_oscillation"
    assert pattern["code_sizes"] == sizes


def test_undiscovered_entity_hint_is_tailored():
    """The assistance message for undiscovered_entity should mention
    flextools_get_object_api -- the correct discovery tool for that error."""
    state = _new_state()
    base = datetime.now()
    for i in range(5):
        state.record_op_signal(
            error_code="undiscovered_entity",
            code_size_bytes=400,
            timestamp=base + timedelta(seconds=i * 20),
        )
    pattern = state.detect_retry_loop_pattern()
    assert pattern is not None
    assert "get_object_api" in pattern["message"]


def test_project_not_open_hint_points_to_list_projects():
    """project_not_open hint should mention list_projects."""
    state = _new_state()
    base = datetime.now()
    for i in range(5):
        state.record_op_signal(
            error_code="project_not_open",
            code_size_bytes=100,
            timestamp=base + timedelta(seconds=i * 10),
        )
    pattern = state.detect_retry_loop_pattern()
    assert pattern is not None
    assert "list_projects" in pattern["message"]


def test_attach_assistance_injects_into_response():
    """Once the detector fires, _attach_assistance_if_loop must mutate the
    response JSON to include _assistance.pattern_detected."""
    # We need the real handler module + a controllable session_state.
    import json
    from server.handlers import execution as exec_mod
    from server.session import SessionState

    # Temporarily swap session_state with a fresh instance for the test.
    original = exec_mod.session_state
    exec_mod.session_state = SessionState()
    try:
        # Pre-load 4 prior failures
        base = datetime.now()
        for i in range(4):
            exec_mod.session_state.record_op_signal(
                error_code="casting_issues_detected",
                code_size_bytes=250,
                timestamp=base + timedelta(seconds=i * 30),
            )
        # Build a stand-in response (dict-bearing list -- the unit-test
        # path of error_response when MCP TextContent isn't available).
        from response_utils import error_response
        resp = error_response(
            "casting_issues_detected",
            "Found 1 polymorphic property access issue.",
            issues=["fake"],
        )
        # 5th failure happens via _attach_assistance_if_loop
        result = exec_mod._attach_assistance_if_loop(
            resp,
            error_code="casting_issues_detected",
            code_size_bytes=260,
        )
        # Pull the JSON back out
        text = result[0].text if hasattr(result[0], "text") else result[0]["text"]
        data = json.loads(text)
        assert "_assistance" in data, (
            f"5th consecutive casting failure should carry _assistance; "
            f"got payload: {data!r}"
        )
        assert data["_assistance"]["pattern_detected"] == "same_error_retry_loop"
        assert data["_assistance"]["error_code"] == "casting_issues_detected"
    finally:
        exec_mod.session_state = original


def test_attach_assistance_passthrough_when_no_pattern():
    """When the detector doesn't fire (e.g., only 1 failure in the deque),
    the response must come back unchanged -- no _assistance key."""
    import json
    from server.handlers import execution as exec_mod
    from server.session import SessionState

    original = exec_mod.session_state
    exec_mod.session_state = SessionState()
    try:
        from response_utils import error_response
        resp = error_response("syntax_error", "Bad syntax")
        result = exec_mod._attach_assistance_if_loop(
            resp,
            error_code="syntax_error",
            code_size_bytes=50,
        )
        text = result[0].text if hasattr(result[0], "text") else result[0]["text"]
        data = json.loads(text)
        assert "_assistance" not in data
    finally:
        exec_mod.session_state = original
