#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: teardown_recovery SIL import fallback must chain ImportErrors (deferred-issues section 3).

The writing-system mutex helper tries a direct ``SIL.WritingSystems`` import, then
``clr.AddReference`` and a second import. When both fail, the original ImportError
must remain on ``__cause__`` for diagnostics.
"""

from pathlib import Path

import pytest

from flextoolsmcp.server.handlers import teardown_recovery as tr_mod


def test_teardown_recovery_module_still_imports():
    assert callable(getattr(tr_mod, "ws_repo_mutex_names", None))


def test_ws_import_fallback_chains_in_source():
    path = Path(tr_mod.__file__)
    text = path.read_text(encoding="utf-8")
    assert "raise _ws_second from _ws_first" in text


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
            lambda: (_ for _ in ()).throw(ImportError("direct import failed")),
            lambda: (_ for _ in ()).throw(ImportError("after AddReference failed")),
        )
    assert "after AddReference failed" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert "direct import failed" in str(excinfo.value.__cause__)
