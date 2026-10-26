"""P2: tailored retry-loop assistance for sandbox_unavailable (#28, #322).

When the same sandbox_unavailable fires five times in a window, the assistance
message must steer at install/repair (hcparse.ps1), not the generic
flextools_find_examples fallback.
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


def test_sandbox_unavailable_hint_is_registered():
    hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["sandbox_unavailable"]
    assert "hcparse" in hint
    assert "flextools_health" in hint


def test_sandbox_unavailable_loop_steers_to_install_not_find_examples():
    message = _loop_message("sandbox_unavailable")
    assert "sandbox_unavailable" in message
    assert "hcparse" in message or "install" in message
    assert "flextools_find_examples" not in message
    assert "flextools_health" in message
