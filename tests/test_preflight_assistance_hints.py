"""P2: tailored retry-loop assistance for preflight/parse error codes (#28).

When the same error fires five times in a window, session._assistance_message_for_error
must not fall back to the generic find_examples hint for codes whose fix is specific.
"""

from datetime import datetime, timedelta

from flextoolsmcp.server.session import SessionState, _ASSISTANCE_HINTS_BY_ERROR_CODE


def _loop_message(error_code: str) -> str:
    state = SessionState()
    base = datetime.now()
    for i in range(5):
        state.record_op_signal(
            error_code=error_code,
            code_size_bytes=200,
            timestamp=base + timedelta(seconds=i * 10),
        )
    pattern = state.detect_retry_loop_pattern()
    assert pattern is not None
    return pattern["message"]


class TestPreflightAssistanceHintsPresent:
    @staticmethod
    def _codes():
        return (
            "undefined_variables",
            "missing_imports",
            "wrong_library_imports",
            "parse_morph_unresolved",
            "parse_run_not_found",
            "parse_job_cancelled",
        )

    def test_map_has_entries(self):
        for code in self._codes():
            assert code in _ASSISTANCE_HINTS_BY_ERROR_CODE
            assert _ASSISTANCE_HINTS_BY_ERROR_CODE[code].strip()

    def test_loop_detector_uses_tailored_hint_not_generic(self):
        for code in self._codes():
            msg = _loop_message(code)
            assert code in msg
            assert "flextools_find_examples" not in msg

    def test_missing_imports_mentions_flexicon_import(self):
        hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["missing_imports"]
        assert "flexicon import" in hint or "from flexicon import" in hint
