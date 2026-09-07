# QC review -- bugfix cycle 2 (`cb3f1b8` #103, `0c9a59b` #96)

Reviewed the commit diffs, not the working tree.
**No P0. Both commits are sound; `closes #103` is safe. Merge.**

## Q1 -- hvo false positives: claim CONFIRMED (`validators.py:2295-2454`)

Value side is `_is_int_literal` only (`ast.Constant` + `int` + not `bool`). I
ran it against the live index on 20 adversarial snippets; every non-literal
shape passed -- `entry.Hvo`, `entry.Hvo + 0`, `GetHvo(e)`, `h = 1234` then
pass `h`, `enumerate` index, `True`, `-5`, `**{'entry_or_hvo':7}`, `wsHandle`
ints, `GetAll(1)` (`recursive`). Positional alignment is right: the index
strips `self`. All 84 `*_or_hvo` params document "object or its HVO", none with
an int default or sentinel (checked `level_or_hvo` / `index_or_hvo`).
Cross-class name collisions can't fire -- the ops class resolves from the
index's own `FLExProject` return types. **No realistic false positive
constructible.** Only contrived one: `_resolve_alias_maps` never clears
aliases, so `ops = LexEntryOperations(project)`; `ops = MyThing()`;
`ops.AddSense(3,'x')` flags. **P2, no action.**

## Q2 -- table right, code registry stale [P1, cb3f1b8]

I counted 18 rows (`syntax_error`..`runtime_error`); TOOL-CONTRACT.md:69's
"18 codes" is correct. Runtime envelope is fine (`RejectionEnvelope` is
`extra="ignore"`). But the code landed in the doc only:
`response_models.py:345-363` `AnyDetail` still lists 17 models with no
`HvoLiteralWriteRiskDetail`, so TOOL-CONTRACT.md:94's "field lists below are
authoritative" is false for the new row; `response_models.py:10` still says
"17 per-code detail models"; `test_response_contract.py:199 ALL_17_CODES` and
`:255 DETAIL_MODEL_MAP` unextended -> no round-trip coverage. **P2:**
`session.py:44-85 _ASSISTANCE_HINTS_BY_ERROR_CODE` has no entry, so
`_attach_assistance_if_loop` emits the generic retry hint.

## Q3 -- `success` False on every commit-failure path [OK]

All `success = True` sites (`execution.py:3847`, `:3852`, `RESULTS:` path) sit
inside the `try`, so the new `finally` (`:3862-3888`) always runs and demotes;
the early `return` at `:3687` never sets success. Your reading of the bare
`except:` sites is correct and they are **benign**: `:3731`/`:3743`/`:3773` are
in the read-only `find_writing_system` / `list_writing_systems` helpers (local
`result` list, no LCM write); `:3891` is `FLExCleanup()`, which runs *after*
`CloseProject()` did `EndNonUndoableTask -> Save -> Dispose`. None can mask a
commit or data-integrity failure. Nothing filed.

## Q4 -- `HeadlessLcmUI` fallback fails SAFE [OK]

`execution.py:3645-3677`: on `ImportError`, `_lcm_ui = None` **and**
`report.Warning(...)` naming the hang hazard. Genuinely visible -- `report` is
created before the imports (`:3636`), the early OpenProject return copies
`messages`/`summary` (`:3680-3686`), and `_cap_info_messages` (`:4370`) trims
info only ("Errors/warnings always survive intact"). Test-locked. **P2:** only
`ImportError` is caught, so a raising `HeadlessLcmUI()` constructor aborts the
run instead of degrading -- fail-closed, acceptable.

## Q5 -- primer promises no interval [OK]

`shared_mode_read_back.why`: *"there is NO reliable interval and NO retry count
that guarantees the write has become visible -- the window is unbounded, not
merely long."* `note`: *"there is no N that is safe."* No number anywhere.
**P2:** the `note`'s remedy ("needs a LIVE peer session ... not a new one")
isn't achievable via `run_module`, which always opens a fresh session.
**P2:** the lock test's forbidden list is a blacklist ("18s", "within 30") that
would pass "wait 45 seconds"; assert a digit+unit regex.

## Q6 -- test quality [OK]

#103's 5 gate cases exercise the *decisions*, not just the AST: block, warn
(read-only, asserting warning text and `success is True`), pass (`.Hvo` write,
comment-only). #96 adds 3 real subprocess runs against a fake `flexicon` --
`ui_type == HeadlessLcmUI`; teardown raise -> `success False` +
`TeardownError`; missing `headless_ui` -> `ui_is_none` + WARNING -- plus
source-shape checks and the primer lock. **P2 gap:** the "preserve, don't
clobber a prior error" branch (`:3869-3873`) is untested.

## Recommendation

Merge. Fix the P1 registry drift (add `HvoLiteralWriteRiskDetail`, extend
`ALL_17_CODES`/`DETAIL_MODEL_MAP`, correct `response_models.py:10`) here or as
a follow-up -- a docs/test-coverage inconsistency, not a runtime defect.
