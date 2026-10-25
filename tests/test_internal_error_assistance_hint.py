"""P2 (#28 / #89): tailored retry-loop assistance for internal_error."""

from datetime import datetime, timedelta

from flextoolsmcp.server.session import SessionState, _ASSISTANCE_HINTS_BY_ERROR_CODE


def test_internal_error_hint_is_registered():
    hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["internal_error"]
    assert "flextools_health" in hint
    assert "traceback" in hint
    assert "resubmit" in hint.lower()


def test_same_error_loop_uses_internal_error_hint():
    state = SessionState()
    base = datetime.now()
    for i in range(5):
        state.record_op_signal(
            error_code="internal_error",
            code_size_bytes=100,
            timestamp=base + timedelta(seconds=i * 10),
        )
    pattern = state.detect_retry_loop_pattern()
    assert pattern is not None
    assert pattern["pattern_detected"] == "same_error_retry_loop"
    assert pattern["error_code"] == "internal_error"
    assert "flextools_health" in pattern["message"]
