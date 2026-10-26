"""P2: tailored retry-loop assistance for project/chain error codes (#28).

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


class TestProjectAssistanceHintsPresent:
    @staticmethod
    def _codes():
        return (
            "invalid_api_chain",
            "project_not_found",
            "project_drive_unavailable",
            "project_path_mismatch",
        )

    def test_each_code_has_a_map_entry(self):
        for code in self._codes():
            assert code in _ASSISTANCE_HINTS_BY_ERROR_CODE, code

    def test_loop_messages_use_tailored_hints_not_generic_fallback(self):
        generic = "flextools_find_examples"
        for code in self._codes():
            msg = _loop_message(code)
            assert code in msg
            assert generic not in msg, (code, msg)


class TestProjectAssistanceHintContent:
    def test_invalid_api_chain_points_at_issues_and_access_path(self):
        hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["invalid_api_chain"]
        assert "issues" in hint
        assert "access_path" in hint

    def test_project_not_found_points_at_available_projects(self):
        hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["project_not_found"]
        assert "available_projects" in hint
        assert "flextools_start" in hint

    def test_project_drive_unavailable_is_environment_not_code(self):
        hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["project_drive_unavailable"]
        assert "attempted_path" in hint
        assert "environment fix" in hint
        assert "reconnect" in hint

    def test_project_path_mismatch_names_both_paths(self):
        hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["project_path_mismatch"]
        assert "discovered_at" in hint
        assert "attempted_path" in hint
