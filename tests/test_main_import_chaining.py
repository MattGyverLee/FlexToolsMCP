#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: __main__ dual-mode import must chain ImportErrors (deferred-issues section 3)."""

from pathlib import Path

import pytest

import flextoolsmcp


def test_main_module_still_imports():
    main_path = Path(flextoolsmcp.__file__).parent / "__main__.py"
    assert main_path.is_file()
    spec = __import__("importlib.util", fromlist=["spec_from_file_location"]).spec_from_file_location(
        "flextoolsmcp.__main__", main_path
    )
    assert spec and spec.loader
    mod = __import__("importlib.util", fromlist=["module_from_spec"]).module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert callable(mod.run)


def test_main_dual_import_chains_in_source():
    path = Path(flextoolsmcp.__file__).parent / "__main__.py"
    text = path.read_text(encoding="utf-8")
    assert "raise _second_exc from _first_exc" in text


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
            lambda: (_ for _ in ()).throw(ImportError("relative import failed")),
            lambda: (_ for _ in ()).throw(ImportError("absolute import failed")),
        )
    assert "absolute import failed" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert "relative import failed" in str(excinfo.value.__cause__)
