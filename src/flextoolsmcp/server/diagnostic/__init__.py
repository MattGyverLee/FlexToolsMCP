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

Checkpoint 1 shipped the foundation:
  - triggers.py     : section 6.1 trigger predicate + 6.2 workaround inference
  - signature.py    : section 6.3 code-independent inconsistency signature
  - offered_store.py: section 6.4 offered.json read/write/prune (fail-open)

Checkpoint 2 (this checkpoint) ships reconstruction/normalization/rendering:
  - reconstruct.py  : sections 3, 5 -- JSONL-driven slice reconstruction,
                      rotation stitching (resolved Q3), MAX_REPORT_OPS
                      summarize-not-drop.
  - normalize.py    : section 8.3 / decision E2 -- path-scoped machine-
                      hygiene normalization (NORMATIVE; never a document-
                      wide find/replace of the username/home-path string).
  - render.py       : section 7 -- the seven-part report bundle, rendered
                      from a reconstructed + normalized slice.
  - triggers.py also gained `compute_casting_signature()` (CP2 precision
    fix for the deferred cycle-2 QC P1: recurrence now keys on the real
    per-issue casting signature, not a coarse same-turn fallback).

Checkpoint 3 (tool surface/transports/no-transmission guard) lands in a
later spurt as sibling modules in this same package (transports.py) --
see specs/diagnostic-report/tasks.md.
"""

__all__: list = []
