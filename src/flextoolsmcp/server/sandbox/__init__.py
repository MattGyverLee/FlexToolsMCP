#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Home for the parser-check sandbox spine (parser-check CP5,
specs/parser-check-cp5/plan.md).

The sandbox spine runs HermitCrab outside FieldWorks: it builds an HC config
from a COPY of the project, then drives `hc` over that config through the
packaged `scripts/hcparse.ps1`. This package holds the spine's policy; the
script holds the mechanics (contracts/hcparse.md).

THE READ-ONLY BOUNDARY. Everything in this package is written to one rule,
and that rule is the thing to understand before editing anything here:

  - The spine NEVER opens the live project through LCM. The one read of the
    live project is a plain stream-read of the `.fwdata` (engine.py, R-02) and
    the file copy made for config generation. No LcmCache, no FLExProject, no
    pythonnet, and therefore no `.fwdata.lock`.
  - The spine NEVER writes inside a project folder. Every file it creates lives
    under the sandbox root (paths.py; `FLEXTOOLSMCP_PARSE_SANDBOX_DIR`
    overrides it), and `assert_outside_project` guards each write path (R-11).

Four lifecycles live under the sandbox root, each owned by one module:

  copy      the allowlisted project copy in a marked work dir; created per
            generation and deleted in `finally`, swept at startup (workdir.py)
  cache     generated HC configs keyed by project + inputs, built through
            `-Mode Generate`, LRU-pruned, invalidated after writes (cache.py)
  sandbox   a named, user-visible config snapshot to parse against (store.py)
  corpus    the assertion corpus a sandbox is tested with (store.py)

Submodules (see plan.md "Source Code"): paths, engine, workdir, cache, script,
hc_output, classify, store, client.

This module exports nothing and imports nothing from its own submodules.
Consumers import the submodule they actually need, by name.
"""

__all__: list = []
