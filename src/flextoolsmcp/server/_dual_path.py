#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collapse legacy ``server.*`` and packaged ``flextoolsmcp.server.*`` spellings.

Pytest puts both ``src/`` and ``src/flextoolsmcp/`` on ``sys.path``, so the
same file can load twice under different module names (#172). Call
``alias_dual_path_modules`` at the end of each dual-loaded module.
"""

from __future__ import annotations


def alias_dual_path_modules(*pairs: tuple[str, str]) -> None:
    """Point each (packaged, legacy) name pair at one shared module object.

    Prefer the packaged spelling when both are already loaded. Also bind the
    submodule attribute on the parent package so attribute access and
    ``unittest.mock.patch`` path resolution work on Python 3.10.
    """
    import sys

    for packaged_name, legacy_name in pairs:
        packaged = sys.modules.get(packaged_name)
        legacy = sys.modules.get(legacy_name)
        if packaged is None and legacy is None:
            continue
        mod = packaged if packaged is not None else legacy
        assert mod is not None
        for name in (packaged_name, legacy_name):
            sys.modules[name] = mod
        for full_name in (packaged_name, legacy_name):
            parent_name, attr = full_name.rsplit(".", 1)
            parent = sys.modules.get(parent_name)
            if parent is not None:
                setattr(parent, attr, mod)
