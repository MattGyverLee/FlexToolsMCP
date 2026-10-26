"""P2: tailored retry-loop assistance for parser infrastructure error codes (#28).

docs/PARSER-GUIDE.md documents remedies for these codes; issue #28's loop
detector should surface them instead of the generic find_examples fallback.
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


class TestParserAssistanceHintsPresent:
    @staticmethod
    def _codes():
        return (
            "parser_engine_mismatch",
            "parser_core_missing",
            "parser_agent_missing",
            "parser_tool_missing",
            "parse_scope_empty",
            "parse_scope_ambiguous",
            "parse_scope_mismatch",
            "parser_filing_in_progress",
            "grammar_load_unclean",
            "parser_timeout",
            "parser_job_failed",
            "parser_config_failed",
            "parse_sandbox_refused",
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

    def test_engine_mismatch_mentions_hermitcrab(self):
        hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["parser_engine_mismatch"]
        assert "HermitCrab" in hint
