# Implementation Plan: parser-check CP2a -- the script-library parser surface

**Scope**: CP2a ONLY -- User Story 1 (FR-001..FR-011) in the `flexicon`
repository. CP2a-bridge and CP2b are deliberately NOT planned here; see
"Scope fence" below.

**Implementation repository**: `D:\Github\_Projects\_LEX\flexicon`
(package `flexicon`, installed in this environment in editable mode).
This planning artifact lives in the `FlexToolsMCP` repo because the
checkpoint is specified here, but **CP2a changes no file in this
repository.**

**Governing constitution**: `D:\Github\_Projects\_LEX\flexicon\.specify\memory\constitution.md`
(Flexicon Constitution v1.0.0). This repository has no
`.specify/memory/constitution.md`; the work lands in flexicon, so
flexicon's constitution governs.

**Planning brief**: `specs/parser-check-cp2/reviews/cycle1-synthesis.md`
**Spec**: `specs/parser-check-cp2/spec.md` (amendment-clean as of commit
`088e781`)

---

## Summary

CP2a adds a read-only parser area to the `flexicon` project object, so a
generated FLExTools module can ask "does this word parse?" through the same
object it already receives, and degrades to a stated reason rather than an
exception when the parser component is missing. It also closes three read
gaps the later checkpoints depend on: all genres of a text rather than only
the first, the entry that owns an allomorph, and a readable
morpho-syntactic-analysis surface.

The technical approach is almost entirely *pattern replication*, not
invention: flexicon has a settled Operations-class idiom, a settled lazy
`@property` registration mechanism, and existing sibling templates for each
of the three read gaps. Two things are genuinely new and carry the
checkpoint's risk. First, a capability probe that **degrades with a reason**
-- flexicon today has exactly two shapes, raise or silently become `None`,
and no precedent for a third. Second, the binding of the grammar reload,
which cycle 1 proved cannot be a bare `Update()` call.

No new runtime dependency is introduced. The work ends with a `4.9.0`
release cut, whose tag push is a maintainer act, not an automated one.

---

## Scope fence

Three things are in the spec but **not** in CP2a, recorded here so they do
not drift in by association with US1:

| Out of CP2a | Where it belongs | Why |
|---|---|---|
| `pyflexicon>=4.9.0,<5` floor, refreshed index artifacts, floor/index-equality test | **CP2a-bridge** (this repo, ~4 files) | Runs after the tag, before CP2b's first parser task. Changes no handler, tool or contract. Named separately so it cannot be used as a precedent for starting CP2b early. |
| `flextools_try_word`, `flextools_parse_status`, the run record, stages, priority queue, cancellation | **CP2b** (this repo, ~17 files) | Entry gate is CP2a's recorded evidence plus the landed bridge. |
| SC-003 / the `HCParser_DoesNotLoadXCore` standing test | **CP2b** | Cycle 1 established the no-user-interface guarantee must be asserted against the loaded-assembly list of the `run_scan_module` **child process**, which is MCP-side machinery that does not exist in flexicon. Associating it with US1 because both mention the parser would put it in the wrong repository. |

Decision D4 is authoritative on ordering: Part A is extended and **proven**
before any assistant-side change. The seam is at *proven*, not *released*.

---

## Project Structure

All paths relative to `D:\Github\_Projects\_LEX\flexicon`.

```
flexicon/
  __init__.py                      # version 4.8.0 -> 4.9.0; ParserOperations
                                   #   export; CAPABILITIES += "parser";
                                   #   the #: doc block above the frozenset
  __init__.pyi                     # matching import + __all__ entry
  py.typed                         # (unchanged -- stubs already shipped)
  code/
    Parser/                        # NEW domain package
      __init__.py                  # NEW
      ParserOperations.py          # NEW -- the facade + capability probe
      ParserOperations.pyi         # NEW -- hand-written stub
    FLExProject.py                 # + lazy @property Parser (one block)
    FLExProject.pyi                # + import and `def Parser(self) -> ...`
    _op_aliases.py                 # + "Parsers" -> "Parser" plural guess
    TextsWords/
      TextOperations.py            # + GetGenres() (FR-007)
      TextOperations.pyi           # + matching stub line
    Lexicon/
      AllomorphOperations.py       # + GetOwningEntry() (FR-008)
      AllomorphOperations.pyi      # + matching stub line
      MSAOperations.py             # + GetAll() read surface (FR-009)
      MSAOperations.pyi            # + matching stub line
tests/
  flex_plugin.py                   # operations_modules + _OPERATIONS_CLASS_DOMAIN
  write_path_transactions/
    test_capabilities.py           # EXPECTED_TOKENS += "parser"
  test_parser_offline.py           # NEW -- tier A1
  test_parser_reflective.py        # NEW -- tier A2
  operations/
    test_parser_live.py            # NEW -- tier A3 (read-only)
CHANGELOG.md                       # [Unreleased] -> [4.9.0] - <date>
history.md                         # newest-first narrative entry
RELEASE_NOTES_v4.9.0.md            # NEW
```

