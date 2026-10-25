"""P2: retry-loop assistance for run_module subprocess wrapper failures (#28).

PR #429 wires timeouts and result-marker infra keys; this pins the outer
``except Exception`` path around subprocess launch (still missing on main).
"""

from datetime import datetime, timedelta

from flextoolsmcp.server.session import SessionState, _ASSISTANCE_HINTS_BY_ERROR_CODE

_GENERIC_FALLBACK_SNIPPET = "flextools_find_examples"


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


def test_subprocess_execution_error_hint_is_registered():
    hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["subprocess_execution_error"]
    assert hint.strip()
    assert "traceback" in hint or "stderr" in hint


def test_subprocess_execution_error_loop_avoids_generic_find_examples_fallback():
    message = _loop_message("subprocess_execution_error")
    assert "subprocess_execution_error" in message
    assert _GENERIC_FALLBACK_SNIPPET not in message
