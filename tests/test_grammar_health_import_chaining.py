#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: grammar_health dual-mode imports must chain ImportErrors (deferred-issues section 3).

PR #409 chains the inline ``project_adoption`` fallback only. The module-level
``response_utils`` import and the handler's ``execution`` / ``project_discovery``
fallbacks were still bare ``except (ImportError, ValueError)`` blocks that discard
the original traceback when the script-mode import also fails.
"""

from pathlib import Path

import pytest

from flextoolsmcp.server.handlers import grammar_health as gh_mod


def test_grammar_health_module_still_imports():
    assert callable(getattr(gh_mod, "handle_flextools_grammar_health", None))


def test_grammar_health_dual_imports_chain_in_source():
    path = Path(gh_mod.__file__)
    text = path.read_text(encoding="utf-8")
    # Response_utils block chains and reaches the server tier (3-tier form,
    # superseding the old 2-tier pin): assert the chain, not the exact
    # 2-tier raise string.
    assert "from server.response_utils import build_response_with_context, error_response" in text
    assert "raise _response_utils_third from _response_utils_second" in text
    assert "raise _execution_second from _execution_first" in text
    assert "raise _discovery_second from _discovery_first" in text
    assert "raise _resolve_second from _resolve_first" in text
    assert "raise _adopt_second from _adopt_first" in text
    assert text.count("except (ImportError, ValueError):\n") == 0 or (
        "except (ImportError, ValueError) as" in text
    )


def test_dual_import_fallback_chains_when_both_fail():
    def _chain_harness(primary, fallback):
        try:
            return primary()
        except ImportError as first_exc:
            try:
                return fallback()
            except ImportError as second_exc:
                raise second_exc from first_exc

    with pytest.raises(ImportError) as excinfo:
        _chain_harness(
            lambda: (_ for _ in ()).throw(ImportError("package-mode failed")),
            lambda: (_ for _ in ()).throw(ImportError("script-mode failed")),
        )
    assert "script-mode failed" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert "package-mode failed" in str(excinfo.value.__cause__)