Plus one artifact written back into **this** repository, which is the only
FlexToolsMCP file CP2a touches:

```
specs/parser-check-cp2/evidence/cp2a-evidence.md   # NEW -- the A1-A3 record
```

**Structure Decision**: `ParserOperations` gets its own domain package
`flexicon/code/Parser/` rather than joining `Lexicon/` or `TextsWords/`,
because it wraps a different assembly (`ParserCore.dll`) with a different
availability lifetime than the data model, and the package boundary is what
makes "this whole area can be unavailable" expressible. The accessor is
**singular** `project.Parser`: `_op_aliases.py:6-8` reserves plural for
collection namespaces and singular for service facades (`POS`, `MSA`,
`Discourse`, `ProjectSettings`), and a parser is a service.

---

## Constitution Check

Assessed against the Flexicon Constitution v1.0.0. Gate status before
Phase 0: **PASS** (no violations). Re-checked after Phase 1 design:
**PASS**.

| Principle | Assessment |
|---|---|
| **I. Verify the LCM surface before building on it** (NON-NEGOTIABLE) | **PASS, and this principle is the checkpoint's spine.** Every member the facade binds is verified against the real installed `ParserCore.dll` in tier A2 before any behaviour is built on it, and the reload binding is verified behaviourally in A3. Cycle 1's FR-043 finding is this principle's documented failure mode caught early: `HCParser.Update()` is conditional, so `Reload() -> Update()` would have shipped a discard guarantee that is fiction -- the same shape as the `RollbackToMark` incident (#236) the principle cites. |
| **II. No live FLEx write without a human gate** (NON-NEGOTIABLE) | **PASS.** CP2a performs no live write. Tier A3 opens `IndonesianHC-Complete` with `writeEnabled=False`; tier A4 (the only write-requiring proof) is explicitly deferred to CP2b with `needs_human`. The required invocation is quoted verbatim in Phase 1 and in every task briefing: `python -m pytest -m "not requires_live_project" -q`. `pytest --ignore=tests/contract` is prohibited and appears nowhere in this plan. |
| **III. Controls, not prohibitions** | **PASS.** Every constraint this checkpoint relies on is encoded as something that fails loudly, not as prose an implementer must remember: FR-002's absence-of-write-path becomes an enumeration test over the facade's public surface, FR-006's no-version-comparison becomes a standing AST test, FR-003's laziness becomes an AST assertion that no module-scope parser import exists (template: `tests/test_public_casting_export.py:127-153`), and the `"parser"` CAPABILITIES token is already ratcheted by a frozen `EXPECTED_TOKENS` literal. |
| **IV. Report the measurement, not the impression** | **PASS.** The evidence artifact records the exact invocation and full counts per tier, including pre-existing failures named as pre-existing. It is explicitly not a passing-test count -- see Phase 1, "The evidence artifact". |
| **V. Honest API surface** | **PASS, with the sharpest constraint on this checkpoint.** `tests/write_path_transactions/test_capabilities.py:12-16` states that a CAPABILITIES token added without a landed capability behind it is a Principle V violation, so `"parser"` lands **last**, after the facade is proven. The unavailability reason must state what was actually checked (directory equality, member presence) and must not imply the component was loaded and validated -- FR-004 accepts that a foreign component in the right directory passes undetected, and the docstring says so. |
| **VI. Hide LCM complexity, not LCM behavior** | **PASS.** Callers never see `ClassName` or a cast: the MSA surface returns the existing `MorphosyntaxAnalysis` wrapper with its `is_*` / `as_*` family. But behaviour that changes what happens to their data does surface -- parser unavailability is a return value with a reason, not a swallowed `None`, and the conditional nature of reload is documented at the call site rather than smoothed away. |

No Complexity Tracking table: there are no violations to justify.

