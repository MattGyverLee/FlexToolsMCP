# Tier A1 -- the offline behavioural and structural evidence

**Tasks**: T005 (behavioural checks), T006 (standing ratchets), T017 (this transcript).
**Phase 3, User Story 1.**
**Status: GREEN.** A1.1 through A1.6 all pass. The tier A3 live tasks are released.

## Exact invocation

Quoted verbatim from `tasks.md` ("Required invocation -- quoted per Constitution
Principle II"). Working directory is the flexicon repository root:

```
python -m pytest -m "not requires_live_project" -q
```

The A1 files alone, for the focused run:

```
python -m pytest tests/test_parser_offline.py tests/test_parser_structure.py -m "not requires_live_project" -q
```

Bare `pytest` was not run at any point, and neither was
`pytest --ignore=tests/contract` -- both apply no marker filter and would
execute `requires_live_project` tests against real projects.

## Tree state

| | |
|---|---|
| Repository | `D:\Github\_Projects\_LEX\flexicon` |
| Branch | `feat/parser-check-cp2` |
| Behavioural file | `tests/test_parser_offline.py` (new at T005) |
| Structural file | `tests/test_parser_structure.py` (new at T006) |
| Facade under test | `flexicon/code/Parser/ParserOperations.py` (new at T010/T011) |
| Python / pytest | 3.12.7 / 9.0.2 |
| Date | 2026-09-19 |

**No project was opened, no LcmCache was constructed, no grammar was loaded
and no word was parsed.** The behavioural tests drive the facade against a
hand-built stub parser and against a component resolution pointed at paths
that do not exist; the structural tests read source text. There is no write
risk of any kind, which is why the file carries no marker and runs in the
default tier.

## Result

Focused run, the two A1 files:

```
29 passed in 1.78s
```

Full offline suite, the required invocation:

```
1918 passed, 824 deselected, 12 warnings in 28.11s
```

**Zero failures.** Nothing to reconcile against the T001 baseline as
pre-existing, because nothing failed.

### Reconciliation against the T001 baseline

Principle IV requires the separation of CP2a-caused failures from inherited
ones. Both counts moved, and both movements are fully accounted for:

| | baseline (T001) | now (T017) | delta |
|---|---|---|---|
| passed | 1878 | 1918 | **+40** |
| deselected | 808 | 824 | **+16** |
| failed | 0 | 0 | 0 |

- **+40 passed** is exactly the three new offline parser files:
  `test_parser_offline.py` (20) + `test_parser_structure.py` (9) +
  `test_parser_reflective.py` (11) = 40. The T001 baseline was taken after
  T002 and before T003 and T006 landed, so all three files are new since it.
- **+16 deselected** is exactly the new live tier,
  `tests/operations/test_parser_live.py`, confirmed by
  `--collect-only -m requires_live_project`: **16 tests collected**. Being
  deselected here is correct -- tier A3 runs under its own invocation.

No test that passed at baseline fails now, and no failure is being carried.

## What each assertion covers

### `tests/test_parser_offline.py` -- 20 tests

| Group | Covers | Outcome |
|---|---|---|
| `TestA11AvailabilityDegradesWithAReason` (7) | **A1.1 -- SC-001, FR-004** | pass |
| `TestA14NoWriteSurface` (4) | **A1.4 -- FR-002** | pass |
| `TestA15PositionalBinding` (3) | **A1.5 -- FR-005** | pass |
| `TestA16StaleGrammarReloadsBeforeParsing` (6) | **A1.6 -- FR-043, SC-015** | pass |

### `tests/test_parser_structure.py` -- 9 tests

| Group | Covers | Outcome |
|---|---|---|
| `TestA13NoModuleScopeParserImport` (4) | **A1.3 -- FR-003** | pass |
| `TestA13FacadeLoadsByUse` (1) | A1.3, positive half | pass |
| `TestA12NoParserVersionFloor` (4) | **A1.2 -- FR-006, SC-002** | pass |

## Three results worth recording beyond the count

**1. A1.3's positive half is no longer skipping.** At T006 the facade did not
exist, so `TestA13FacadeLoadsByUse` skipped and only the negative ratchet
("no module-scope parser import anywhere") was doing work. With
`ParserOperations.py` landed it now asserts the compliant shape positively:
the module has zero module-scope parser imports *and* at least one
function-local one. A ratchet that scans for something absent passes
trivially when it scans nothing; this one is now scanning something.

**2. A1.1 simulates absence rather than observing it.** Every unavailability
test actively repoints `_parser_component_path` / `_data_model_dir` -- at a
path that does not exist, at two differing directories, and at a function
that raises. The machine these ran on has a working parser (tier A2
confirmed `ParserCore.dll` 9.3.10 resolving from
`C:\Program Files\SIL\FieldWorks 9`), so none of these three states occurs
here naturally. A test that merely ran on a broken machine would pass for
the wrong reason everywhere else.

**3. A1.6 asserts ORDER, not counts.** The stub records the sequence of calls
the facade makes. SC-015 is "0 parses served from a grammar whose currency
was not confirmed immediately before reuse" -- a reload that happens after
the parse satisfies every count and none of the meaning, so the assertions
are `index(Reset) < index(ParseWord)`, and the same for every route
(`ParseWordXml`, `TraceWordXml`). One test asserts the counterweight: a
grammar reported *current* is **not** reloaded, because a facade that
reloaded unconditionally would pass every order assertion and be useless.

## What tier A1 does NOT prove

Stated because the evidence artifact must not be read as claiming more than
it tested (Principle V), and because this is the exact gap T019 exists to
close:

**A1.6 proves the facade CALLS reset-then-update in the right order against a
stub. It does not prove the real component discards anything.** The stub
does what it is told. Whether `Reset()` followed by `Update()` actually
replaces the loaded grammar in `ParserCore.dll` -- and whether a bare
`Update()` really does short-circuit, which is D-A5's whole premise -- is a
property of the real component and is witnessed only by tier A3.3 (T019).

This is not a formality. Every one of flexicon's four structural ratchets,
and every test in this tier, **would have passed a reload bound to a bare
update** -- which is the defect cycle 1 actually found. A green A1 cannot
discharge the one claim that matters most.

## One unplanned change this tier forced

`tests/contract/extract_lcm_contract.py` gained a `NON_CONTRACT_PREFIXES`
exclusion for `SIL.FieldWorks.WordWorks.Parser`. No task names that file.

The facade is the first code in the package to import from a SIL namespace
that is **not a required library**, and the contract extractor had no concept
of an optional one: it classified `HCParser` as an LCM type dependency, and
`TestLiveContractVerification` then reflected for it and failed
(`test_no_new_type_dependencies`, `test_all_types_found`,
`test_compatibility_score` -- three real failures, not noise).

Adding `HCParser` to the baseline would not have helped, since
`test_all_types_found` checks the baseline against the liblcm snapshot.
Teaching the snapshot generator to load `ParserCore.dll` would have made an
optional component mandatory for the contract suite -- the direct opposite of
FR-003. The exclusion is scoped to the parser namespace alone; the four other
`SIL.FieldWorks.*` modules already in the baseline are untouched. Contract
suite after: **22 passed**.

## Next

Tier A1 is green, so T018-T021 (tier A3, live, read-only) are released.
T019/A3.3 remains the gate that blocks CP2b, and it cannot be cleared
offline.
