#!/usr/bin/env python3
"""Issue #172: server.kernel and flextoolsmcp.server.kernel must alias."""

import importlib
import sys


def test_kernel_import_spellings_share_one_module():
    """Both import paths must resolve to the same module object and globals."""
    import flextoolsmcp.server.kernel as packaged

    legacy = importlib.import_module("server.kernel")

    assert packaged is legacy, (
        "Expected a single kernel module; got distinct objects for packaged "
        f"({packaged.__name__}) vs legacy ({legacy.__name__})"
    )
    assert packaged.session_state is legacy.session_state

    kernel_modules = [
        n
        for n, m in sys.modules.items()
        if n in ("flextoolsmcp.server.kernel", "server.kernel") or n.endswith(".server.kernel")
    ]
    distinct = {id(sys.modules[n]) for n in kernel_modules}
    assert len(distinct) == 1, (
        f"Expected one kernel module object, found {len(distinct)} "
        f"across {kernel_modules!r}"
    )


def test_session_import_spellings_share_one_class():
    """SessionState class identity must not diverge across import spellings."""
    import flextoolsmcp.server.session as packaged

    legacy = importlib.import_module("server.session")
    assert packaged is legacy
    assert packaged.SessionState is legacy.SessionState


def test_packaged_server_exposes_kernel_attribute():
    """flextoolsmcp.server.kernel must be reachable via attribute access (py3.10)."""
    import flextoolsmcp.server as pkg
    import flextoolsmcp.server.kernel as packaged

    assert getattr(pkg, "kernel") is packaged
