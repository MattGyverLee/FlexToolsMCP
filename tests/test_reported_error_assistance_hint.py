"""P2 (#28): tailored retry-loop assistance for run_module ReportedError."""

from datetime import datetime, timedelta

from flextoolsmcp.server.session import SessionState, _ASSISTANCE_HINTS_BY_ERROR_CODE


def test_reported_error_hint_is_registered():
    hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["ReportedError"]
    assert "report.Error" in hint
    assert "Create" in hint or "Add" in hint
    assert "SetGloss" in hint
    assert "summary.error_count" in hint


def test_same_error_loop_uses_reported_error_hint():
    state = SessionState()
    base = datetime.now()
    for i in range(5):
        state.record_op_signal(
            error_code="ReportedError",
            code_size_bytes=200,
            timestamp=base + timedelta(seconds=i * 10),
        )
    pattern = state.detect_retry_loop_pattern()
    assert pattern is not None
    assert pattern["pattern_detected"] == "same_error_retry_loop"
    assert pattern["error_code"] == "ReportedError"
    assert "report.Error" in pattern["message"]
