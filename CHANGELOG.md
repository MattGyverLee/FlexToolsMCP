# FlexToolsMCP Changelog

## [Unreleased]

- Recovered SIL.LCModel.Core types that a `ReflectionTypeLoadException` was
  silently dropping from the LibLCM index during extraction (#135).

### Doc-snippet gate: scope split with flexicon, and our own comments added

flexicon now gates its own docstring examples at source
(`tests/test_docstring_example_ratchet.py`, static AST over the library
itself). Scanning the same text here against a generated index is the weaker
of two duplicate checks, so the upstream surface is no longer scanned by
default -- `--upstream` / `--worklist` keep it available for cross-checking
and for regenerating the worklist.

In its place the gate now covers what this repo writes and previously did
not: our own `>>>` docstring examples, and API claims in our comments and
docstring prose. Prose is judged narrowly -- only a two-segment
`project.<Accessor>.<Member>` reference or a flexicon import, with
metavariables (`X`, `XOperations`) and `doc-check: ignore` lines skipped.
A bare `project.<X>` mention is not a claim: `validators.py` alone discusses
29 wrong accessor names on purpose, and flagging those would bury real
findings under intentional counter-examples.

Also fixed a false-failure class the wider scan exposed: flexicon installs 46
deprecated singular/plural accessor aliases onto FLExProject at import time
(`_op_aliases.OP_NAMESPACE_ALIASES`, issue #200), and 17 of them were absent
from the accessor universe this checker derives. `project.Sense.GetGloss(s)`
runs -- with a DeprecationWarning -- so calling it a typo is wrong. The
checker now reads the alias table and resolves members through it.

### New: a gate for the code that lives inside text

`scripts/check_doc_snippets.py` checks every code claim the MCP teaches from
against the bundled flexicon index: `python` fences in repo-root and `docs/`
markdown, `templates/`, `CURATED_RECIPES` and `WORKED_EXAMPLES` code strings,
their `see_also` references, and the index's own docstring examples. pyright
covers `src/` and none of that, which is why refactor rot survives there:
names in prose stay plausible forever.

Checks are `syntax`, `bad-import`, `unknown-accessor`, `unknown-method`,
`arity`, and `refusing-method` -- the last for members that still exist but
always raise `NotImplementedError`, a class of rot no existence check can
see. Base classes are resolved transitively (without that, every
`BaseOperations` `Move*`/`Sort` call reads as a phantom failure), and each
snippet's flavor comes from its own imports, overridable with a
` ```python flavor=flexlibs_stable ` / ` ```python doc-check=ignore ` fence
info string.

The check refuses (exit 2) rather than reports (exit 1) when it cannot see
its full ground truth -- no `flextoolsmcp` import, no served-code surfaces.
pre-commit's isolated venv produced exactly that: a narrowed accessor
universe that flagged 13 valid names (`project.Text`, `project.Example`, ...)
as typos. The hook now runs with `language: system`, and a gate that fails on
valid code cannot quietly become one people learn to bypass.

`--worklist PATH` writes the upstream findings as an actionable list --
markdown plus a JSON sibling -- resolving each one from an index entity
(`FLExProject.Paragraphs`) to the flexicon repo path and `def` line where the
docstring actually lives, with a nearest-real-name suggestion where difflib
finds one. Checked in at `reports/upstream-flexicon-docstring-findings.md`.

Wired as a pre-commit hook and `tests/test_doc_snippets.py`, so the real
trigger -- `refresh.py` moving to a new flexicon while the prose stays put --
turns CI red. Upstream pyflexicon docstring findings are reported
(`--upstream`), never blocking.

Fixed what it found:

- CLAUDE.md and `docs/FLEXTOOLS-STYLE-GUIDE.md` taught
  `from flexicon import ReversalOperations`, a symbol that does not exist
  (`ReversalIndexOperations` / `ReversalIndexEntryOperations` are real). The
  template that imported it was fixed long ago; the prose teaching it was
  not, so every generated script inherited the dead import.
- The `phonological-rule-with-context` worked example called
  `PhonRules.AddInputSegment` / `AddOutputSegment` (never existed) and
  `SetLeftContext` / `SetRightContext` (exist, always refuse since flexicon
  issue #142). Rewritten on `WireRule` with `Seg`/`NC`; its `see_also` list
  pointed at the same four dead names.
- Three markdown fences did not parse as Python at all.

### Index refreshed to flexicon 4.7.0

`python -m flextoolsmcp.refresh` against the installed flexicon 4.7.0. The
bundled flexicon-mode index, LCM bridge and common-patterns files move to
`v4.7.0`; the `v4.6.0` files leave the repo (they are kept locally under the
gitignored `index/**/archive/`, still resolvable for a project pinned to the
older flexicon). LibLCM stays at `v11.0.0`, with its `python_wrappers`
back-annotations and `reverse_mapping_liblcm-v11.0.0.json` updated by the same
pass.

Reviewed diff -- 118 entities unchanged, none added or removed, 1537 -> 1529
methods, description coverage 100%, example coverage 76.3% (was 76.4%).
Exactly three entities changed:

- `FLExProject` **+`FromOpenProject`** -- the attached-view bridge constructor
  landing in the index for the first time. Its `return_type` is `""` (no
  return annotation upstream), which is what issue #130 turned on.
- `POSOperations` **+`GetParent`**.
- `GramCatOperations` **-10 methods** (`ApplySyncableProperties`, `CompareTo`,
  `Delete`, `Duplicate`, `GetAll`, `GetName`, `GetParent`,
  `GetSyncableProperties`, `SetName`, `GetSubcategories`), leaving `Create`
  and `__init__`. Not an API removal: 4.7.0 made `GramCatOperations` a
  deprecated alias subclassing `POSOperations`, and the AST extractor records
  only an entity's own definitions, never inherited ones. The methods are all
  still callable, via the base class.

No `is_mutating` flag flipped anywhere, so no write-gate classification
changed. The `GramCatOperations` shrink does mean calls like
`GramCatOperations(project).Delete(cat)` now resolve as
`source: "unknown"` (method not in that entity) rather than `source: "index"`.
They are still blocked -- an unknown non-read-only-prefixed method on a known
Operations class already fails closed -- but at lower confidence. Flattening
inherited methods into the index is the real fix and is not attempted here.

### Fixed: the write gates were blind to the facade shape they teach (#130)

An **unguarded** mutation reached through `FLExProject.FromOpenProject(project)`
passed **every** write gate. `unprotected_writes` reported `passed`,
`writeability.is_mutating_script` was `false`, and
`would_require.write_enabled` was `false` -- so a write with no
`if modifyAllowed:` guard, no confirmation prompt and no mutation plan was
treated as a read-only script:

```python
fx = FLExProject.FromOpenProject(project)
entry = fx.LexEntry.Find("nsanga-nsanga")
fx.LexEntry.SetLexemeForm(entry, "PROBE-SHOULD-BE-BLOCKED")   # 11 gates green
```

That is the shape flexicon 4.7.0 documents as *the* portable module shape, and
the shape `flextools_get_module_template(flavor='flexicon')` itself generates.
The blind spot landed squarely on the pattern users are told to adopt.

**Why an index refresh did not help.** The resolver typed a call receiver by
comparing its name to the literal `"project"`. `fx` is not `project`, so `fx`
was untyped, `fx.LexEntry` was untyped, and the mutating call on it was never
looked up in the API index at all -- it was not misfiled, it was unseen, in
every bucket. Nor could the index rescue it: `FromOpenProject` carries no
return annotation upstream, so its recorded `return_type` is `""`. Return-type
coverage on `FLExProject` is thin generally (28 of 107 methods).

**Two fixes, because either alone leaves a gap.**

- The receiver test is now a membership test over every variable known to hold
  a `FLExProject`, not a comparison to one name. Facade-valued variables are
  tracked through direct construction, the `FromOpenProject` bridge (typed off
  an *empty or absent* `return_type` -- deliberately, since that is the actual
  state of the index), rebind chains, accessor aliases (`lex = fx.LexEntry`)
  and tuple unpacking (`lex, lists = fx.LexEntry, fx.PossibilityLists`). All
  six shapes from the issue's scope table now resolve through the index and
  report the real class and method. Future bridge constructors are typed even
  when the index has never heard of them.
- An **unresolvable** receiver reaching a method name the index declares
  mutating is now reported as a suspected mutation instead of being silently
  certified read-only, with `confidence` degraded to `low` and
  `source: "unresolved_receiver"` on the row. This is what keeps a stale or
  incomplete index a *reporting* problem rather than a safety one: the next
  un-annotated seam nobody anticipated fails closed. The set of mutating names
  is read from the index, not guessed from verb prefixes, so read-only calls on
  untyped receivers stay silent.

Guarded facade writes are unaffected: they still pass `unprotected_writes`
while still requiring `write_enabled`, the project lock and confirmation, per
the #93 split between "is this a mutation" and "was it guarded".

The same receiver generalization was applied to the two other gates that
resolved receivers by name -- the hvo-literal gate (`detect_hvo_literal_args`)
and the casting gate (`detect_casting_needs`) -- which had gone equally blind
the moment a module adopted the documented shape.

Upstream item 1 from the issue is **not** included here and remains worth
doing: annotating `def FromOpenProject(cls, donor) -> "FLExProject":` in
flexicon improves `return_type` coverage broadly. The fix above does not depend
on it, and covers the annotated case too.

### Added: the flexicon template pre-flights its environment

Generated flexicon modules now check the environment they land in before doing
anything, because `FLExProject.FromOpenProject()` makes
`from flexicon import FLExProject` load-bearing for the first time. The module
therefore depends on whatever Python the user's FlexTools install happens to
use -- which is frequently **not** the one on their `PATH`. Two failures become
possible, and neither reads as an environment problem:

- `pyflexicon` absent -> `ImportError` at load, before `Main()` runs; FlexTools
  shows a traceback naming a package, with no remedy.
- `pyflexicon` present but pre-bridge -> imports cleanly, then dies on the first
  line of `Main()` with `AttributeError: type object 'FLExProject' has no
  attribute 'FromOpenProject'`.

Both now produce a plain `[ERROR]` block naming the fix and saying explicitly
that the module is fine and the environment is not. The import is guarded, so
the module still loads and can report rather than dying first. Silent on a
current install -- not even a `report.Info`.

A **third** case gets its own message, and it is the one where the module *is*
what needs editing: a name in the `from flexicon import (...)` list that
flexicon does not export. `except ImportError` cannot tell "no such package"
from "no such name in the package", so a single `try` around both imports sent
that case down the not-installed path -- telling the user flexicon "is not
installed", to run `pip install pyflexicon` for a package they already have,
and that "the module itself is fine". All three were wrong. The two imports are
now guarded separately, and the bad-name branch points at the import list,
names the offending symbol, and says the environment is not the problem. This
is the trap the template's own comment documents (reversal work has no
top-level `ReversalOperations`), so it is a likely path rather than a
hypothetical one; the new tests drive the real import machinery with a real bad
name, which the original set did not -- it only ever substituted a
fully-blocked `import flexicon`.

The staleness check is `hasattr(FLExProject, "FromOpenProject")`, a **capability
probe, never a version floor**. Field evidence for why, from one machine: the
FlexTools interpreter reports `pyflexicon` 4.1.1 via `importlib.metadata` while
`flexicon.version` reports 4.6.0, from the same editable install. A floor
compared against the wrong one of those refuses a working environment.

Separately, generated modules now record the flexicon version they were written
against (`_TESTED_AGAINST`, stamped by `flextools_get_module_template()` at
generation time) and emit a `report.Warning` if they later run somewhere older.
That is advisory only: it runs after the capability gate has passed and cannot
stop the module, so a wrong comparison costs a spurious note rather than a dead
module. Equal, newer, or unparseable versions produce no output.

The template's `REQUIRES: - Flexicon version 2.0+` line was corrected. It was
prose, unenforced, and false -- exactly the hand-maintained-version rot that
argues for stamping the constant rather than writing it by hand.

Two smaller review items on the same code:

- The advisory comparison padded no version tuples, so `(4, 7)` sorted below
  `(4, 7, 0)` and a flexicon reporting `"4.7"` was told it was behind `"4.7.0"`
  -- the same release, reported as older than itself. Both tuples are now
  padded to a common length. Pinned in both directions, since a fix that
  swapped the operands would pass a one-sided test.
- `if not _flexicon_preflight(report): return` is now two lines. It is the
  first statement of every generated module and users copy and edit it, so it
  should look like the rest of the file.

**The pre-flight test file now really does run in a bare checkout**, which its
own docstring had claimed since CP4 landed. It did not: exec'ing the template
ran the real `import flexicon`, and on a machine with pyflexicon installed but
no FieldWorks that raises a bare `Exception("64bit FieldWorks 9 not found")`.
Not an `ImportError`, so the template's guard does not catch it and it came
back out of the exec -- every test in the file failed on the Windows CI runner,
for a reason with nothing to do with the pre-flight. The exec now runs against
a stub `flexicon` installed in `sys.modules`, used unconditionally so a pass on
a dev machine means what it means on the runner. The import machinery itself
still really runs, which is what the bad-name test above needs. A new drift
check ties the stub to the template's import list in both directions, and skips
the half of itself that needs the real package.

That bare `Exception` at import is worth noting for its own sake: it is the
failure class the pre-flight exists to prevent, arriving in a form the
pre-flight does not catch. Widening the guard past `ImportError` is a separate
change and is not made here.

Also fixed the CI lint step, red for the same hidden reason -- it runs after
the test step, so nothing had reached it. `ruff check .` was failing on a dead
`import json` in `build_element_types.py` (removed) and on eight findings in
the vendored `.specify` spec-kit companion scripts (now excluded, the same
treatment `.claude` already gets: not part of the shipped package, and not
ours to restyle). Both predate this branch and are red on `main` too.

### Fixed: casting preflight now has dataflow (#121)

`detect_casting_needs` was two regex passes over raw source lines with no type
inference -- the receiver's type was known only when a syntactic cast alias
(`x = ILexEntry(y)`) happened to be visible. The gate was inverted in practice:
it passed the code that actually crashes and flagged code that was safe.

**The false negative it now catches.** This passed with 0 issues and then
failed at runtime with `'ICmObject' object has no attribute 'HeadWord'` -- the
most common runtime failure in production logs (4 of 10 sessions,
2026-09-02 -> 2026-09-08):

```python
for c in project.LexEntry.GetComplexFormComponents(entry):
    project.LexEntry.GetHeadword(c)
```

Three independent reasons it slipped through: `c` is never the *receiver* of an
attribute access, both real receivers are `project` (hard-skipped), and
`GetHeadword` is not a casting-index property so no known-pattern regex could
match. The root cause was that the index had **no field in which the answer
could be recorded** -- flexicon method records had no `element_type` and no
`polymorphic`.

**The false positives it stops.** `types =
project.Cache.LangProject.LexDbOA.ComplexEntryTypesOA` flagged `LexDbOA`,
because the index-pass regex bound the mid-chain *property* name `LangProject`
as if it were a variable. `n = poss.Name.BestAnalysisAlternative.Text` flagged
`Name`, because the multistring exemption covered the chain's tail but not the
property that heads it. Both are fixed structurally (by unwinding the real AST
chain) rather than with another regex exemption.

#### Index: `element_type` and `polymorphic` on method records

`flexicon_analyzer.py` now AST-resolves each method's *element source property*
-- the LCM collection the returned elements actually come from -- by walking
return statements through `list()`/`tuple()` wrapping, call arguments,
comprehension iterables, and one level of local-variable tracing. A new
`build_element_types.py` post-process (wired into `refresh.py`) resolves that
against the LibLCM index's `target_type` and emits `element_type` plus
`polymorphic` (only when true); both keys are **omitted** when unresolvable, so
every consumer degrades to prior behavior via `.get()`.

Coverage: **142** methods carry `element_type` -- 112 via element-source
resolution, 30 via a `EnumerableWrapper[IX]` / `list[IX]` return-type fallback
that reaches high-traffic methods like `LexEntryOperations.GetAll`. Of those,
**46** are polymorphic and **96** are not.

Deriving from LCM `target_type` rather than docstring prose is deliberate:
`ILexEntryRef.ComponentLexemesRS.target_type` is `ICmObject`, while the
docstring promises "List of ILexEntry or ILexSense objects". The prose
describes the conceptual type; `target_type` is what the object arrives as at
the pythonnet boundary, which is what determines whether a cast is needed.

#### Validator: loop-target binding, two new rules

`detect_casting_needs` takes an optional `api_index` (passed by keyword, so
existing 3-argument test stubs keep working) and binds `for` targets iterating
a flexicon Operations method to that method's element type. The binding is kept
in its own map, never merged into `line_var_cast_types` -- a cast alias means
"this var IS this interface, so access is safe", whereas a polymorphic
`element_type` means the opposite, "this var is only weakly typed". It is capped
at the first reassignment of the name, so narrowing via a cast releases it.

- **Rule A** flags a property access on a polymorphically-bound variable.
- **Rule B** flags such a variable passed to an operation that expects a more
  specific interface -- the headline case. It fires only when the element type
  is genuinely wider than the expected interface and no intervening cast
  applies.

Rule B's premise was verified against flexicon source: `__ResolveObject`'s
object-input branch is unguarded, so passing a `LexSense` to
`project.LexEntry.GetHeadword` really does reach `entry.HeadWord` and fail --
unlike the HVO path, which raises a friendly `FP_ParameterError`.

#### No cast is offered where no cast is legal

For a genuinely mixed collection there is no single valid cast, so Rule A now
teaches the `ClassName`-branch dispatch flexicon's own docstring teaches, and
leaves `cast_interface`/`rewrite` as `None`. It still resolves a concrete cast
when exactly one interface declares the property -- which is the ambiguity
collapse #121 asked for. An interface-spelling heuristic that had preferred
LCM's `IXOrY` names (`ISenseOrEntry`) was removed: across the whole LibLCM
index exactly one entity implements `ISenseOrEntry` -- the wrapper struct
`SenseOrEntry` -- and neither `LexEntry` nor `LexSense` does, so
`ISenseOrEntry(c)` would throw for every element. Relatedly, the
variable-name tie-break (`sense` -> `ILexSense`) no longer applies to a
receiver already proven heterogeneous; proven dataflow beats spelling.

Also removed the dead `casting_index.get("polymorphic_collections", {})` read,
whose result was discarded; the data is still consumed by the discovery path.

## [2.11.0] - 2026-09-08

Index-refresh release: the bundled Flexicon API index is regenerated against
**Flexicon 4.6.0**, the `pyflexicon` floor is raised to match, and the casting
guidance this server emits moves to Flexicon's newly-public `cast_to_concrete`
export.

### Changed: `pyflexicon` floor raised to `>=4.6.0,<5`

The floor was `>=4.3.0`, but the bundled index had drifted well past it: 2.10.0
shipped an index built against Flexicon **4.5.2**, a version that never reached
PyPI. Flexicon tagged 4.5.0/4.5.1/4.5.2 in its changelog but never pushed the
tags, so its `publish.yml` never fired and **4.4.1 was the last version actually
published**. A user installing 2.10.0 therefore resolved Flexicon 4.4.1 while
the index described 4.5.2 -- documenting methods the installed library did not
have.

Flexicon 4.6.0 ships that whole backlog (4.5.0 through 4.6.0) in one published
release, which closes the gap. Raising the floor to `>=4.6.0` makes the shipped
index and the minimum resolvable library the same version for the first time
since 2.9.x. Still a floor rather than a pin, so upgrading FLExToolsMCP
re-resolves to the latest Flexicon.

**This is why the bump is minor, not patch:** a fresh install of 2.11.0 will
pull Flexicon 4.6.0, which contains six behavioural breaking changes relative
to 4.4.1 -- among them `OpenProject(..., ui=None)` now defaulting to
`HeadlessLcmUI`, `FLExProject.SaveChanges()` now raising instead of returning
falsy, and whitespace-stripping name-field writers. None is an API-signature
break; each is a correctness repair. Scripts generated against 4.4.1 that
relied on the old behaviour should be re-checked against Flexicon's own 4.6.0
changelog before upgrading.

### Changed: Flexicon index regenerated at 4.6.0

`flexicon_api_v4.6.0.json`, `flexicon_lcm_bridge_v4.6.0.json`, and
`common_patterns_flexicon-v4.6.0.json` replace their 4.5.2 counterparts (the
4.5.2 files move to `index/python/archive/`). The LibLCM index stays at
**11.0.0** and the stable-FlexLibs index at **1.2.8**; both were re-scanned and
only their cross-reference annotations changed.

Index diff -- 118 entities unchanged, three new methods, none removed:

- `MSAOperations.GetSyncableProperties` / `ApplySyncableProperties` (Flexicon
  #251) -- `MSAOperations` previously had no sync methods at all, so every MSA
  synced across projects with a correct `ClassName`/POS but a permanently null
  feature structure.
- `AllomorphOperations.ApplySyncableProperties` -- Task T8 of Flexicon's
  `specs/feature-structure-sync-gap`. Flexicon's changelog deliberately cites
  the task rather than an issue number: it is an unfiled P0, and filing it is
  an outstanding decision on their side.

### Changed: casting guidance now advertises the public `cast_to_concrete`

Flexicon 4.6.0 re-exported `cast_to_concrete` at the top level (#271), so every
hint this server emits, and the shipped LibLCM template, now say
`from flexicon import cast_to_concrete` instead of reaching into
`flexicon.code.lcm_casting`. Eight sites: two in `handlers/api.py`, two in
`handlers/discovery.py`, two in `server/validators.py`, and the import plus its
comment in `templates/3-liblcm-template.py`.

Guidance text only -- no logic changed. `_FLEXICON_IMPORT_ROOTS` already
accepted the `flexicon` root, so user code written against the new hint
satisfies the discovery gate unchanged. Flexicon documents all three paths
(`flexicon`, `flexicon.code`, `flexicon.code.lcm_casting`) as the same function
object and leaves the deep one supported, so scripts already written against it
keep working.

Flexicon #271 exists because consumers -- this server among them -- reached
into that private path or guessed at public names that never existed. It also
confirms there has never been a `CastingOperations` module, the stale name
behind the `ImportError` in 3 of 10 sessions that motivated 2.10.0's gate work
(#120).

Two test changes came with it, in `tests/test_issue48_inline_casting.py`:

- `_BAD_IMPORT_RE` was pinned to `from flexicon.code.lcm_casting import ...`.
  Moving the template off that path would have left it matching nothing, so
  `test_no_template_imports_ilexentry_from_lcm_casting` would have passed
  **vacuously** -- a silent regression rather than a red test. It now matches
  any `flexicon` / `flexlibs2` module path, which makes it strictly stronger:
  it catches `from flexicon import ILexEntry`, which the old pattern missed.
- New `test_public_and_deep_cast_to_concrete_are_the_same_object` pins the
  #271 equivalence. The advertised public import is now load-bearing for every
  casting hint, so if a future Flexicon makes the top-level name a wrapper or
  drops it, this fails loudly instead of letting the guidance rot.

### Verification

- `pytest`: 1157 passed, 7 skipped, 14 subtests passed.
- `python scripts/validate_integrity.py all`: clean -- 21 tools registered,
  43/43 Operations classes import, flexicon runtime contract reports 4.6.0.
- Flexicon 4.6.0 confirmed installable from PyPI (wheel fetched fresh,
  `pyflexicon>=4.6.0,<5` resolves).
- eval: Tier-2 live task evals NOT run for this release. Index content changed,
  so the pre-release checklist nominally requires them; the Tier-2 runner is a
  documented contract, not a wired harness, and the run is manual.

## [2.10.0] - 2026-09-08

97 commits since 2.9.1. The headline is that **2.9.1 shipped a pre-flight
casting gate that hard-rejects safe read-only code, and advertises a helper
that does not exist** -- ten production sessions between 2026-09-02 and
2026-09-08 hit the `CastingOperations` ImportError in 3 of 10, and a false
`casting_issues_detected` rejection in 4 of 10 (issue #120). Everything below
was already fixed on `main`; this release is what puts it in users' hands.

### Fixed: a guarded write could bypass the write gate entirely (#93 findings (a)/(d))

`build_writeability_payload()` read only `cert['mutating_calls']` /
`'unprotected_liblcm_calls'` and never the `protected_*` lists that
`certify_script_readonly()` already populated, so a correctly-guarded write
(`if modifyAllowed: project.Senses.SetGloss(...)`) produced a
self-contradictory Rung-3 refusal: *"would mutate the database (0 mutation(s)
detected)"*.

A live escalation during the cycle raised the severity well past a wording
bug. For the property-accessor idiom -- `project.<Accessor>.<Method>`, e.g.
`project.CustomFields.CreateField(...)` -- the call never reached Step 1's
Operations-classname index lookup at all, and the line-blind CUD regex missed
the `Create*`-suffixed verb too. The old gate formula
(`(not cert['is_certified_readonly']) or cud_info['is_cud']`) therefore
evaluated **False** for the guarded form: **a schema mutation could run with
`write_enabled=True`, `confirmed=False`, and no lock.**

- **New Step 1c in `certify_script_readonly()`** resolves `project.<Accessor>`
  to its Operations class through the index's `access_path` metadata (the #100
  facade scan below), so these calls get the same authoritative `is_mutating`
  lookup as a literal `*Operations` call, regardless of how the receiver is
  spelled.
- **New `protected_calls` list** tracks guarded wrapper mutations instead of
  dropping them through a bare `pass`.
- **`build_writeability_payload()` now surfaces both `protected_liblcm_calls`
  and `protected_calls`**, so `mutations_detected` is populated for guarded
  scripts and the refusal text stops contradicting itself.

Note: this does **not** close [#105](https://github.com/MattGyverLee/FlexToolsMCP/issues/105).
Its third evidence block is untouched -- `write_certification.mutating_calls_detected`
filters `cert["mutating_calls"]` only and still never reads `cert["protected_calls"]`,
so a guarded mutation can still report `[]` alongside `is_certified_readonly: true`
on a real run.

### Fixed: the pre-flight casting gate over-rejected safe read-only code (#40, #97, #39)

On 2.9.1 the gate is an unconditional `if casting_check["has_casting_issues"]:`.
Safe read-only property access -- `project.Cache.LangProject.LexDbOA.ComplexEntryTypesOA`,
`poss.Name.BestAnalysisAlternative.Text` -- was hard-rejected with
`casting_issues_detected`. Six commits closed this out:

- **Severity is now consulted on read-only runs.** A read-only run rejects only
  if at least one issue is severity `error` (a known-pattern hit, or a genuine
  attribute typo); an all-warning set (index-derived lookup only) proceeds, with
  the issues surfaced as non-blocking `warnings`. **Write-enabled runs still
  hard-reject at every severity, unchanged.** The downgrade is gate-local, and
  records a success signal so the retry-loop detector resets.
- **Variable typing is now assignment- and branch-aware.** Mutually exclusive
  `if`/`elif`/`else` arms casting the *same* variable name to different
  interfaces no longer conflate onto the last arm in document order -- #97
  Bug 2's exact repro (four MSA-interface branches falsely flagged against
  `IMoUnclassifiedAffixMsa`) goes from 4/4 false positives to 0/4.
- **The candidate-union fallback closed a false-*negative* regression.** When
  positional resolution legitimately returns `None` for a name that IS cast
  somewhere, `detect_interface_attribute_typos` had responded by dropping the
  check entirely, silently weakening the #39 typo gate on both read-only and
  write runs. This was the more dangerous of the two P1s found mid-fix.
- **That fallback is scoped to the lexical scope chain.** Walking the whole
  module tree produced 209 false-positive combinations among just 12 common
  interfaces -- issue #40's complaint verbatim, at error tier. Resolution now
  walks the innermost enclosing function outward, then Module, so bare
  module-level snippets still resolve.
- **`validate_only` agrees with the real gate.** Gate 5 rejected on any casting
  issue regardless of severity or `write_enabled`, disagreeing with
  `handle_run_module` after the downgrade above. Both call sites now share one
  extracted predicate so they cannot drift apart again.
- **The `fix` string names the interface that was actually resolved** (#97
  Bug 1). It previously took `defined_on[0]` unconditionally, so a payload
  could print a confident "Cast x to ILexEtymology" **next to a
  `cast_interface: null` on the same payload**. Ambiguous cases now emit a
  two-tier candidates-with-uncertainty message: 2-6 candidates are listed with
  an explicit "alphabetical, not ranked, do not pick the first" warning, and
  **more than 6 candidates emits no interface names at all** -- a 4-of-36
  alphabetical slice used to lead with `ICmAgent` for `Name`, the exact wrong
  pairing #97 cited. Severity, `cast_interface`, `rewrite`, `imports_needed`
  and `available_on` are byte-identical; this is a message-only change.

### Fixed: `CastingOperations` was advertised in five places and does not exist (#112, #113)

Verified at runtime against pyflexicon 4.5.2: `from flexicon import
CastingOperations` raises `ImportError`, and five advisory strings named it --
`handlers/api.py:1621,1636`, `handlers/discovery.py:163,169`, and
`validators.py:3642` (`_POLY_ITERATION_NOTE`, which on 2.9.1 reads *"Items are
heterogeneous; cast each item: concrete = CastingOperations.cast_to_concrete(item)"*).
All five now name the real call form from `flexicon.code.lcm_casting`.

A second, worse defect rode along: **the shipped liblcm template did not run.**
`cast_to_concrete` takes exactly one argument and every call site in the
template passed two, and `ILexEntry` was imported from a module that never
re-exports it. That template is served verbatim by
`flextools_get_module_template(flavor='liblcm'/'advanced')`, so it is code
users execute, not prose. Fixed at all call sites (live code and examples) in
`templates/3-liblcm-template.py`, `templates/00-FLAVOR-GUIDE.md`, and
`templates/README.md`, with a new regex-scanning regression test shown RED
against 7 bad sites before the fix.

### Added: hvo-stability guard and the GUID round trip (#103)

`hvo` is a session-scoped handle -- liblcm renumbers it on every cache load --
yet every `*_or_hvo` parameter accepts one and nothing warned about the risk.
The inverse of `GetGuid` already shipped as `FLExProject.Object(hvoOrGuid)`
(it accepts `str` / `System.Guid` too); it was simply undiscoverable.

- **An `hvo_stability` block in the runtime primer** and a prominent warning in
  the `flextools_run_module` tool description, quoting liblcm's own wording and
  the `project.Object(guid_str)` round trip.
- **`validators.detect_hvo_literal_args()`** -- an AST preflight for a bare
  integer *literal* reaching an `*_or_hvo` parameter or `project.Object(<int>)`.
  A `.Hvo` value read during the same run is never flagged; only a literal,
  which can only have come from a prior session or the FLEx UI.
- **A new gate**, wired like `unprotected_writes` / `nested_unit_of_work`:
  **hard block** (`error_code='hvo_literal_write_risk'`) on write-enabled runs,
  non-blocking warning on read-only runs.
- **The new code is in the response contract**, not just the docs.
  `HvoLiteralWriteRiskDetail` was added to the `AnyDetail` union with
  round-trip coverage, and the error-code count corrected from 17 to 18.
  `ALL_17_CODES` was renamed `ALL_ERROR_CODES` -- a count baked into an
  identifier goes stale every time a code is added, which is how the gap
  survived.

### Fixed: teardown commit failures were reported as success; headless runs could hang (#96, MCP side)

- **The generated runner set `result["success"] = True` before `CloseProject()`
  ran, under a bare `except: pass`.** `CloseProject()` is where the commit
  actually happens (`EndNonUndoableTask` -> `UnitOfWorkService.Save` ->
  `Dispose`), so a commit failure during teardown was invisible and reported as
  a successful write. The `finally` block now captures the exception, demotes
  `success` to `False`, and surfaces the error without clobbering prior messages.
- **`OpenProject()` was generated with no `ui=` argument**, so flexicon fell
  back to the WinForms `FwLcmUI`, whose `ConflictingSave()` is a modal dialog
  with no owner in a headless subprocess -- an indefinite hang. The runner now
  passes `ui=HeadlessLcmUI()`, guarded by `except ImportError` so an older
  flexicon still runs, with the fallback reported via `report.Warning()` rather
  than silently.
- **The primer stopped prescribing an impossible remedy.** #96's root cause is
  structural and the staleness window is *unbounded*, not 18 seconds: a
  non-master peer's commit lands only in the in-memory shared commit log,
  `.fwdata` advances only when the master writes, and a fresh open reads
  `.fwdata` and never replays commit-log records. The primer now states the
  truthful rule with **no promised interval and no retry count** -- there is no
  N that is safe.

`#96` itself remains open: the read-back half needs a live repro.

### Added: shared-mode access probe and verdict-specific lock diagnosis (#93 CP2, CP3)

- **New `server/project_access.py`** composes a per-project access verdict from
  three independently-fallible facts using only the filesystem and stdlib -- it
  never opens a `.fwdata` and never touches LCM: the `.fwdata.lock` JSON payload
  (PID / ProcessName / Timestamp, in real .NET ticks, not Unix epoch), whether
  that PID is actually alive (`ctypes OpenProcess` on Windows, `os.kill(pid, 0)`
  elsewhere -- no `psutil`), and `projectSharing="true"` in
  `SharedSettings\LexiconSettings.plsx`. Verdicts: `free` / `open_shared` /
  `open_exclusive` / `stale_lock` / `held_by_other`.
- **`_diagnose_project_open_error()` now uses that verdict** instead of always
  returning the same generic "Close FieldWorks" hint. `open_exclusive` gets the
  enable-sharing recipe, `stale_lock` names the dead holder PID, `held_by_other`
  gets the holder-collision message, and everything else falls back to the
  previous generic hint.
- **`_pid_is_alive` now checks `GetExitCodeProcess`.** `OpenProcess` succeeding
  is not proof of liveness on Windows -- a handle to an exited-but-not-reaped
  process opens fine, which reported a dead holder as live.
- **Bare-lock false positives swept** out of the `check_project_locked` sibling.

### Fixed: facade-only Operations classes advertised an import that raises (#100, #101)

- **`access_path`.** `MSAOperations` and its peers are reachable only through a
  `FLExProject` facade property and are not re-exported at flexicon's top level,
  so the `from flexicon import MSAOperations` line the server advertised raised
  `ImportError`. The generator now records `entity["access_path"]` from a
  facade-property scan of `FLExProject.py`, and the server prefers it. The
  load-bearing half was the *read* path: `_build_entity_import` had four call
  sites that ignored the index entirely.
- **Non-`ICmPossibility` warning.** `IMoInflAffixSlot`, `IMoInflAffixTemplate`
  and `IMoInflClass` are `CmObject`-derived despite each having its own `Name`
  field -- a naming coincidence with `CmPossibility.Name` that invites a runtime
  `TypeError` when code casts via `ICmPossibility` to read it. Gated on a
  curated set rather than a structural heuristic, which would have
  false-positived on ~76 unrelated entities; `IMoMorphType`, which genuinely
  *is* an `ICmPossibility`, stays unflagged.

### Fixed: `get_navigation_path` never returned a path (#85, #88)

The Wave 3 parent-tracking rewrite left the `target == end` branch
reconstructing the path from `parent[end]`, which is never recorded, so **every
query returned `[]`**. Fixed by seeding the path with the final edge and walking
`parent` backwards from `current`. `IFsFeatStruc -> IFsFeatDefn` now resolves
its genuine 2-hop path, verified live through `server.call_tool`.
`ILexSense -> IFsSymFeatVal` still correctly returns `found: false` -- that is a
missing downcast edge, tracked separately as #91.

### Fixed: the index file-discovery cache served stale results

`versioning._dir_state_token()` keyed the cache on bare
`index_dir.stat().st_mtime`. Filesystem mtime granularity meant rapid writes
could leave `st_mtime` unchanged -- measured **58/200 (29%)** for double-writes,
and **40/300 (13.3%)** stale reads through the real production
`find_versioned_api_file()` / `find_latest_versioned_api_file()`. The token is
now `(dir_mtime, entry_count, max_child_mtime)` from a single `os.scandir()`
pass: a new file changes `entry_count` immediately regardless of mtime
resolution, and an in-place overwrite is caught by `max_child_mtime`.

This is the exact path a release-time `refresh.py` run exercises -- an
out-of-band writer against a running server.

### Changed: bundled flexicon index migrated 4.4.1 -> 4.5.2

Same 118 entities, but **55 of them now carry `access_path`** (4.4.1 carried
zero) -- the #100 fix reaching the shipped index. Retires the superseded 4.4.1
files, matching the one-live-version-per-library convention already followed by
flexlibs (1.2.8) and liblcm (11.0.0).

### Added: dependency cap canary

Upper bounds protect fresh installs from the mcp 2.0.0 class of break, but
`dependabot.yml` scopes pip updates to development dependencies, so a cap
otherwise buys total silence -- nothing reports that it has started excluding a
usable release. `scripts/cap_canary.py` asks PyPI for the latest stable release
of every capped runtime dep and reports which caps now exclude one; the monthly
workflow then force-installs each excluded version past our own pin, runs the
suite against it, and records the verdict. Prereleases and yanked releases are
skipped.

### Fixed: writes are no longer refused on a project FieldWorks has open in shared mode (#93)

The write gate refused on the mere *existence* of a `.fwdata.lock` file
(issue #33). That was an over-correction, and it made the server unusable for
its single most valuable workflow -- editing the lexicon and watching the
change land in the FLEx UI. With `projectSharing="true"` in the project's
`SharedSettings\LexiconSettings.plsx`, LCM promotes the backend to
`SharedXMLBackendProvider` (`LcmCache.cs:211-226`) and our process attaches as
a non-master peer that reads and writes through the shared commit log. The
lock file's presence says nothing about whether that is possible.

- **The gate is now driven by `project_access.probe_project_access()`**
  (added detection-only in CP2, previously wired into
  `flextools_health(verbose=True)` and nothing else). Verdict table:
  `free` -> proceed; `open_shared` -> **proceed**; `stale_lock` (claimed PID
  is dead) -> **proceed**; `open_exclusive` (live FieldWorks, sharing off) ->
  refuse; `held_by_other` (live non-FieldWorks holder) -> refuse.
- **`project_locked` rejections now carry the facts behind the verdict** --
  `verdict`, `sharing_enabled`, `holder_pid`, `holder_process`, `remedy`, and
  `lock_file_path` (response-shape addition; `ProjectLockedDetail` is
  `extra="forbid"`, so the model was extended first). The remedy for
  `open_exclusive` is the enable-sharing recipe, and it states that
  re-submitting the same call re-checks the setting and continues
  automatically. The server still never writes `LexiconSettings.plsx` itself.
  Where the lock file is unreadable and no holder can be identified, the
  remedy says so rather than blaming FieldWorks.
- **Successful runs that went through a live peer or over a stale lock carry
  a `shared_mode` block** naming the verdict, the holder, and the caveat that
  custom-field and writing-system changes are *not* safe from a non-master
  peer.
- **The pre-write backup note is honest about what it is.** With FieldWorks
  attached, the `.fwdata` on disk lags FLEx's unsaved in-memory state, so the
  copy is a floor to fall back to, not a snapshot of what the UI is showing.
- Read-only runs are unaffected: they were never gated, and the probe is not
  even called for them.
- Covered by `tests/test_shared_mode_write_gate.py` (15 tests: the remedy
  builder, every verdict's effect on `handle_run_module`, the read-only
  bypass, and the backup note).

### Fixed: writes silently failed under `undoable=True`; undo machinery removed (#92)

Issue #55 Rung 1 made `undoable=True` the default whenever `write_enabled=True`.
In undoable mode flexicon's `OpenProject` deliberately skips
`BeginNonUndoableTask()` and opens no `UnitOfWork`, so every mutating call
either raised `TypeError` (multi-mutation methods hitting LCM's two-argument
`BeginUndoTask`) or `InvalidOperationException` (simple setters like
`SetGloss`) -- and the generated script's own `except Exception` block then
still reported `result["success"] = True`. No end-to-end test covered this:
`operations.jsonl` had 27 `write_enabled: true` records and zero with
`undoable: true`. Separately, `flextools_undo_last_operation` could never have
worked: LCM's undo stack is a RAM-only `Stack<UnitOfWork>` with no serializer,
and the MCP opens a fresh subprocess per call, so every undo attempt started
from an empty stack.

- **Hardcoded `undoable=False`** at the generated `OpenProject` call, so
  flexicon takes the `BeginNonUndoableTask()` path that actually persists
  writes. Removed the `undoable` session flag and its entire plumbing chain:
  the `flextools_start` tool parameter, `SessionState.undoable`/`is_undoable()`,
  and every warning that referenced it.
- **Removed `flextools_undo_last_operation`** entirely (tool definition,
  dispatch entry, input model, handler, and `undo_subprocess.py`) along with
  the false "can reverse them across MCP sessions" claim and the
  `undo_available`/`redo_available` fields on `flextools_get_session_history`.
- **Removed the dead Feature-3 undo machinery** (`record_operation`,
  `undo_stack`, `redo_stack`, `can_undo`, `can_redo`, `pop_undo`, `pop_redo`,
  `undo_checkpoints`) -- `record_operation` was never called from production
  code, so `get_session_history` had always reported `total_operations: 0`
  regardless.
- **Stopped reporting success over a failed write.** If a run emitted any
  `report.Error()`, the operation is now returned (and logged) as a failure
  (`success: False`, `error_type: "ReportedError"`, `error` describing the
  count) instead of a clean success -- this is a response-shape change for
  any caller that only checked for the absence of a raised exception.
- **Added the end-to-end write test that was never written**
  (`tests/test_issue92_write_path_e2e.py`, marked `requires_flex`, skipped by
  default): drives the real `flextools_run_module` handler to `SetGloss`,
  close the project, reopen it, and assert the value persisted.

### Added: pre-flight gate refuses raw liblcm UnitOfWork nesting (#92 follow-up)

CP1's `undoable=False` hardcode means a write-enabled run now always has one
non-undoable `UnitOfWork` open for the whole session (flexicon's
`OpenProject()` calls `MainCacheAccessor.BeginNonUndoableTask()` once,
closed once at `CloseProject()`). A script that opens its OWN raw
`UnitOfWork` on top of that -- `UndoableUnitOfWorkHelper` /
`NonUndoableUnitOfWorkHelper` (constructor or static `.Do*()` calls), or a
bare `IActionHandler.BeginUndoTask()`/`BeginNonUndoableTask()` -- nests a
second task inside the runner's own; liblcm rolls back the already-open
task first (discarding the whole run's writes) before the second call
throws. Worked previously under the old `undoable=True` default; is a
silent-data-loss regression surface now.

- New AST-based detector `validators.detect_nested_unit_of_work()` --
  flags the raw constructs above regardless of any `if modifyAllowed:`
  guard (a guard does not fix the nesting collision). A construct name
  appearing only in a comment or string literal is not flagged (AST-based,
  not regex/line-blind). flexicon's own `project.Transaction()` /
  `project.UndoableOperation()` wrappers are nesting-aware and never
  false-positive.
- New hard-refuse gate in `handle_run_module`, error code
  `nested_unit_of_work`, wired beside the `partial_module_structure` gate.
  Fires **only** on write-enabled runs: flexicon's `OpenProject()` only
  opens that `UnitOfWork` when `writeEnabled=True`, so a read-only run has
  nothing open to nest into.
- New `NestedUnitOfWorkDetail` response model (`extra="forbid"`) plus
  `AnyDetail` union entry, golden fixture, `TOOL-CONTRACT.md` row, and
  `_ASSISTANCE_HINTS_BY_ERROR_CODE` entry -- the error-code count in
  `docs/TOOL-CONTRACT.md` and `tests/test_response_contract.py` moves from
  16 to 17.
- New `tests/test_nested_uow_gate.py`: one case per sibling construct,
  guard-does-not-suppress, comment/string non-false-positive, an ordinary
  guarded write not refused, and the read-only-not-refused condition above.

### Fixed: `project.LexSense` was blessed by the pre-flight gate but does not exist (#84)

The accessor allowlist was built partly by stripping `"Operations"` off every
`KNOWN_OPERATIONS` entry (`LexEntryOperations` -> `project.LexEntry`). That holds
for 41 of the 43 classes, but invents two accessors `FLExProject` does not have:
`LexSense` (real: `Senses`) and `PhonologicalRule` (real: `PhonRules`).

A phantom in an allowlist is worse than a missing one -- the gate *approves* code
that raises `AttributeError` at runtime. That is how the authoritative flexicon
template came to teach `project.LexSense.GetAllSenses(entry)`, and it also placed
`LexSense` in the candidate pool for its own `AttributeError`, so the runner
offered the failing name back as the top fix.

- **`PROJECT_ACCESSOR_ALIASES`** (`server/constants.py`) records the two
  exceptions; `_project_accessors()` drops them from the legacy union, while
  index-derived properties stay authoritative.
- **Deterministic redirect.** `detect_invalid_project_chains()` rejects a phantom
  with the single correct answer at `match_ratio` 1.0, so auto-fix can apply the
  rewrite instead of guessing via difflib.
- **No more circular hints.** `detect_unknown_attribute_error()` filters the
  failing identifier out of its own candidate list -- if a name were a valid fix
  for itself, no `AttributeError` would have fired.
- **`scripts/check_project_accessors.py`** diffs the shorthands against the
  **live** `dir(FLExProject)` and fails on drift, so a future flexicon release
  that adds a third phantom is caught rather than silently blessed. It
  deliberately does not use the index: that property list enumerates 58 names and
  omits 29 real accessors (`Example`, `WritingSystem`, `Text`, ...), so deriving
  the allowlist from it would delete working accessors.
- **Corpus swept.** The bad idiom had propagated into `curated_recipes.py` (16
  sites), `worked_examples.py`, both affected templates, the `common_patterns`
  index, four `docs/` pages and `CLAUDE.md`.
- **Two further defects found while fixing this**, both pre-existing and both
  strictly worse than the reported bug because they fail at *import* time:
  `2-flexicon-template.py` imported a nonexistent `ReversalOperations`, and
  `3-liblcm-template.py` pulled LCM interfaces from `flexicon.code.lcm_casting`,
  which imports them internally from `SIL.LCModel` but never re-exports them.
- **Argument-type trap pinned.** `GetAllSenses` exists on *both* operations
  classes with different parameters (`LexEntry` takes an entry, `Senses` takes a
  sense) and both duck-type on an `AllSenses` property, so passing an entry to
  the sense flavour returns plausible results instead of raising. The accessor
  gate compares names only and cannot see this, so it is covered by test instead.
- 61 assertions in `tests/test_issue84_project_lexsense_accessor.py`, including
  live import resolution for every shipped template and alias-table drift.

### Added: `workspace_notice` -- warn when the workspace is a source checkout (#90)

Users who find the project on GitHub tend to clone it and then open that clone as
their AI workspace. That measurably degrades the assistant: instead of calling
the `flextools_*` tools it starts *reading the repository* -- grepping the
bundled API index, hand-copying templates, walking `specs/`, and in the worst
case parsing LCM model XML or a project's `.fwdata` directly rather than going
through the API. Installing from PyPI makes this less likely but not impossible,
since the checkout can still be the *working directory* while the code runs from
`site-packages` or a `uvx` cache.

- **New `flextoolsmcp/workspace_check.py`.** Detects when the server's cwd is
  inside a source checkout of FlexToolsMCP, LibLCM, Flexicon, FlexLibs,
  FLExTools, or FieldWorks. Detection is a bounded walk up from cwd (at most 6
  ancestors) doing `exists()` probes for **two** markers per repo -- two so an
  ordinary folder that merely contains a `pyproject.toml` or a `flexicon/`
  subdirectory doesn't trip it. No file reads, no network; safe on the hot path.
  Fails open to *no notice* on any problem, never raising into a tool response
  (same contract as `update_check.py`).
- **The notice carries an `assistant_directive`**, not just prose: explicit
  do-not-read instructions naming the tool to call instead
  (`flextools_search_by_capability`, `flextools_get_object_api`,
  `flextools_get_module_template`), plus a concrete empty-folder suggestion for
  the user (`~/flex-scripts`).
- **Distinguishes the maintainer case.** `running_from_this_checkout` is `true`
  when the executing package also lives in the detected checkout (a source or
  editable install), so the message points at the opt-out instead of implying
  the setup is broken.
- **Three surfaces.** `flextools_start` adds a `WORKSPACE: ...` line to
  `warnings` plus the full `workspace_notice` block; `flextools_health` adds the
  same warning line; the response envelope
  (`build_response_with_context`) attaches the block at most once per process so
  it still lands if `flextools_start` was skipped. Start and health report every
  time -- both are moments where the setup can still be changed.
- **Opt out with `FLEXTOOLSMCP_NO_WORKSPACE_CHECK=1`** (matches
  `FLEXTOOLSMCP_NO_UPDATE_CHECK` semantics), for maintainers who legitimately
  work inside the repo.
- Additive optional envelope field -- **no contract-version bump**, same as
  `update_notice`. Documented in
  [`docs/TOOL-CONTRACT.md`](docs/TOOL-CONTRACT.md#workspace_notice-advisory-block).
- 34 new tests in `tests/test_workspace_check.py` covering every signature,
  the ancestor walk and its depth bound, nearest-match-wins on nested
  checkouts, the no-false-positive cases, opt-out parsing, the once-per-process
  gate (including that a clean cwd does not consume it), fail-open on an
  unresolvable cwd, and all three wiring surfaces.

### Added: `inherited_from` / `total_properties_including_inherited` -- inheritance-aware `get_object_api` (#86)

`get_object_api` previously only listed a type's own (`DeclaredOnly`)
properties and methods -- ancestor-declared members like `IFsClosedValue`'s
`FeatureRA` (declared on a parent interface) were invisible, forcing users
onto fragile workarounds (e.g. parsing `LongName` strings, which breaks on
unordered `ILcmOwningCollection` positional assumptions and on space-bearing
values like Swahili `"NC 4"` / `"NC 1a"`).

- **New `collect_inherited_members()` helper** -- memoized, cycle-guarded walk
  of an entity's `interfaces` closure (already the full transitive closure
  per `liblcm_extractor.py`'s use of .NET `GetInterfaces()`; no recursive walk
  needed for interface ancestors). Merged into `paginate_entity()`'s
  candidate list *before* pagination, filtering, and `summary_only`
  truncation, so all three stay consistent with the merged view.
- **`inherited_from`** tags each merged property/method with its declaring
  ancestor. Own members always shadow an ancestor member of the same name.
- **`total_properties_including_inherited`** and
  **`total_methods_including_inherited`** added at the top level.
  `total_properties` and `total_methods` are both unchanged (byte-identical,
  own-only counts).
- **Scoped to interface entities only** (`I*`) this round -- interface
  merging is collision-free (0 interface-side name collisions found across
  the index); class-side merging needs an override-semantics policy and is
  tracked separately.
- Additive optional fields -- **no contract-version bump**, same pattern as
  `update_notice` and `workspace_notice`. Documented in
  [`docs/TOOL-CONTRACT.md`](docs/TOOL-CONTRACT.md#inherited-member-fields-get_object_api-resolve_property).
- `resolve_property` gained a matching ancestor-aware fallback so a property
  found via `get_object_api`'s merged view also resolves via
  `resolve_property` for the same concrete type -- verified by a
  cross-tool consistency test sampled against `get_object_api`,
  `resolve_property`, and `validators._interface_member_names`.
- Canonical case: `IFsClosedValue` merges 2 own properties to 31 total, with
  `FeatureRA` now visible and tagged `inherited_from`.

### Fixed: `get_object_api` pagination under-reported remaining properties (#86)

`has_more` / `next_offset` were computed from `total_methods` alone, so
`properties` had no pagination signal of its own -- a property-heavy entity
could report `has_more: false` while properties beyond the current page were
still unreachable. `IFsClosedValue` (14 combined methods vs 31 combined
properties) flips this after page 3: the method-only signal goes `False`
while 16 properties remain unpaged.

- **`has_more` is now `methods_has_more OR properties_has_more`**, derived
  from both dimensions instead of methods alone.
- Widened to **all** entities, not only the `I*`-interface entities the
  inheritance merge (see `Added` entry above, #86) targets -- the underlying
  under-reporting bug predates and is independent of that merge, and existed
  for every entity's properties. See `SPEC.md` DEC-7 for the scoping
  rationale and the verification matrix (method-heavy merged, property-heavy
  merged, and non-merged non-interface cases).

## [2.9.1] - 2026-08-10

### Fixed: installs of 2.3.1-2.9.0 were broken against mcp 2.0.0

**Every published release from 2.3.1 through 2.9.0 (11 releases) fails to
import on a fresh install today.** `pyproject.toml`/`requirements.txt`
declared an uncapped `mcp>=1.27.0`; mcp 2.0.0 (released 2026-07-28) removed
the low-level `Server.list_tools()`/`call_tool()` decorator API that
`server.py` depends on, so any fresh `pip install` resolving mcp>=2.0.0
raises `AttributeError` at import time. 2.9.1 is the fix: it caps `mcp` back
to the working 1.x range. No forward port to mcp 2.0 is included in this
release (tracked separately, see `specs/mcp2-compat/deferred-issues.md`).

- **Capped `mcp` to `>=1.27.0,<2`** in `pyproject.toml` and `requirements.txt`.
  Newest available 1.x is 1.29.0, which resolves cleanly with no dependency
  fallout.
- **Fixed error laundering in the lazy server loader**
  (`src/flextoolsmcp/server/__init__.py`). The loader's
  `spec.loader.exec_module(...)` call had no try/except; because it runs
  inside module `__getattr__`, CPython's `IMPORT_FROM` opcode reinterprets
  *any* `AttributeError` escaping it as "attribute absent" and re-raises a
  generic `ImportError: cannot import name`, destroying the real
  traceback/message. This is exactly why the original mcp 2.0 break surfaced
  in CI as `ImportError: cannot import name 'APIIndex'`, naming neither `mcp`
  nor `list_tools`. `exec_module` is now wrapped in `try/except Exception`,
  re-raising a clearly labeled `ImportError` chained via `raise ... from exc`
  so the true cause is always visible.
- **Cached the load failure**, not just the success. A broken `server.py`
  previously re-executed in full on *every* subsequent lazy attribute touch,
  compounding side effects (logging setup, decorator registration) and
  further obscuring the original error. A failed load is now cached and
  short-circuits immediately on later access.
- **Added `list_tools`, `call_tool`, and `server` to the lazy-loader's
  `LAZY_IMPORTS` set.** They were defined in `server.py` but never
  registered for lazy loading, so `from flextoolsmcp.server import
  list_tools` always raised `ImportError: cannot import name 'list_tools'`
  even when `server.py` itself imported fine -- and no runtime tool-count
  check could ever exercise the actual decorator-registration seam that
  broke.
- **Fixed `scripts/validate_integrity.py`'s tool-count check, which had been
  silently AST-only for its entire life.** `check_server_tools()` imported
  from `src.server` (a module that can never resolve -- no `src/__init__.py`
  exists), so every run fell through to the AST fallback and reported
  `"23 tool definitions found (AST) [OK]"` against a completely
  non-importable server under mcp 2.0.0. Repointed to
  `flextoolsmcp.server`, which now performs a real runtime `list_tools()`
  call and reports `"N tools registered (runtime) [OK]"`. The AST path
  remains as a fallback but now prints plainly that it is a DEGRADED check
  when it fires, so it can never again be mistaken for a real runtime
  verification. Also fixed a second dead `src.server` import in the
  flexicon contract check.
- **Fixed `check_runtime_import()`'s silent fall-through to green.** A
  non-zero subprocess exit whose stderr contained neither `ImportError` nor
  `ModuleNotFoundError` (e.g. a bare `AttributeError` from a removed
  decorator API) fell through to `return True` -- an unclassified runtime
  failure now correctly fails the check. The existing, deliberate skip for
  genuine third-party "dependency not installed" `ImportError`s is
  unchanged.
- **Added a wheel-install smoke-test job to `.github/workflows/publish.yml`**
  (`smoke`, gating `publish`). It installs the just-built wheel into a
  completely fresh venv -- no repo checkout, no editable install, no
  `conftest.py` sys.path shims -- and runs
  `list_tools()` from a directory outside the repo, exercising the exact
  lazy-loader + decorator-registration seam that broke. `twine check` only
  validates package metadata and could never have caught this.
- **Added `--continue-on-collection-errors` to both pytest invocations in
  `.github/workflows/test.yml`.** On 2026-08-01 the mcp 2.0 break turned a
  single root-cause failure into "0 of 824 tests ran" because two
  module-level imports failed at collection time; this degrades that to
  "N passed, M errors" (still a non-zero exit) instead of masking the
  entire suite's results.
- New regression tests: `tests/test_lazy_loader_diagnostics.py` (loader
  diagnostics, failure caching, `list_tools` reachability) and
  `tests/test_dependency_bounds.py` (mcp major-version and upper-bound
  regression guards).
- Review trail for this investigation and fix is recorded under
  `specs/mcp2-compat/`.

### Fixed: unprotected mutating scripts returned an opaque error instead of guidance (#82)
- **`run_module` on any unprotected mutating script returned `'str' object has
  no attribute 'get'`** instead of the `unprotected_mutations_detected`
  guidance the preflight had already computed. The writeability gate worked
  correctly -- it detected the mutation and decided to reject -- but the
  handler crashed while *logging* that rejection, so the one message telling
  the caller how to fix their script (`wrap writes in if modifyAllowed:`) never
  arrived. Regression from `a449605` (2.7.x); affected every
  `write_enabled` / `confirmed` combination. `validate_only=True` was
  unaffected and was the workaround.
- **Root cause:** the per-issue DEBUG loop iterated `cert["raw_lcm_patterns"]`
  calling `p.get("line")`, but that list holds plain formatted strings
  (`"CREATE (Create())"`) extended from `detect_cud_operations()["operations"]`
  -- not the `{"line", "method", "context"}` dicts its sibling
  `unprotected_liblcm_calls` holds. Copy-paste from the immediately preceding
  loop, which uses the same field names correctly.
- **Structural hardening:** the reject diagnostics moved into
  `_log_writeability_reject()`, wrapped in a blanket `try/except`. This block
  is diagnostic-only -- it describes a rejection already decided -- so a future
  shape drift in any of the three lists now costs a log line rather than the
  tool result. Also closed a second latent path to the same symptom:
  `get_operations_logger()` is `Optional` and returns `None` before kernel
  init, which would have raised `'NoneType' object has no attribute 'info'` in
  place of the guidance.
- Regression coverage in `tests/test_issue82_writeability_reject_logging.py`,
  including the `raw_lcm_patterns`-is-strings shape contract, so a future
  change to that structure fails loudly instead of silently breaking the log.

## [2.9.0] - 2026-07-22

### Refresh always scans all APIs (per-library filter removed)
- **Removed `--flexicon-only` / `--flexlibs-only` / `--liblcm-only` from
  `refresh.py`.** Every run now scans all available APIs. The scans are
  cross-linked -- the reverse mapping annotates LibLCM entities with their
  FlexLibs/Flexicon wrappers (`python_wrappers`) and pattern extraction
  annotates Flexicon entities (`common_patterns`) -- so refreshing one library
  in isolation left the other libraries' cross-references stale. This regressed
  in 2.8.0, where a targeted `--flexicon-only` refresh silently dropped
  `python_wrappers` from 201 LibLCM entities and `common_patterns` from 9
  Flexicon entities. **Breaking:** any script or automation invoking those
  flags must drop them; the full refresh is the only mode.
- **LibLCM scanning is now best-effort.** A new `liblcm_scannable()` probe
  skips the LibLCM reflection scan (keeping the existing index) when FieldWorks
  DLLs / pythonnet are unavailable, instead of failing the whole refresh.
  Post-processing still re-applies the cross-link enrichment to the retained
  index.
- **Post-processing is no longer gated to full refreshes** (it never should
  have been). Reverse mapping, navigation graph, pattern extraction, and the
  casting index run after every scan; only `--skip-postprocess` suppresses them.
- **Server cold-start self-heal simplified** to trigger a single full refresh
  (the `_REFRESH_ATTEMPTED` dedup means one refresh covers all missing
  indexes). Stale `--*-only` guidance in the runtime version-mismatch warning,
  health warnings, and prefilled bug-report text was updated to the flagless
  command.

### New: `flextools-mcp-refresh` post-install warmup
- **Added the `flextools-mcp-refresh` console entry point**
  (`flextoolsmcp.refresh:main`). Wheels cannot run code at install time, so
  this is the reliable seam to warm the index right after install and avoid the
  server's first-run lazy-refresh delay: run it once after `pip install`, on
  the machine where the server will run. On Windows with FieldWorks it warms
  all three indexes to match the installed libraries; without FieldWorks /
  pythonnet the LibLCM scan is skipped gracefully and the shipped LibLCM index
  is kept.

### Indexes regenerated
- **All bundled indexes regenerated** with the cross-link enrichment restored:
  `python_wrappers` on 201 LibLCM entities, `common_patterns` on 9 Flexicon
  entities, navigation-graph relationships (325 entities), the casting index,
  and the semantic-search embeddings/FAISS index (3579 items).

### Docs & integrity
- Updated `CLAUDE.md`, `CONTRIBUTING.md`, `DEVELOPMENT.md`,
  `docs/VERSIONING.md`, `docs/workflow-detail.md`,
  `docs/workflow-detail-2-foundation.svg`, and `docs/STABILIZATION-STRATEGY.md`
  to the flagless refresh (with the cross-linked-scan rationale and LibLCM
  best-effort note) and to document `flextools-mcp-refresh` as the post-install
  warmup step.
- `scripts/validate_integrity.py` now asserts the removed per-library filter
  flags stay absent from `refresh.py --help`, guarding against reintroduction.

## [2.8.0] - 2026-07-22

### Flexicon 4.3.0 floor + index refresh
- **Minimum `pyflexicon` raised to `>=4.3.0,<5`** (`pyproject.toml`,
  `requirements.txt`). Upgrading FLExToolsMCP now re-resolves to a Flexicon
  that ships the GetAll() behavioral-collection contract by construction, so
  the flexicon-mode advisory removed below is correct for every supported
  install.
- **All bundled indexes regenerated** against the current sources:
  flexicon-mode API + LCM bridge (v4.3.0, sourced from the local clone on the
  dev machine), flexlibs-stable API + LCM bridge (v1.2.8), LibLCM API
  (v11.0.0), and the semantic-search embeddings/FAISS index (3579 items).

### GetAll() behavioral-collection contract (issue #37)
- **Flexicon-mode index regenerated to v4.3.0.** Flexicon 4.3.0 upgraded
  `EnumerableWrapper` (`flexicon/code/BaseOperations.py`, commit 205d5a9) to
  cache its materialized list on first access, so `.GetAll()` results now
  safely support `len()`, subscript/slice, and repeat iteration — a genuine
  behavioral collection, not a one-shot generator. Docs, worked examples, and
  curated recipes are reframed around this contract instead of the previous
  "materialize with `list(...)` to be safe" idiom.
- **Reverses the cycle-2 flexicon-mode overreach.** An earlier synthesis
  (`specs/getall-contract/SPEC.md`) proposed a Level-3 validator rule that
  flagged unsafe `GetAll()` idioms in flexicon mode, keyed off a
  reconciled `returns.type` container-shape taxonomy. That taxonomy is
  obsolete now that flexicon 4.3.0 makes the flexicon-mode result safe by
  construction; the flexicon-mode advisory has been removed.
- **Validator (`server/validators.py`) rescoped to `flexlibs_stable` mode
  only.** `detect_getall_unsafe_idiom` now flags raw one-shot
  iterators/generators in the stable FlexLibs API only (e.g.
  `LexiconAllEntries`, `LexiconAllEntriesSorted`, `ObjectsIn`,
  `GetLexicalRelationTypes`, `ReversalEntries`, `TextsGetAll`) via a
  hand-curated, docstring-sourced allowlist, and is silent in flexicon mode.
  Wired into `handlers/execution.py` alongside the other advisory detectors.
- **v4.2.1 index files archived**, still resolvable for projects pinned to
  older Flexicon versions (`src/flextoolsmcp/index/python/archive/`,
  `src/flextoolsmcp/index/archive/`).

## [2.7.0] - 2026-07-20

### Proactive update notice (issue #79)
- **The server now tells users when a newer `flextools-mcp` is on PyPI.**
  Neither `uvx`, `uv tool`, nor `pip` proactively notifies, so users got
  silently stuck on old builds — a stale `uvx` cache served a pre-2.6.2 build
  (Flexicon 4.1.2) even after 2.6.2 shipped, and a blanket `pip install -U`
  upgraded Flexicon but left the MCP behind. The notice rides out on the
  tool-response envelope as an optional `update_notice` block so the assistant
  relays it, with the correct upgrade command for each install method
  (`uvx flextools-mcp@latest` / `uv tool upgrade flextools-mcp` /
  `pip install -U flextools-mcp`).
- **Cheap and safe by construction.** The PyPI check is cached in
  `~/.flextoolsmcp/update-check.json` (~24h TTL) and runs on a background daemon
  thread; the tool-call path only reads the cache and never blocks on the
  network. Any failure fails open to no notice and never raises into the op
  path. Emitted at most once per process. Skipped for source/dev installs.
- **Opt-out:** set `FLEXTOOLSMCP_NO_UPDATE_CHECK=1` to disable entirely (no
  thread, no notice).
- Additive-optional envelope field — does **not** bump the tool contract
  (still `tool-responses/1.0`). Documented in
  [`docs/TOOL-CONTRACT.md`](docs/TOOL-CONTRACT.md#update_notice-advisory-block).

## [2.6.2] - 2026-07-20

### Raise the `pyflexicon` floor to 4.2.0
- **`pyflexicon` is now required at `>=4.2.0,<5`** (was `>=4.1,<5`). The bundled
  Flexicon API index and generated-script guidance track the 4.2.x surface, so
  the floor is raised to keep installs resolving to a matching library. Still a
  floor (not a pin), capped at the next major. Mirrored in `requirements.txt`.

## [2.6.1] - 2026-07-13

### Ship stable `flexlibs` as a runtime dependency
- **`flexlibs` (the shallow/stable cdfarrow wrapper) is now a declared
  dependency**, alongside `pyflexicon`. It is small and its only dependency
  (`pythonnet`) was already required, so bundling it costs little and means the
  stable-flexlibs index now matches the installed library out of the box (the
  bundled index is `flexlibs_api_v1.2.8` and PyPI `flexlibs` is 1.2.8). It also
  makes the runtime `--flexlibs-only` refresh path viable without a manual
  install, so the 2.6.0 version-mismatch handling can regenerate a matching
  index if the installed `flexlibs` ever drifts. Floor `>=1.2.8`, capped `<2`.
  Verified conflict-free: `flexlibs` and `pyflexicon` both require
  `pythonnet<3.1,>=3.0.3`, satisfied by our existing `pythonnet>=3.0.0`.
  Mirrored in `requirements.txt`.

## [2.6.0] - 2026-07-13

### Handle installed API versions that don't match the shipped index
- **Version mismatch now triggers a refresh-to-match, then a warned fallback.**
  `_load_library_api_index` previously only auto-refreshed when the index dir
  was *empty*; on a version mismatch it silently served the latest shipped
  index, so a user whose LibLCM / Flexicon / FlexLibs was newer *or* older than
  what shipped got a doc surface that didn't match their library, with no signal.
  Now, when no exact-version index exists for the detected installed version, the
  loader (1) attempts one refresh to regenerate a matching index from the
  installed library, and (2) if that can't reproduce it, serves the nearest
  shipped index but emits a WARNING naming the installed version, the served
  version, and the mismatch direction (older/newer), with the exact
  `python -m flextoolsmcp.refresh --<lib>-only` command to regenerate.
- **Refresh is attempted at most once per library per process** (`_REFRESH_ATTEMPTED`
  guard) so startup and repeated loads never shell out repeatedly when a user's
  version simply isn't reproducible on their machine (e.g. no FieldWorks DLLs for
  LibLCM). Refresh needs the extraction source — pyflexicon (always present),
  FieldWorks DLLs (LibLCM), or flexlibs — so it degrades gracefully to the warned
  fallback when the source is unreachable.
- **Fixed a latent cache bug on the refresh path.** `find_versioned_api_file`
  caches negative results, so the pre-existing "refresh then re-search" flow
  could return a stale `None` and fail to load a just-written index. The new
  `_try_refresh_once` clears the file-discovery cache after a successful refresh.
- New `tests/test_version_mismatch.py` covers exact match (no refresh), installed
  newer/older than shipped (both warning directions), refresh-regenerates-match,
  missing-entirely, the once-per-process guard, and crash-proof version parsing.

### Exclude index `archive/` from the built wheel (packaging)
- `include-package-data=true` + the `index/**/*` package-data glob swept the
  `archive/` subdirs (old index versions kept for local diffing) into the wheel;
  MANIFEST.in `prune` only trims the sdist. Added
  `[tool.setuptools.exclude-package-data]` so wheel and sdist both ship zero
  archive files while all live indexes remain.

## [2.5.0] - 2026-07-13

### Renamed the bundled Python-API index dir: `index/flexlibs` -> `index/python`
- **The folder held both wrapper libraries, so its name was misleading.**
  `src/flextoolsmcp/index/flexlibs/` contained the **Flexicon** index
  (`flexicon_api_v*`, `flexicon_lcm_bridge_v*`) *and* the **FlexLibs-stable**
  index (`flexlibs_api_v*`, `flexlibs_lcm_bridge_v*`). It is now
  `index/python/`, mirroring the sibling `index/liblcm/` (C#) — the taxonomy is
  now cleanly by source language: `python/` = the two Python wrappers, `liblcm/`
  = the C# API. All path references updated in `server.py` (API + LCM bridge
  loaders), `refresh.py`, `build_embeddings.py`, `build_reverse_mapping.py`,
  `extract_patterns.py`, `archive_old_versions.py`, plus `.gitignore`,
  `MANIFEST.in`, and the CI comment in `test.yml`.
- **Fixed `test_script_certification` to resolve the index like production.**
  It hardcoded the stale repo-root path `index/flexlibs/` (broken since the
  `src/` layout move), so all 21 of its cases errored locally with
  `FileNotFoundError` and were only green in CI because they're deselected via
  the `requires_flex` marker. It now uses `get_index_dir() / "python"`; the full
  suite is green locally (443 passed).

### Installation docs — uvx PATH troubleshooting
- **Documented the "`claude mcp add` succeeded but the server won't start"
  failure mode.** `claude mcp add` only *records* the launch command and reports
  success even when `uvx` is missing or not yet on PATH; the failure surfaces
  later, when the AI assistant tries to *launch* the server (it hangs, fails to
  connect, or shows no `flextools_*` tools). SETUP.md gains a prerequisite step
  to verify `uvx --version` in a **fresh** shell — the uv installer's PATH change
  does not reach already-open terminals or GUI apps until a new shell or reboot —
  an IMPORTANT callout at the quick-install step, and a Troubleshooting section
  covering uvx-not-found, the absolute-path fallback, and a uvx-free
  `pip install` + `python -m flextoolsmcp` alternative. README.md links to it.
- **Normalized package vs. server-alias naming.** Fixed four spots in README.md
  that passed the no-hyphen `flextoolsmcp` to `uvx`/`pip`/`uv tool`. The PyPI
  package is `flextools-mcp` (hyphenated); `flextoolsmcp` (no hyphen) is only the
  MCP server alias, the importable Python module, and the `~/.flextoolsmcp/` data
  directory.

### Inline casting metadata into get_object_api (issue #48)
- **Casting requirements now surface at discovery time.** Casting knowledge
  previously lived only in `flextools_resolve_property`, a tool the model
  reliably ignored (#22). `get_object_api` — the discovery gate's *required*
  step — now joins each property against the loaded casting index: properties
  that need a pythonnet cast gain `requires_cast` / `cast_to` / `cast_example`,
  polymorphic collections gain `polymorphic` / `iteration_note`, and a
  top-level `casting_notes` counter summarizes the entity. The model writes
  cast-correct code on the first draft instead of learning it from a rejection.
- **One vocabulary, taught earlier.** `cast_example` is produced by the same
  `_pick_cast_interface` + `_build_cast_rewrite` generator that powers
  `casting_issues[*].rewrite` (#21), so discovery-time guidance is
  byte-identical to what a preflight rejection would emit. The new
  `build_property_cast_example()` / `annotate_properties_with_casting()` helpers
  in `validators.py` are the shared join, called from both `paginate_entity`
  (get_object_api) and `_inline_discovery_docs` (discover-and-run rejections),
  keeping the two paths consistent.
- **No divergence, no bloat.** The annotation mirrors the rejection path's
  flow-independent skips (`Guid`/`Hvo`/`ClassID`/`ClassName` and multistring
  value accessors, #40) so it never re-introduces needless casts. Only
  index-member properties are annotated (entities with none come back
  byte-identical), and `summary_only` (#11) emits just the top-level counter.
- **resolve_property drops off the happy path.** Tool descriptions updated:
  `get_object_api` advertises the inline casting info; `resolve_property` is
  now scoped to chained/ambiguous receivers (`rewrite: null` cases) and
  debugging. New `tests/test_issue48_inline_casting.py` covers annotation,
  golden byte-identity, summary mode, safe-member parity, and the
  cast_example ↔ rewrite consistency contract.

## [2.4.0] - 2026-07-11

### MCP spec compliance — outputSchema (issue #54 follow-up)
- **Disabled the `outputSchema` advertisement in `list_tools()`.** The
  tool-responses/1.0 work wired `list_tools()` to advertise `outputSchema` for
  the three tools carrying an `output_model`, but `call_tool()` returns text-only
  (`json_response()` -> `[TextContent]`) and never populates `structuredContent`.
  Per MCP spec 2025-06-18, a tool advertising `outputSchema` MUST return matching
  `structuredContent`, and spec-compliant clients (e.g. Claude Code) reject
  text-only responses — so `run_module` / `get_object_api` / `search_by_capability`
  failed for those clients while all other tools worked. The advertisement is now
  commented out; `output_model` metadata is retained for the follow-up.
  `tests/test_response_contract.py::TestOutputSchema` inverted to guard that no
  tool advertises `outputSchema` until structured content is returned.
- **Operational note:** requires an MCP server **restart** to take effect (the
  running process does not hot-reload). Returning `structuredContent` so the
  schemas can be re-advertised is tracked in `docs/TODO.md` ("Option B"), scoped
  to the low-level `mcp` tuple return — NOT a FastMCP migration.

### Session identity + read-only auto-discovery (issues #42, #47)
- **#42 -- Session-state identity / discovery-state leak fixed**: `SessionState`
  is a long-lived global singleton; without an identity key it leaked discovery
  state across logical sessions. `session.py configure()` rewritten to branch on
  explicit `session_id` kwarg / `new_session=True` / first-configure /
  `project_name` change / else keep-current-no-wipe (project-anchored identity,
  `auto-<project|uuid>` minting). Fixes the P0 where the production start path
  minted a fresh uuid every call and wiped discovery on every `flextools_start`
  (broke the supported mid-session restart flow, issue #9). `admin.py` removes
  dead `session_state.session_id = ...` direct assignment; passes `project_name`
  through; adds unknown-kwarg warning guard. New `TestProductionPathSessionContinuity`
  covers the same-project-restart-preserves case that would have caught the P0.
  `#42.2` (missing Operation End on writeability reject) was already correct --
  locked with a regression test only.
- **#47 -- Read-only auto-discovery**: introduces a separate
  `auto_discovered_apis` set that the write gate never reads (write-gate
  isolation -- `validators.py:851` reads only `validated_apis`; write never
  auto-discovers). Resolve criterion uses the api_mode-specific entity table plus
  accessor-to-ops map (rejects naive `f"{name}Operations"` fallback). Cap 5 on
  read runs, 0 on write runs. Success path attaches Optional `auto_discovered` /
  `_inline_discovery` / `discovery_note` on `RunModuleSuccess`. The
  `KEY_INLINE_DISCOVERY = "_inline_discovery"` leading underscore is intentional:
  matches existing reject-payload `_inline_discovery`/`_assistance` keys that
  clients already parse.
- `docs/TOOL-CONTRACT.md` updated with the 3 new `RunModuleSuccess` Optional
  fields (`auto_discovered`, `_inline_discovery`, `discovery_note`).
- +26 tests (400 passed, 21 deselected). New `tests/test_issue42_session_identity.py`
  and `tests/test_issue47_auto_discovery.py`.

### Validator + auto-fix (issues #40, #46)
- **#40 — Casting whitelist false-positive fix**: `detect_casting_needs()` no
  longer over-rejects receivers whose var is a known cast-alias or a
  multistring-value accessor (`BestAnalysisAlternative`/`BestVernacularAlternative`/`.Text`),
  and never flags `project.*` wrapper calls. The advanced `casting_index` loop
  now consults `cast_aliases.get(obj_var)` against
  `_extract_interface_names(defined_on)` before flagging. Conditional-safe
  members (`LexemeFormOA`/`AnalysesRS`/`Wordform`/`Form`/`FreeTranslation`)
  pass only when a cast-alias proves the receiver type.
- **#46 — Fix-and-run auto-apply**: on read-only runs with `auto_fix` on, the
  preflight now auto-applies SAFE casting rewrites (exactly-one concrete target)
  and single-candidate typo corrections (difflib ratio >= 0.9), re-parses +
  re-runs the full preflight on the patched code, and executes in the same call,
  returning `auto_fixes_applied` + `auto_fix_note`. Write runs keep the hard
  rejection unconditionally. Cap of 5 fixes. New config kill switch
  `auto_fix_enabled`; `RunModuleInput.auto_fix` per-call override. Collision
  pre-pass rejects the whole fix set if any `(line, found_at)` key repeats.
- +5 tests (374 passed, 21 deselected). New `tests/test_auto_fix.py` covers
  re-parse-failure degradation, same-line collision rejection, and accumulator
  cap. 3 new golden response fixtures for auto-fix applied/not-applied paths.
  New `RunModuleSuccess` Optional keys (`auto_fixes_applied`, `auto_fix_note`)
  compose with the #54 contract.

### Tool contract (issue #54)
- **tool-responses/1.0 contract introduced**: all tool responses are now stamped
  with `_contract: "tool-responses/1.0"` and a unique `op_id`. Success responses
  carry a typed envelope; error responses carry flat canonical fields
  (`error_code`, `message`, `hint`, `error_details`) plus a per-code `detail`
  object validated against one of 16 Pydantic models.
- **outputSchema exposure — DEFERRED** (see "MCP spec compliance" below): the
  `output_model` metadata is retained on `ToolDef` for `run_module`,
  `get_object_api`, and `search_by_capability`, but the `list_tools()`
  advertisement of `outputSchema` is currently disabled. Advertising a schema
  without returning matching `structuredContent` breaks spec-compliant clients;
  re-enabling is tracked as a follow-up (docs/TODO.md, "Option B").
- **Dual-emit deprecation of nested `error{}` shape**: the legacy
  `error: {code, message, hint}` sub-object is still emitted alongside the
  new flat fields for backward compatibility. Scheduled for removal at
  `tool-responses/2.0`.
- New: `src/flextoolsmcp/server/response_models.py` (BaseEnvelope,
  RejectionEnvelope, 3 success models, 16 detail models, AnyDetail union,
  `validate_detail()`).
- New: `tests/test_response_contract.py` (94+ tests), 16 golden fixtures in
  `tests/golden/responses/`, `tests/make_golden.py` drift tooling.
- New: `docs/TOOL-CONTRACT.md` — full contract reference.

### Telemetry
- **First-pass-green metric now emitted** (issue #50): every `run_module`
  operation writes one JSONL line to `operations.jsonl` alongside the
  existing prose `operations.log`.  Fields include `ts`, `op_id`, `seq`,
  `project`, `write_enabled`, `source_kind`, `user_intent`, `code_sha256`,
  `code_bytes`, `code_lines`, `outcome` (ok / preflight_reject /
  runtime_fail / timeout), `error_code`, `preflight_gate`, `duration_s`,
  `auto_fixes_applied`, `auto_discovered`, `assistance_triggered`,
  `info_count`, `warning_count`, `error_count`.
- JSONL is written from inside the three close functions
  (`_log_operation_end_success`, `_log_operation_failure`,
  `_log_preflight_reject`) -- NOT at the ~12 individual call sites -- so the
  prose log and JSONL file can never diverge.
- `operations.jsonl` rotates at 10 000 lines to `operations.jsonl.1`.
- `get_operation_logs` statistics block now includes `first_pass_green_rate`,
  `turns_to_green_median`, and `rejects_by_error_code` (top 5) computed from
  JSONL.
- New CLI: `scripts/green_report.py` (stdlib only) -- reads one or more
  JSONL files, computes first-pass green rate, turns-to-green (median + p90),
  abandoned groups, retry-loop trips, and a reject-by-error-code table with
  optional `--previous` trend diff.  `--json` flag for CI integration.

### CI / Robustness (issue #57)
- **Added `.github/workflows/test.yml`**: runs on every push and pull_request.
  Windows-latest matrix over Python 3.10 and 3.12; steps are `pip install -e .[dev]`,
  `python scripts/validate_integrity.py all`,
  `pytest -m "not requires_flex" --cov=src/flextoolsmcp --cov=server --cov-fail-under=25`,
  and `ruff check .`.  A second job `test-linux` runs on `ubuntu-latest`
  (needs: test) with the same pytest surface.  Both jobs deselect
  `requires_flex` because GitHub runners have no FieldWorks install or
  generated Flexicon index.
- **Added `pytest-cov` and `ruff` to `[project.optional-dependencies] dev`** in
  `pyproject.toml` so `pip install -e .[dev]` sets up CI tooling in one step.
- **Fixed `tests/conftest.py`** path setup: added `src/flextoolsmcp/` to `sys.path`
  so legacy `from server.xxx import` statements resolve correctly alongside the
  installed `flextoolsmcp` package form.
- **Subprocess process-tree kill** (`server/subprocess_helpers.py`): on timeout,
  `run_script_async` now kills the entire process tree (`taskkill /T /F /PID` on
  Windows, `os.killpg` on POSIX) instead of only the immediate child.  Prevents
  grandchildren spawned by pythonnet / FLExInit from orphaning and holding
  `.fwdata` locks.  Regression test added: `tests/test_subprocess_tree_kill.py`
  (Windows-only, no live FLEx required).
- **Startup stale-lock sweep** (`server/project_discovery.sweep_stale_locks()`):
  at server startup, all `.fwdata.lock` files under the FieldWorks projects
  directory are logged at WARNING level and surfaced via `validate_server_state()`
  warnings; the `flextools_run_module` preflight health check picks them up.
  Detection only -- no deletion.  Tests in `tests/test_startup_lock_sweep.py`.
- **Added `requires_flex` pytest marker** in `pytest.ini`, applied to
  `test_script_certification.py` (needs a generated Flexicon index that CI
  runners lack) so both CI jobs deselect it with `-m "not requires_flex"`.
- **Fixed `src/flextoolsmcp/server/kernel.py` dual-import guard**: under the
  bare-`server` layout `__package__ == "server"` (truthy) wrongly took the
  relative-import branch, raising "attempted relative import beyond top-level
  package" and failing `test_undo_wiring.py` in CI.  Guarded with
  `__package__.startswith("flextoolsmcp")` so the relative branch is used only
  when installed as the package.
- **Repointed and un-quarantined `tests/test_mcp_tools.py`**: it loaded the
  pre-src-layout `src/server.py` via importlib; repointed to
  `src/flextoolsmcp/server.py` -- 18 tests now pass with no marker (the earlier
  `requires_flex` mark was masking a stale path, not a FieldWorks dependency).
- **Scoped ruff to fatal-only** via `[tool.ruff.lint] select = ["E9","F63","F7","F82"]`
  in `pyproject.toml` (matches the pre-commit hook); the incremental
  lint-widening in issue #57 part 2 broadens this set in follow-up PRs.
- Added `.coverage` and `htmlcov/` to `.gitignore`.

### Packaging / Policy (issue #57)
- Added `src/flextoolsmcp/py.typed` marker (PEP 561) and registered it in
  `[tool.setuptools.package-data]` so it ships inside the wheel.
- Capped `pyflexicon` at `>=4.1,<5` in `pyproject.toml` and `requirements.txt`
  to prevent silent breakage on a future major-version bump.
- Added `.github/dependabot.yml` for monthly Dependabot checks on
  `github-actions` and `pip` (dev dependencies).
- Added `SECURITY.md`: supported-versions table, private-report contact via
  GitHub Security Advisories, and explicit TRUST-MODEL statement clarifying
  that `write_enabled` gating is a safety feature (not a security boundary)
  and the server is intended for localhost/stdio use only.
- Added `CONTRIBUTING.md`: dev setup (`pip install -e .[dev]`),
  `pre-commit install`, refresh and test commands, and PR rules (CHANGELOG
  entry required; extractor changes need index diff; payload-shape changes
  need golden-file regen).
- Appended ROLLBACK PROCEDURE and PRE-RELEASE CHECKLIST sections to
  `RELEASING.md` (previously absent; flagged by STABILITY-SURVEY sec 5).

## [2.3.3] - 2026-07-06

### Index
- **Refreshed the Flexicon API index to v4.1.2** (v4.1.0 and v4.1.1 moved to
  `index/flexlibs/archive/`); regenerated the matching `common_patterns` and
  `flexicon_lcm_bridge` artifacts.
- **Refreshed the LibLCM v11.0.0 index**: added `PhonemeOperations` wrapper
  mappings and cleaned up stale `IDataReader` wrapper entries; regenerated the
  LibLCM reverse-mapping index.

### Internal
- Build scripts (`build_casting_index`, `build_navigation_graph`,
  `build_reverse_mapping`) now resolve their input/output locations via
  `get_index_dir()` instead of hardcoded package-relative paths, so they honor
  the user-overlay index directory.

## [2.3.2] - 2026-07-04

### Documentation
- Rewrote **SETUP.md** around the `uvx flextools-mcp` one-liner (source install
  kept as a dev option); fixed **README** update instructions and anchor links.
- Corrected commands and clarified the bundled-vs-`~/.flextoolsmcp/index` overlay
  location in **docs/VERSIONING.md**.
- Added an **INNOVATIONS.md** chapter on the zero-setup distribution and
  self-healing index overlay.
- Archived the historical v1.3.0 implementation plan to `docs/archive/`.

## [2.3.1] - 2026-07-04

### Packaging
- **Published to PyPI as `flextools-mcp`** — installable/runnable with a single
  `uvx flextools-mcp` (or `pip install flextools-mcp`); no clone or manual
  dependency install. The indexed API documentation ships inside the wheel as
  package data. Restructured to a `src/flextoolsmcp/` src-layout with a
  `pyproject.toml`, console-script entry points (`flextools-mcp` /
  `flextoolsmcp`), and a `python -m flextoolsmcp` module runner.
- **`pyflexicon` is now a runtime dependency**, so the deep FieldWorks wrapper
  is installed automatically and re-resolves to the latest on upgrade.
- **User-writable state consolidated under `~/.flextoolsmcp/`** (logs, saved
  skeletons, model cache, and runtime-refreshed indexes) so it persists across
  upgrades and is never written into the installed package. Runtime
  auto-refresh writes a user-overlay index seeded from the bundled one; source
  checkouts still refresh the in-tree index for committing.
- Added a tag-triggered GitHub Actions release workflow using PyPI Trusted
  Publishing (OIDC), plus `RELEASING.md`.

## [2.3.0] - 2026-07-04

### Changed
- **Renamed `flexlibs2` -> `flexicon`.** The deep wrapper is now the `flexicon`
  package, installed via `pip install pyflexicon` (imported as `flexicon`)
  instead of being cloned as a sibling repo. Updated across the MCP: analyzer
  module (`flexicon_analyzer.py`), index prefixes (`flexicon_api`,
  `flexicon_lcm_bridge`, `common_patterns_flexicon`), refresh CLI
  (`--flexicon-only` / `--flexicon-path`), the `FLEXICON_PATH` env var, and all
  templates/docs. The `api_mode` / `library` / template-flavor value is now
  `flexicon`; the previous `flexlibs2` value is still accepted as a **deprecated
  alias** (normalized to `flexicon`). Version detection now reads the
  `pyflexicon` distribution. Dated entries below retain their original
  `flexlibs2` naming for historical accuracy.

## [2.2.1] - 2026-07-01

June session-log triage follow-up: index freshness + discoverability.

### Features
- Canonical-intent map for `search_by_capability`: high-frequency intents now surface the exact flexlibs2 method as the top result instead of the assistant guessing nonexistent accessor/method names. E.g. "get sense part of speech" -> `LexSenseOperations.GetPartOfSpeechObject`, "list texts" -> `TextOperations.GetAll`, "wordform gloss" -> `WfiGlossOperations.GetForm`. Canonical hits are flagged (`canonical_intent`), counted (`canonical_matches`), and recorded so the same search also satisfies the discovery gate (#45)

### Fixes
- Library version detection now honors a live module `version` attribute (flexlibs2's convention), preferring it over stale `importlib.metadata`. Previously the server detected 3.0.0 from pip metadata while flexlibs2 4.0.1 was on the path, so it loaded a mismatched (archived) index and false-rejected valid code such as `ApplySyncableProperties` (#38)
- Reindexed flexlibs2 to v4.0.1 so recently-added methods (`ApplySyncableProperties` on all 13+ Operations classes, etc.) are present in the API index (#38)

### Tests
- Reconciled a stale #20 test with #31's implicit-discovery behavior (`from flexlibs2 import X` counts as discovery)

## [2.2.0] - 2026-06-30

Follow-up release from the June session-log audit: a validator-cluster fix pass (#39-#45 triage), the #16/#30-#36 batch, plus shared-mode, indexing, and session-header improvements.

### Features
- `report.Result(data)` for structured payload return from user scripts (1 MB cap, JSON-validated, distinct sentinel) (#35)
- Expose `lcm_undoable_action_count` after write-enabled runs so callers can see how many actions the UoW actually committed (#16)

### Fixes
- Casting gate no longer over-rejects safe read-only access: whitelist universally-safe members (`Guid`/`Hvo`/`ClassID`/`ClassName`), skip method calls on Operations-class aliases (`segOps.IsLabel(seg)`), and normalize the cast-alias `defined_on` check so a cast satisfies the property even with a descriptive `"(raw LCM)"` qualifier (#40)
- Missing-imports gate is now AST-based, so parenthesized / multi-line `from flexlibs2 import (...)` no longer false-rejects (#41)
- Attribute typos prefer Python's authoritative `Did you mean: 'X'?` suggestion (surfaced as `did_you_mean`) instead of routing through the cast path with an unactionable "resubmit" hint (e.g. `ILexDb.EntriesOC` -> `Entries`) (#39)
- Writeability preflight reports a consistent mutation total: a raw `set_String` now counts toward `mutating` instead of logging the self-contradictory `mutating=0 ... raw_lcm=1` (#44)
- `unprotected_writes` no longer false-positives on `Get*`/`Find*`/`Is*`/`Has*`/`Count*`/`Contains*` methods absent from the API index (#32)
- Fuzzy validator replaces the blanket `Lexicon*` skip with an enumerated method set from the FLExProject index, so typos like `LexiconGetSenses` still get caught (#34)
- Casting typed-receiver hint extended to `_obj`/`_typed`/`_cast` variable-name variants (#30)
- `undiscovered_entity` no longer rejects operations classes on a fresh session when they are explicitly imported (`from flexlibs2 import X` treated as implicit discovery) (#31)
- Runtime `PolymorphicAttributeError` embeds the resolved cast `rewrite` + `imports_needed`, matching the preflight payload (#36)
- Read-only operations are allowed on FLEx-open projects (shared mode): the `.fwdata.lock` preflight gates on write intent only, letting LCM arbitrate concurrent reads; exclusive writes still fail fast (#33)
- Enhanced domain and search synonyms for inflection and related terms

### Performance
- `get_object_api` thin-indexes Operations classes: returns name/signature/one-line description by default (full bodies still returned when `method_filter` narrows the request)

### Observability
- Session header now populates the FlexToolsMCP version (from the repo `VERSION` file) and the LibLCM version (read from `SIL.LCModel.dll` on disk), instead of logging `(unknown)` when run from source

## [2.1.0] - 2026-05-30

Coverage-test post-mortem follow-up: 13 issues (#17-#29) opened from the May 22 session-log audit, all landed. Three follow-up corrections from lex-domain review also included, plus a late-cycle Seth-session false-positive fix and a logging-gap audit pass.

### Features
- Capture `user_intent` on `run_module` / `start_module`; echo into operations log (#18)
- Skeleton storage closet -- auto-capture working helpers, retrieve via `find_examples` + new `list_skeletons` tool (#24)
- Cap `report.Info` messages at 100 (first-50 / last-50 slice + truncation marker) (#25)
- Detect retry loops and code-size oscillation; surface `_assistance` hint on rejections (#28)
- Inline `get_object_api` summary on `api_discovery_required` rejections (#29)
- Inline cast rewrite + `KernelInterfaces` import on `casting_issues_detected` rejections (#21)

### Fixes
- Surface operation failures at ERROR, preflight rejects at WARNING (#17)
- `[TOOL CALL]` always reaches cross-session `operations.log`; `[TOOL ARGS]` demoted to INFO (#19)
- Clarify `undiscovered_entity` rejection when entity is explicitly imported; inline discovery payload (#20)
- Drop alphabetical tie-break for ambiguous cast targets -- route to manual `resolve_property` (#21 follow-up)
- Retarget polymorphic hint at inlined rewrite, not external `resolve_property` (#22)
- Diagnose SharedSettings / path-mismatch errors against discovered project list (#23)
- Surface `project_locked` with close-FieldWorks hint; correct exception class to `LcmFileLockedException` and FW9 lock-file location (#27)
- Retry-loop assistance hint now points at #21 inlined rewrite, not `resolve_property` (#28 follow-up)
- Casting validator skips mid-chain segments rooted at a typed receiver -- eliminates the `wf.Form.BestVernacularAlternative` and `IWfiWordform(ana).Form.BestVernacularAlternative` false positives surfaced in Seth's 2026-05-28 session

### Observability
- Writeability rejects log per-issue DEBUG (mutating calls / unprotected LCM / raw LCM patterns with line + context), mirroring the casting-reject log pattern
- Close logging gaps so every `error_response` in `handle_run_module` is preceded by either `_log_preflight_reject` (in-op) or `[PRE-OP REJECT]` WARN (pre-op-id rejections like `project_name_required` / fuzzy-resolve failure)
- `handle_list_skeletons` storage failure now logs at ERROR with `exc_info`, not just packed into JSON
- Silent `list_projects()` failure inside the path-failed diagnostic now WARNs so the operator can tell discovery-failed from no-projects-nearby

### Docs
- Relax module-template mandate; bare snippets are first-class (#26)
- Reword `undiscovered_entity` message ("loaded" not "validated") (#20 follow-up)

## [2.0.0] - 2026-04-07

### Major Features
- **Async-first MCP Architecture**: Complete async implementation for concurrent tool execution
- **FlexLibs2 v3.0.0 Integration**: Deep wrapper support with 90% API coverage
- **LibLCM v11.0.0 Support**: Current version of FieldWorks library bindings
- **Session-based Configuration**: Persistent state management across tool calls
- **Structured Script Certification**: Validate FLExTools scripts before execution

### Code Consolidations & Improvements

#### Core Analyzer Modules
- Eliminated duplicate `infer_output_behavior_lcm()` function (-83 LOC)
- Pre-compiled regex patterns in docstring parsing (5-10% faster)
- Eliminated duplicate AST parsing in FlexLibs stable analysis (~2x faster)
- Merged dual entity iterations in refresh pipeline (O(2n) → O(n))
- Consolidated 52 API categorization constants to shared module

#### Handler Architecture Unification
- Created `response_keys.py` module for centralized response field constants
- Unified `json_response()` helper across all handlers
- Removed duplicate KEY_* constant definitions across handler modules
- Consolidated response formatting patterns

#### Performance Optimizations
- Cached version detection in server startup
- Optimized entity iteration patterns
- Pre-compiled regex patterns for docstring extraction
- Lazy-loaded pattern analyzers

### Bug Fixes
- Fixed duplicate @OperationsMethod decorators in FlexLibs2 (6 methods)
- Fixed undefined KEY_LIMIT and KEY_OFFSET constants
- Improved error handling in PropertyResolver
- Enhanced session state reset for clean test isolation

### Testing
- Added comprehensive validator tests (25+ new tests)
- Improved test fixture consolidation
- Added AST pattern visitor for complex analysis
- Enhanced test isolation with reset_session_state fixture

### Documentation
- Updated FLEXTOOLS-STYLE-GUIDE.md with best practices
- Added API versioning documentation
- Documented safe write guard patterns for user scripts

### Migration Notes
- **Breaking Change**: FlexLibs2 v2.0+ scripts need explicit imports (see CLAUDE.md)
- API response structure unchanged - backward compatible
- Session initialization now required before tool calls (already implemented)

### Known Limitations
- LibLCM reflection requires pythonnet on Windows
- Write operations serialize at project level (by design)
- Session state not persisted across CLI invocations