---

## Phase 0 -- Research

Complete. See [`research.md`](./research.md) for the eight decisions and
their alternatives, and for the four findings that changed the shape of
this plan relative to the cycle-1 brief.

The two findings that most affect sequencing, stated here because they
change what the task list can assume:

1. **`import flexicon` requires FieldWorks.** The package's own module
   scope calls `InitialiseFWGlobals()`, which raises when the FieldWorks
   registry key is absent. The cycle-1 brief's tier A1 ("Offline, no
   FieldWorks, no project. Runs anywhere, including CI.") is therefore not
   achievable as written. A1 is re-tiered in `research.md` (D-A1). SC-001
   itself remains satisfiable -- it speaks about the *parser component*
   being absent, not FieldWorks.
2. **The MSA read surface is far cheaper than estimated.** The wrapper
   `MorphosyntaxAnalysis` and its `MSACollection` are already fully
   written and are never instantiated by any code path. FR-009 is wiring,
   not design.

---

## Phase 1 -- Design and contracts

- [`data-model.md`](./data-model.md) -- the entities CP2a introduces or
  reshapes, their fields, and the availability state transitions.
- [`contracts/parser-operations.md`](./contracts/parser-operations.md) --
  the public surface a caller or test codes against, with every
  spec-pinned identifier copied exactly.
- [`contracts/evidence-gate.md`](./contracts/evidence-gate.md) -- the
  A1-A3 tiers as a checkable contract, since CP2b's entry depends on it.

**The evidence artifact.** CP2a ends by writing
`specs/parser-check-cp2/evidence/cp2a-evidence.md` in this repository,
recording what was *observed* per tier with the exact invocation that
produced it. Per Decision D4 and Principle IV, the next phase is authorised
by observation, not by a green suite -- a future maintainer asking "how do
we know the reload discards?" must find an answer that is not "there is a
test named that".

**Required invocation, quoted per Principle II:**

```
python -m pytest -m "not requires_live_project" -q
```

For the A3 tier only, run in-place against the installed project:

```
$env:FLEXLIBS_REQUIRE_LIVE = "1"; python -m pytest tests/operations/test_parser_live.py -m requires_live_project -q
```

---

## Sequencing

The order is constrained, not stylistic. Each step's output is the next
step's precondition.

1. **A2 first, before any facade behaviour.** Verify every member against
   the real installed `ParserCore.dll` (Principle I). This is the direct
   remediation of cycle 1's finding, and `Reset` / `IsUpToDate` have never
   been verified anywhere.
2. **The three read gaps.** Independent of the parser entirely, and of
   each other -- genres, allomorph owner, MSA reads can proceed in
   parallel once A2 is underway.
3. **The facade and its probe**, including the degrading
   unavailable-with-reason return, which has no template to copy.
4. **A1 offline tests** against the facade, simulating component absence.
5. **A3 live read-only** against `IndonesianHC-Complete`, including the
   unconditional-discard proof. **A `Reload()` that cannot be shown to
   discard has not been proven, and CP2b does not start.**
6. **The `"parser"` CAPABILITIES token** -- last, per Principle V.
7. **The release cut**: version bump, CHANGELOG, history, release notes.
   The tag push and `gh release create` are maintainer acts (escalation
   E-C) -- the crew prepares the release commit and stops.

---

## Risks specific to CP2a

- **The degrading probe has no template.** flexicon's only lazy-load
  precedent raises; the per-type degrade path silently produces `None`
  with no reason recorded. The unavailable-with-reason return is new code,
  and must be tested by *simulating* absence rather than assuming it.
- **A3's discard proof reads a private field.** The observable witness
  that `LoadParser()` ran is a replaced internal morpher instance. That is
  a private-field read under pythonnet, acceptable only in a test that
  documents itself as such, with the `{ProjectName}HCLoadErrors.xml`
  rewrite as the documented fallback.
- **No CI safety net.** No workflow runs pytest on a hosted runner, and
  the self-hosted `[windows, fieldworks]` pool has zero registered
  runners. Every ratchet and every tier is a local, manual measurement --
  which raises the stakes on Principle IV's exact-invocation discipline.
- **Four ratchets fail loudly on a new Operations class.** Stub parity,
  return-annotation agreement, docstring examples and alias stability all
  have opinions about a new class. They are listed as concrete edits in
  `research.md` D-07 so they are not discovered one failure at a time.
