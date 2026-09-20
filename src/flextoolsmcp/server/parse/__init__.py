#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Home for the parse run machinery (parser-check CP2b,
specs/parser-check-cp2b/plan.md Phase C).

This package exists to make a *process-lifetime* boundary expressible, which
is the one thing CP2b needs that no other package in this server provides.
FR-026 says all parser execution goes through one run mechanism and that
there is no second synchronous path; that guarantee is only checkable if the
mechanism has a name and a wall around it. This package is the wall.

THE PACKAGE IS SPLIT ACROSS TWO PROCESSES. That split is the thing to
understand before editing anything here:

  Server process (imported normally by handlers and dispatch):
    stages.py         the closed stage enum and its transition table
    priority.py       the five priority levels
    queue.py          the single sorted queue, per-wordform granularity
    record.py         the append-only run record on disk
    runner.py         the run lifecycle and the 5-second grace window
    worker_client.py  the server side of the worker channel
    resolver.py       the morph resolver's DECISION LOGIC -- pure, holds no
                      project, and imported by BOTH processes. The lexicon
                      read it works over happens in the worker, because the
                      server never has a project open to read one from.

  Worker process (NEVER imported by the server process):
    worker_main.py    the long-lived parse worker

`worker_main.py` is addressed by dotted module path and launched through the
existing `subprocess_helpers.run_script_async` family, exactly the way
`run_scan_module` addresses `scan/grammar_scan_module.py`. The MCP server
process must never import it (research.md R-02): it opens a project, holds an
LCM cache and a loaded grammar, and lives inside pythonnet. Importing it
server-side would pull all of that into the server and break the one-worker-
per-project ownership this package exists to express.

For the same reason this module exports NOTHING and imports NOTHING from its
own submodules. A convenience re-export here would be a server-process import
of the worker by the back door, and `tests/test_cp1_boundary.py` pins that
(the `server/parse/` worker-module allowlist entry, research.md R-06).

Consumers import the submodule they actually need, by name.
"""

__all__: list = []
