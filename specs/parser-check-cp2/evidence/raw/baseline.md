# T001 -- CP2a pre-change baseline

**Task**: T001 (Phase 1 Setup, wave 1).
**Purpose**: Principle IV. With no CI anywhere -- no hosted-runner workflow, and
the self-hosted `[windows, fieldworks]` pool has zero registered runners -- this
transcript is the only record that separates a failure CP2a *caused* from one it
*inherited*. It is not a smoke check.

## Exact invocation

Quoted verbatim from `tasks.md` ("Required invocation -- quoted per Constitution
Principle II"), run with the working directory at the flexicon repository root:

```
python -m pytest -m "not requires_live_project" -q
```

Bare `pytest` and `pytest --ignore=tests/contract` are both prohibited by that
section; neither was used.

## Tree state

| | |
|---|---|
| Repository | `D:\Github\_Projects\_LEX\flexicon` |
| Branch | `feat/parser-check-cp2` |
| Commit | `c08ede4a2d89d694905c26a6b0c099580fc17f22` |
| Working tree | clean except the untracked `flexicon/code/Parser/` from T002 |
| `flexicon.version` | `4.8.0` (pre-T023; bump target 4.9.0 not yet applied) |
| Python | 3.12.7 |
| pytest | 9.0.2 |
| Date | 2026-09-19 |

`feat/parser-check-cp2` was cut from `main` at `c08ede4`. The reflog confirms the
order: `c08ede4` was committed **on main** at 23:23:36, and the branch checkout
follows it at `HEAD@{0}`. The branch therefore carries none of the
`lcm-member-truth-sweep` campaign's in-flight work -- that campaign had committed
everything and released the repo before the cut. This is the condition spurt 4's
blocker required before T001 could be taken at all.

## Result

```
1878 passed, 808 deselected, 12 warnings in 34.53s
```

**Failures: none. There is nothing to attribute.**

The run was taken twice. The first (37.77s) overlapped T002's creation of the
empty `flexicon/code/Parser/` package, leaving the tree state at collection time
ambiguous; the second (34.53s) was taken over the settled tree recorded above.
Both produced identical counts. The second is the baseline of record, because a
baseline that cannot be reproduced from its own recorded tree state is not a
baseline. T002's `__init__.py` is zero bytes and is imported by nothing, so it
cannot affect collection or results -- but that is an argument, and the re-run is
evidence.

`808 deselected` is the `requires_live_project` tier, correctly excluded by the
marker filter. Those tests were **not run** at this task; the live tier is
T018-T021 and records its own evidence in `tier-a3.md`.

## Warnings (12) -- all pre-existing, none introduced by CP2a

Recorded rather than rounded away, per Principle IV. None is a failure and none
is actionable inside CP2a's scope:

| Count | Warning | Where |
|---|---|---|
| 5 | `PytestUnknownMarkWarning: Unknown pytest.mark.integration` | `tests/operations/test_{lexentry,lexsense,pos,text,wordform}_operations.py` -- the `integration` marker is unregistered in the pytest config |
| 2 | `PytestCollectionWarning: cannot collect test class ... has a __init__ constructor` | `tests/test_helpers.py:353` (`TestDataBuilder`), `:500` (`TestResultReporter`) -- helper classes whose names collide with pytest's `Test*` collection pattern |
| 1 | `PytestReturnNotNoneWarning` | `tests/test_lcm_direct.py::test_lcm_api_directly` returns `bool` instead of asserting |
| 4 | `DeprecationWarning: GramCatOperations is a deprecated alias for POSOperations` | `tests/test_operations_baseline.py:267,:314,:341,:379` -- the parametrised suite instantiates the deprecated alias by design (issue #276) |

## What this licenses

Any failure appearing in a later CP2a tier that is **not** in the list above --
which is empty -- is caused by CP2a and may not be recorded as pre-existing.
T028's final-suite reconciliation compares against this file.

## Side effect

The run rewrote `tests/test_results.json` (1878 tests recorded) as it always
does. `tests/live_status.json` was **not** touched and does not claim a live run;
no FLEx project was opened at this task.
