# Final suite and Success Criteria validation

**Task**: T028 (Phase 4, Polish).
**Status: GREEN.** 0 failures, so nothing had to be attributed as pre-existing.

## Exact invocation

Quoted verbatim from `tasks.md`. Working directory is the flexicon
repository root:

```
python -m pytest -m "not requires_live_project" -q
```

Bare `pytest` was never run, and neither was `pytest --ignore=tests/contract`.

## Result

```
1923 passed, 826 deselected, 12 warnings in 33.59s
```

Run with every CP2a change in the tree, including the release paperwork, so
the `flexlibs2` alias ratchet saw the new `CHANGELOG.md`, `history.md` and
`RELEASE_NOTES_v4.9.0.md` text.

### Reconciliation against the T001 baseline (Principle IV)

| | baseline (T001) | final (T028) | delta |
|---|---|---|---|
| passed | 1878 | 1923 | **+45** |
| deselected | 808 | 826 | **+18** |
| **failed** | **0** | **0** | **0** |

Every unit of both deltas is accounted for:

- **+45 passed** = the three new offline parser files,
  `tests/test_parser_offline.py` (24) + `tests/test_parser_structure.py` (9)
  + `tests/test_parser_reflective.py` (11) = 44, plus the single
  exclusion-list guard added to `tests/contract/test_lcm_contract.py` in
  response to the QC gate. The T001 baseline was taken after T002 and before
  T003 and T006 landed, so all three parser files are new since it.
- **+18 deselected** = `tests/operations/test_parser_live.py`, correctly
  excluded here and run under its own invocation (tier A3).

**No test that passed at baseline fails now, and no failure is being carried
as pre-existing** -- because there are none. This is stated rather than
rounded to: the reconciliation is the point of the task, and a zero is only
meaningful next to the baseline it is compared against.

### Warnings

12, all pre-existing and none from CP2a code: an unregistered
`pytest.mark.integration`, two helper classes pytest cannot collect because
they define `__init__`, and `GramCatOperations` deprecation notices. Seen,
checked, and judged benign.

## The four release ratchets, run explicitly

T027 requires all four green before the release commit. Run as their own
invocation so the result is not buried in the full-suite count:

```
python -m pytest tests/test_297_init_stub_parity.py tests/test_pyi_return_annotation_ratchet.py \
    tests/test_docstring_example_ratchet.py tests/test_flexlibs2_alias_ratchet.py \
    -m "not requires_live_project" -q
```

```
30 passed in 11.37s
```

| Ratchet | Covers | Outcome |
|---|---|---|
| `test_297_init_stub_parity` | `__init__.py` / `__init__.pyi` export parity | pass |
| `test_pyi_return_annotation_ratchet` | `.py` and `.pyi` do not contradict | pass |
| `test_docstring_example_ratchet` | every `>>>` example names real API | pass |
| `test_flexlibs2_alias_ratchet` | the forbidden string appears in no new code, comment, docstring, test or doc | pass |

The docstring ratchet is worth singling out: before T013 registered
`project.Parser` it reported **seven** `unknown-accessor` findings, one per
facade docstring using the accessor. All seven cleared, and
`tests/docstring_example_baseline.json` was **not** regenerated -- the
findings were fixed, not absorbed.

Separately confirmed clean by direct scan: the string appears in none of
`flexicon/code/Parser/`, `tests/test_parser_offline.py`,
`tests/operations/test_parser_live.py`, or `RELEASE_NOTES_v4.9.0.md`.

## Success Criteria in CP2a's scope

| SC | Claim | Where it is evidenced | Status |
|---|---|---|---|
| **SC-001** | asking availability never raises, on any machine, in any condition | tier A1 `TestA11AvailabilityDegradesWithAReason` (7 tests), driving component-absent, foreign-install, and probe-itself-throws by *simulating* each | **MET** |
| **SC-002** | 0 comparisons of a detected parser version against a minimum | tier A1.2 standing AST ratchet over `flexicon/code/Parser/`, with a self-test that plants a floor and catches it | **MET** |
| **SC-014** | at most one grammar held, 0 retained for a project not in use | tier A3.5, live, across both projects plus a single area re-pointed at a second cache | **MET** |
| **SC-015** | 0 parses served from a grammar whose currency was not confirmed immediately before reuse | tier A3.5, live: currency read wrapped and counted -- 3 parses by 3 routes, 3 confirmations. Order (not just count) pinned offline by A1.6 | **MET** |
| **SC-016** | the shipped MCP-side capability check is unmodified, and the divergence is written down | T029: 0-line diff and 0 commits since CP2a began; divergence documented in `ParserOperations.GetAvailability`'s docstring and in `tests/test_parser_reflective.py` | **MET** |
| **SC-013** (CP2a portion) | the released surface is reachable as an ordinary area of the project object | `project.Parser` registered (T013), exported top-level (T014), alias registered (T016), reachable live in tier A3 | **MET** |

### One qualification, recorded rather than glossed

**SC-015 is met for the paths CP2a can exercise read-only.** The counted
evidence shows currency is confirmed before every reuse, and A1.6 shows a
stale answer produces a reload *before* the parse. What is **not** shown
live is the automatic reload firing when the model genuinely changes
underneath a held grammar -- making a grammar stale on purpose requires a
write, which is tier A4, deferred to CP2b with `needs_human` (escalation
E-D). That link is covered only against a stubbed currency read.

## Note on a green suite

Recorded because it is the standing lesson of this checkpoint: **this suite
was green while the facade was returning wrong answers.** Tier A1 passed,
all four ratchets passed, and an unrestricted trace was still silently
truncating every subsequent plain parse. Only the live tier found it (see
[`tier-a3.md`](tier-a3.md)). The count above is necessary evidence and it is
not sufficient evidence.
