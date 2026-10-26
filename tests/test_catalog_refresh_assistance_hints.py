"""Issue #28: tailored retry assistance for catalog + admin error codes."""

from flextoolsmcp.server.session import (
    _ASSISTANCE_HINTS_BY_ERROR_CODE,
    _assistance_message_for_error,
)

_GENERIC_SNIPPET = "flextools_find_examples"


def test_recipe_not_found_hint_is_mapped():
    hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["recipe_not_found"]
    assert "closest_matches" in hint
    assert "flextools_list_recipes" in hint


def test_refresh_failed_hint_is_mapped():
    hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["refresh_failed"]
    assert "flextoolsmcp.refresh" in hint
    assert "liblcm" in hint or "FieldWorks" in hint


def test_loop_message_uses_tailored_hints_not_generic_fallback():
    for code in ("recipe_not_found", "refresh_failed"):
        msg = _assistance_message_for_error(code, count=5)
        assert code in msg
        assert _GENERIC_SNIPPET not in msg
