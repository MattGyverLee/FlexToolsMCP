"""P2: retry-loop assistance for run_module runner infrastructure error_type keys (#28).

PR #426 covers flexicon/runtime classification types; this pins the remaining
subprocess and harness keys (timeouts, result parsing, scan bootstrap,
report.Error demotion) plus the timeout paths that must call
``_attach_assistance_if_loop``.
"""

from datetime import datetime, timedelta

from flextoolsmcp.server.session import SessionState, _ASSISTANCE_HINTS_BY_ERROR_CODE

_RUNNER_INFRA_ERROR_TYPES = (
    "Timeout",
    "TimeoutExpired",
    "JSONDecodeError",
    "NoResultMarker",
    "ReportedError",
    "ProjectOpenError",
    "ScanModuleImportError",
    "ScanFunctionNotFound",
)

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


def test_runner_infra_error_type_hints_are_registered():
    for code in _RUNNER_INFRA_ERROR_TYPES:
        assert code in _ASSISTANCE_HINTS_BY_ERROR_CODE, code
        assert _ASSISTANCE_HINTS_BY_ERROR_CODE[code].strip()


def test_runner_infra_error_type_loops_avoid_generic_find_examples_fallback():
    for code in _RUNNER_INFRA_ERROR_TYPES:
        message = _loop_message(code)
        assert code in message
        assert _GENERIC_FALLBACK_SNIPPET not in message, (
            f"{code} loop should use tailored hint, got: {message!r}"
        )
