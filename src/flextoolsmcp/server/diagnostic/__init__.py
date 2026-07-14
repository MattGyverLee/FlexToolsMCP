#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic-report feature ("send this to the maintainer" flow).

Spec: specs/diagnostic-report/SPEC.md.

This package is deliberately kept SEPARATE from the rest of `server/` so the
section 12 "no transmission" guard has a small, dedicated, AST-scannable tree
to check: a static scan of every module under this package must fail the
build on any `subprocess`, `gh`/`git issue create`, `smtplib`,
`webbrowser.open`, `urllib`/`requests`/`http.client`, or raw `socket` outbound
call. Nothing in this package sends anything anywhere -- it only reads/writes
local files under ~/.flextoolsmcp/reports/ and computes in-memory values.

Checkpoint 1 (this checkpoint) ships the foundation only:
  - triggers.py     : section 6.1 trigger predicate + 6.2 workaround inference
  - signature.py    : section 6.3 code-independent inconsistency signature
  - offered_store.py: section 6.4 offered.json read/write/prune (fail-open)

Checkpoint 2 (reconstruction/normalization/rendering) and checkpoint 3
(tool surface/transports/no-transmission guard) land in later spurts as
sibling modules in this same package (reconstruct.py, normalize.py,
render.py, transports.py) -- see specs/diagnostic-report/tasks.md.
"""

__all__: list = []
