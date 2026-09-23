#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CP3's *interpretation* surface (parser-check CP3,
specs/parser-check-cp3/plan.md Phase 7).

This package is deliberately separate from `server/parse/`, and the
separation is the point rather than a filing convenience.

`server/parse/` is EXECUTION and RECORD: it resolves a scope, runs the
engine, and writes an artifact. CP4 and CP5 both read that artifact, so its
shape is a forward commitment -- frozen at T053 and migrated at cost if it
is chosen loosely.

`server/signals/` is INTERPRETATION: it reads a finished artifact and says
what the results appear to mean. Nothing here is consumed by a later
checkpoint's contract, so it is free to change as the diagnosis improves.
Mixing the two would tie a judgement we expect to revise to an artifact we
have promised not to.

Two rules follow from that split and are enforced by test, not by habit:

  * Nothing in this package writes to a FieldWorks project. CP3 is entirely
    read-only, asserted by `tests/test_parse_no_project_writes.py` (FR-063).
  * Nothing here computes from the parser's *document* form. Signals are
    computed from the parser's typed structured output (FR-035, R-11); the
    document form is a rendering and reading it back is guesswork.

The modules:

    tiers.py          completeness tiering of human analyses (FR-038)
    oracle.py         what the human record affirms, and what it cannot
                      (FR-039..FR-043)
    ranking.py        promotion-only ranking by gloss agreement (FR-045)
    pairing.py        candidate pairings and lexicalized forms
                      (FR-044, FR-046)
    batch_signals.py  the five corpus-level signals (FR-036, FR-037)
    clustering.py     grouping suspect words, with a capped drill-down
                      (FR-047, FR-048)
    attribution.py    side-by-side rule-chain attribution (FR-049)
    projections.py    deletion and duplicate projections -- computed,
                      reported, acted on by nothing (FR-050)
"""
