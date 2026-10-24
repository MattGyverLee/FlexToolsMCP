"""P2: tailored retry-loop assistance for runtime_error (#28).

When the same runtime_error fires five times in a window, the assistance
message must steer the model at the payload's error/stderr/messages, not
the generic flextools_find_examples fallback.
"""

from datetime import datetime, timedelta

from flextoolsmcp.server.session import SessionState, _ASSISTANCE_HINTS_BY_ERROR_CODE


def _loop_message(error_code: str) -> str:
    state = SessionState()
    base = datetime.now()
    for i in range(5):
        state.record_op_signal(
            error_code=error_code,
            code_size_bytes=400,
            timestamp=base + timedelta(seconds=i * 10),
        )
    pattern = state.detect_retry_loop_pattern()
    assert pattern is not None
    return pattern["message"]


def test_runtime_error_hint_is_registered():
    hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["runtime_error"]
    assert "stderr" in hint
    assert "flextools_prepare_report" in hint


def test_runtime_error_loop_steers_to_payload_not_find_examples():
    message = _loop_message("runtime_error")
    assert "runtime_error" in message
    assert "stderr" in message or "messages" in message
    assert "flextools_find_examples" not in message
    assert "flextools_prepare_report" in message
