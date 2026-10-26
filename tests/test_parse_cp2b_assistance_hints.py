"""P2: tailored retry-loop assistance for parser CP2b refusal codes (#28).

docs/PARSER-GUIDE.md documents remedies for parse_morph_unresolved,
parse_run_not_found, and parse_job_cancelled; issue #28's loop detector
should surface them instead of the generic find_examples fallback.
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


class TestParseCp2bAssistanceHints:
    @staticmethod
    def _codes():
        return (
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

    def test_morph_unresolved_mentions_candidates(self):
        hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["parse_morph_unresolved"]
        assert "candidates" in hint

    def test_run_not_found_mentions_available_runs(self):
        hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["parse_run_not_found"]
        assert "available_runs" in hint

    def test_job_cancelled_mentions_parse_log(self):
        hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["parse_job_cancelled"]
        assert "flextools_parse_log" in hint
