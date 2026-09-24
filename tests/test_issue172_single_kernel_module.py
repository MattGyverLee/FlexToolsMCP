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
