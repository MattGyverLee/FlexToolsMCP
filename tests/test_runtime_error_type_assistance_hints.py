"""P2: tailored retry-loop assistance for run_module runtime error_type keys (#28).

handle_run_module records assistance under execution_result['error_type']
when set. These keys must map in _ASSISTANCE_HINTS_BY_ERROR_CODE or the
fifth identical failure falls back to flextools_find_examples.
"""

from datetime import datetime, timedelta

from flextoolsmcp.server.session import SessionState, _ASSISTANCE_HINTS_BY_ERROR_CODE

_RUNTIME_ERROR_TYPES = (
    "UnknownImportError",
    "AtomicPropertyIterationError",
    "NotIterableError",
    "PolymorphicAttributeError",
    "OverloadResolutionError",
    "ClassIdConstantError",
    "ServiceLookupAttributeError",
    "WrapperInternalError",
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


def test_runtime_error_type_hints_are_registered():
    for code in _RUNTIME_ERROR_TYPES:
        assert code in _ASSISTANCE_HINTS_BY_ERROR_CODE, code
        assert _ASSISTANCE_HINTS_BY_ERROR_CODE[code].strip()


def test_runtime_error_type_loops_avoid_generic_find_examples_fallback():
    for code in _RUNTIME_ERROR_TYPES:
        message = _loop_message(code)
        assert code in message
        assert _GENERIC_FALLBACK_SNIPPET not in message, (
            f"{code} loop should use tailored hint, got: {message!r}"
        )


def test_atomic_property_iteration_runtime_hint_mentions_single_object():
    hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["AtomicPropertyIterationError"]
    assert "OA" in hint or "single-object" in hint
