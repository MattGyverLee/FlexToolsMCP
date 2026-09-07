# Bugfix campaign -- Swahili audit follow-through (MCP-side only)

Repo: **FlexToolsMCP** `D:\Github\_Projects\_LEX\FlexToolsMCP`, branch
`feat/shared-mode-access`. (#96 is A4 in SPEC.md and is shared-mode territory, so
the campaign stays on this branch.)

## CREW MECHANICS -- learned the hard way, do not re-plan around them

- **`lex-qc` is NOT a dispatchable `subagent_type` in this environment.** It exists
  only as a skill. Cycle 2's QC ran under `general-purpose` with the QC brief passed
  verbatim, which worked fine. Do the same; do not emit a task with
  `subagent_type: lex-qc`.
- **`Explore` has no `Write` tool.** Cycle 1's #96 investigation could not write its
  own report, so the main session had to commit the returned body by hand. For any
  task that must WRITE a report to a path, use `general-purpose` (or accept that the
  coordinator relays the body, which defeats the path-relay rule). `lex-programmer`
  and `lex-verification` both dispatch and write fine.
- **Do NOT treat a static-analysis diagnostic as a finding while a parallel task is
  mid-edit.** Cycle 3 burned three investigations on stale Pyright output: `re`
  reported undefined when the import was present, and a duplicate/None-based class
  declaration reported in a file with a single declaration and all 15 tests
  collecting fine. All three were false alarms against mid-edit saves. **Confirm
  with `pytest --collect-only` or a targeted run BEFORE reporting it.**
- **The versioning-cache flake: CORRECTED CHARACTERIZATION (cycle 6). The version
  cycles 4 and 5 both relied on was WRONG.** Those cycles said it "passes in
  isolation", implying an inter-test interaction. Measured in cycle 6:
  `TestFileDiscoveryCacheInvalidation` run 20x in TRUE single-test isolation
  failed **3/20 (15%)**, alternating between
  `test_new_exact_file_visible_after_write` and
  `test_new_latest_file_visible_after_write`; and
  `test_new_exact_file_visible_after_write` run completely alone 8x failed
  **2/8 (25%)**. So it is an mtime-granularity race **intrinsic to each test**, not
  a sibling interaction. It survived two cycles as received wisdom -- exactly the
  kind of false premise that makes a future cycle dismiss a real failure.
  **"Rerun and move on" is weaker guidance than we assumed.** At a 25% base rate,
  two consecutive failures are ~6% likely, which a future agent could easily
  misread as a genuine regression. Decision rule instead: treat it as the known
  flake only if it fails NON-deterministically with the SAME mtime-comparison
  assertion; treat as a real finding if it fails 10/10, or if the assertion or
  error differs at all.
  **Proposed real fix (cheap, unclaimed):** stop depending on filesystem timestamp
  resolution -- set explicit, distinct mtimes (or use a monotonic counter / injected
  clock) in the cache-invalidation tests instead of writing files and hoping the
  mtime advances. This is now the campaign's oldest recurring noise source and it
  has cost several investigations.
- **The untracked-artifact failure RECURRED at the spurt-2 handoff.** Five gate
  reports from cycles 4-6 -- `bugfix-cycle4-qc.md`, `bugfix-cycle4-verification.md`,
  `bugfix-cycle5-qc.md`, `bugfix-cycle5-verification.md`,
  `bugfix-cycle6-verification.md` -- were all still UNTRACKED, i.e. every artifact
  that justifies this campaign's green board. Committed at handoff. The
  `git ls-files` check earned its place; run it EVERY checkpoint, and note that
  writing a report is not the same as committing it.
- **Untracked report files are a real loss risk.** At the CP-A handoff,
  `reviews/bugfix-cycle1-explore-96.md` (the #96 root cause -- the single most
  valuable artifact of the spurt), `SPEC.md`, and this tasks file were all still
  UNTRACKED despite being believed committed. `git clean -fd` or an untracked-file
  tidy would have destroyed the loop's entire memory. **Verify with
  `git ls-files specs/<feature>/` at every checkpoint, not `ls`.**

## HARD CONSTRAINT -- flexicon is off-limits to this crew

An agent OUTSIDE this crew owns `D:\Github\_Projects\_LEX\flexicon` and is editing
it concurrently under an advisory file-lock registry. **No task in this campaign may
edit flexicon package source.** Reading flexicon for reference is fine; writing is
not. Anything that appears to need a flexicon change gets reported as a cross-repo
dependency, not dispatched.

Every dispatched task must declare the file set it will modify, so the coordinator
can acquire locks before the group fires.

Ordering rule (user's, do not reorder): **silent-wrong-data before loud-failure.**

## OWNED EXTERNALLY -- do not touch

- ~~flexicon #254 `WfiMorphBundleOperations.GetMorphType` returns the allomorph~~ --
  reassigned outside this crew. Still real, still unfixed while we work. See the
  unmasking note under CP-B.

### Cross-repo dependencies to REPORT, never to action here

1. **flexicon #254 has an unreported write-side twin.** `SetMorphType`
   (`flexicon/code/TextsWords/WfiMorphBundleOperations.py:876-877`) assigns
   `bundle.MorphRA = morph_type`, and its own docstring example (`:844-848`) feeds
   it an `IMoMorphType` out of `project.lp.MorphTypesOA.PossibilitiesOS` -- i.e. the
   documented usage writes a possibility-list item into a field typed `IMoForm`.
   The getter bug is filed; this write-side counterpart is not. Relay to whoever
   owns #254; do not fix or comment from this crew.
2. **flexicon #257** (package-level export of `MSAOperations`). Issue #100 states
   explicitly that the MCP index-metadata fix is correct *regardless* of whether
   flexicon also exports at package level, and that the index fix additionally
   repairs already-indexed older flexicon builds. So CP-C proceeds independently.
   Do not wait on #257 and do not edit flexicon to satisfy it.
3. **#103 needs NO flexicon change.** CONFIRMED cycle 1.
   `FLExProject.Object(hvoOrGuid)` (`flexicon/code/FLExProject.py:3212-3226`)
   already accepts `str` / `System.Guid`, so the inverse of `GetGuid` ships today
   and merely needs advertising. `FromGuid` / `ObjectFromGuid` grep clean in both
   repos -- there is nothing to add and nothing to name `FromGuid`.
4. **flexicon `MediaOperations.GetHvo` docstring teaches the #103 anti-pattern.**
   `flexicon/flexicon/code/Shared/MediaOperations.py:1497-1516` has
   `>>> media2 = project.Object(hvo)`, and it is statically extracted into this
   repo's generated index at
   `src/flextoolsmcp/index/python/flexicon_api_v4.5.2.json:44013`. So the MCP
   re-serves the anti-pattern the #103 fix exists to kill. Needs a flexicon-side
   docstring fix (swap `hvo`/`GetHvo` for `GetGuid`/`guid_str`). Report only.
5. **NEW liblcm BUG -- confirmed in source, deserves its own issue.**
   `XMLBackendProvider.WriteCommitWork:518-527` returns WITHOUT writing when the
   file changed underneath it (`ksFileModifiedByOther`, via a modal
   `ReportProblem`), but `SharedXMLBackendProvider.WriteCommitWork:499` sets
   `FileGeneration` unconditionally after that early return. Metadata then claims a
   flush that never happened -- which would strand commit-log records as
   purgeable. Citations are in `reviews/bugfix-cycle1-explore-96.md` section 3.
   Filing a liblcm issue needs the user's authorization; do not file unprompted.
6. **#96's REAL fix (cache-bypassing verification read) may need a flexicon entry
   point -- UNRESOLVED, worth one narrow check.** The cycle-1 investigation
   concluded a verification session must call `SaveChanges()`
   (`FLExProject.py:563-588`) BEFORE reading, which requires `write_enabled=True`
   plus `ReadyForBeginTask` (`UnitOfWorkService.cs:304`) and therefore must run
   before the `undoable=False` envelope -- "i.e. it needs a flexicon entry point,
   not just an MCP change." That conclusion has NOT been stress-tested. If the
   generated runner can call `SaveChanges()` immediately after `OpenProject`, the
   real fix is MCP-side and unblocked. Check this before accepting the blocker.

## Sequencing note -- why the checkpoints cannot be parallelized

CP-A's #103 guard and CP-B's casting gate both edit
`src/flextoolsmcp/server/handlers/execution.py` and
`src/flextoolsmcp/server/validators.py` -- the shared spine of every preflight
gate. Under the lock registry these cannot be held concurrently, so CP-A and CP-B
run in separate spurts rather than in parallel. This is a lock constraint, not a
logical one.

## Open blockers -- RESOLVED 2026-09-06, except the live repro

The user granted blanket discretion: *"sharing on, fix and file at your
discretion."* That cleared all three CP-A blockers:

1. **CP-B severity downgrade: APPROVED**, as scoped -- gate-local to the casting
   gate's warning tier, read-only runs only, detection and reporting fully intact,
   write runs keep hard-rejecting at every severity. The guardrail against a
   generic "read-only downgrades all preflight gates" refactor still stands.
2. **The liblcm bug is FILED as FlexToolsMCP#107.** `MattGyverLee/liblcm` has
   issues disabled, so it was filed on the active tracker, clearly marked as an
   upstream liblcm defect. Reporting it to `sillsdev/liblcm` remains a SEPARATE
   decision, deliberately not taken. Both code sites were independently
   re-verified before filing: `SharedXMLBackendProvider.cs:490-503` calls
   `base.WriteCommitWork`, which early-returns at `XMLBackendProvider.cs:528`
   without writing, and `FileGeneration` is then set unconditionally.
3. **`Target` sharing preconditions: MET.** `projectSharing="true"`, open in FLEx
   under PID 13272, `.fwdata` still at its Aug-18 baseline.

### STILL NOT RUNNABLE -- the live repro, for a NEW reason. RECORD THIS PATTERN.

**The running MCP server is stale.** PID 19808 started 2026-09-06 22:41:49, which
predates `cb3f1b8` (23:16), `0c9a59b` (23:34) and `8f72b9f` (23:47). Python imports
a module once per process, so the live server is still executing the OLD
`execution.py`: no `ui=HeadlessLcmUI()`, and the old teardown that swallows commit
failures. Running the repro against it would be actively harmful twice over:

- repro step 4 calls `SaveChanges()`, which is exactly the `ConflictingSave()` ->
  modal WinForms dialog path that A-8 removes, so it can HANG a headless
  subprocess; and
- A-7 is the very instrumentation the repro depends on to observe teardown
  failures, so any evidence gathered would be untrustworthy.

**The MCP server must be RESTARTED before any live verification of runner-code
changes.** The server is client-managed, so no agent can restart it from a tool
call -- it is a user action.

**This is a general precondition, not a one-off.** It will recur on EVERY future
spurt that fixes generated-runner or server code and then tries to verify it live.
Add "restart the MCP server" to the live-verification preconditions permanently,
alongside sharing-on and the non-editing-view requirement. A live check run against
a stale server is worse than no live check, because it produces confident evidence
about code that is not running.

### CP-B blast radius -- MEASURED at spurt 2 planning, bigger than "flip a check"

Two findings that a naive B-1 implementation would get wrong:

1. **#97's worst symptom is NOT defused by B-1.** #97 Bug 2's false positives on
   correct code surface as `'SlotsRC' does not exist on 'IMoUnclassifiedAffixMsa'`
   -- the *`detect_interface_attribute_typos`* shape, and `execution.py:2852`
   merges those in with `severity = "error"` deliberately. So they hard-reject even
   on read-only runs, and B-1 leaves them fully intact. The item that actually
   unblocks correct code is **B-4** (flow-sensitive variable typing), not B-1.
   Keep `severity = "error"` for genuine typos -- a property that exists nowhere is
   a real error; the bug is the *branch conflation* that misattributes it.
2. **B-2's local-cast tracking and B-4's branch flow-sensitivity are the same
   capability** -- assignment- and branch-aware variable typing. Implement them
   together or they will fight each other.

Existing tests/fixtures that pin the current reject behavior (triage each, do NOT
flip fixtures to make tests pass):
`tests/evals/corpus/06_reject_casting_issues_headword.yaml`,
`20_reject_casting_lexeme_form_no_cast.yaml`,
`issue40_negative_control_uncast_category_rejected.yaml`,
`issue15_cast_alias_satisfies_chain.yaml`,
`issue30_receiver_suffix_naming_skip.yaml`, `tests/evals/preflight_runner.py`,
`tests/evals/test_corpus.py`, `tests/golden/responses/casting_issues_detected.json`,
`tests/golden/responses/auto_fix_ambiguous_not_applied.json`,
`tests/make_golden.py`, `tests/test_retry_loop_detection.py` (11 refs),
`tests/test_diagnostic_report_foundation.py` (7), `test_diagnostic_report_reconstruction.py` (10),
`tests/test_response_contract.py` (5).
Most should NOT change: known-pattern hits stay `severity: "error"`
(`validators.py:3598`) and keep rejecting. Only the index-derived **warning** tier
(`:3710`) flips, and only on read-only runs. Check each fixture's tier first.
`issue40_negative_control_*` is a deliberate negative control -- understand it
before touching it; if it legitimately flips, say why.

Also expect a **retry-loop interaction**: loop detection keys on repeated
`error_code`s via `record_op_signal`. Read-only casting rejects becoming warnings
means the detector sees success and resets. That is probably correct (the loops it
detected were largely this gate's own false rejects) but it is a behavior change
that `test_retry_loop_detection.py` pins.

**CP-C IS NOT BLOCKED.** Items #100 and #101 have no user gate and no flexicon
dependency (see cross-repo item 2 -- flexicon#257 explicitly does not gate them).
CP-C is the correct next spurt: it is not queue-jumping item 3, it is the only
unblocked checkpoint left.

## MERGE READINESS of `feat/shared-mode-access` -- NOT READY (assessed at CP-A close)

The user asked whether this branch can merge to `main`. **No, and the reason is not
this campaign.** Four things stand in the way; only #3 and #4 are ours:

1. **A standing pre-existing blocker forbids it.** `STATUS.md` (shared-mode-access
   section) says verbatim: "Do not merge `feat/shared-mode-access` to `main` until
   this passes" -- the **CP1 live write check for #92**, which has never been run
   because it needs a live FLEx target and the user's authorization. Every green
   gate on #92 is static, and static-green is exactly how the original #92 breakage
   survived 27 `write_enabled: true` runs undetected. Command and pass criteria are
   in STATUS.md.
2. **`STATUS.md` is STALE about its own feature.** It claims "CP2-CP6 are
   UNSTARTED", but `39d1caf` (CP2 access probe) and `6dc459a` (CP4 shared-mode
   write path) have since landed on the branch. Reconcile before anyone reasons
   about merge scope from it.
3. **The flexicon 4.4.1 -> 4.5.2 index migration is uncommitted and undecided.**
   Working tree: 3 deletions (`common_patterns_flexicon-v4.4.1.json`,
   `python/flexicon_api_v4.4.1.json`, `python/flexicon_lcm_bridge_v4.4.1.json`),
   3 untracked v4.5.2 replacements, plus modified
   `liblcm/liblcm_api_v11.0.0.json` and `reverse_mapping_liblcm-v11.0.0.json`.
   **Needs its own deliberate commit or a clean revert -- never sweep it into a
   code commit.** Note this repo supports multiple index versions side by side
   (docs/VERSIONING.md), so deleting the v4.4.1 files is a real decision, not
   housekeeping: anyone still on flexicon 4.4.1 loses their index. Decide
   explicitly whether 4.4.1 support is being dropped. Also `docs/logscan-state.json`
   is modified and belongs to logscan, not to this campaign.
4. **Two prior-session spec artifacts still need a keep-or-drop call** --
   `reviews/cycle1-domain.md` and `reviews/cycle1-explore-nullmorph.md` (Workstream
   B / null-morph work). Left UNTRACKED deliberately at the CP-A handoff so the
   user decides. `SPEC.md` was committed rather than left to that decision, because
   this tasks file depends on it and losing it breaks the next spurt; dropping it is
   a revert, not a loss.

Correct and safe on merge: `cb3f1b8` is the only commit in the branch carrying an
auto-close keyword (`closes #103`), and #103 genuinely is fixed. No commit
auto-closes #96, #40, #97, #100 or #101 -- verified by grep over
`origin/main..HEAD`. #92/#93 commits reference but do not close.

## CP-A -- data integrity (spurt 1, ACTIVE)

- [x] A-4  #103: advertise the GUID round-trip -- `runtime_primer`, the
      `flextools_run_module` tool description, and an audit of every doc/example
      that teaches persisting an hvo. DONE, commit `cb3f1b8`.
- [x] A-5  #103: preflight guard when an int literal reaches an `*_or_hvo`
      parameter. DONE, commit `cb3f1b8` -- WARNING on read-only runs, HARD BLOCK on
      write runs with new `error_code` `hvo_literal_write_risk` (TOOL-CONTRACT.md
      17 codes -> 18). Suite 1041 passed / 4 skipped; the "961 passed, 3 skipped"
      baseline was stale. One pre-existing flake:
      `test_flextools_health.py` mtime race, passes standalone and on rerun.
- [x] A-6  #96: root cause CONFIRMED in source, and it is STRONGER than the
      issue's hypothesis. A non-master peer's commit lands only in the in-memory
      shared commit log; `.fwdata` advances only when the master writes; a fresh
      open reads `.fwdata` via `ReadInSurrogates` and registers at
      `Generation = FileGeneration`, and startup NEVER replays commit-log records.
      So a fresh read-only session **structurally cannot** see a peer's write. Not a
      timing window -- **unbounded**, because the master's `SaveOnIdle` guards
      (`UnitOfWorkService.cs:245-251`) are human-gated. Full citations in
      `reviews/bugfix-cycle1-explore-96.md`. Docs must therefore NOT promise any
      safe interval; the truthful rule is "a fresh read-only session under a live
      FLEx master shows the last master save, not your write."
- [x] A-7  #96 silent-failure half (MCP-side, no flexicon dependency). DONE,
      commit `0c9a59b`. Teardown handler demotes `success` on a `CloseProject()`
      failure and PRESERVES any prior error rather than clobbering it.
      `execution.py:3722` sets `result["success"] = True` BEFORE `CloseProject()`
      runs at `:3747-3752`, under a bare `except: pass`. Teardown commit failures
      are invisible and discarded. Move `success` after teardown; stop swallowing.
- [x] A-8  #96 modal-dialog hazard (MCP-side, no flexicon dependency). DONE,
      commit `0c9a59b` -- `ui=HeadlessLcmUI()` wired at `execution.py:3677` with an
      `ImportError` fallback that emits a visible `report.Warning` naming the hang
      hazard. Confirmed fail-safe by QC and runtime-confirmed by verification.
      Original finding, for the record:
      `execution.py:3571` generates `OpenProject(...)` with **no `ui=` argument**,
      so flexicon supplies WinForms `FwLcmUI` (`flexicon/code/FLExLCM.py:98-100`).
      `HeadlessLcmUI` ALREADY EXISTS (`flexicon/code/headless_ui.py`) and
      `OpenProject(..., ui=None)` already accepts it (`FLExProject.py:164`), but
      `ui=` greps clean across the whole MCP. Same shape as the #103 finding: the
      seam ships, the MCP never uses it. Consequence today: a `ConflictingSave()`
      in a headless subprocess is a modal dialog, i.e. a hang. This is ALSO a hard
      precondition for the authorized #96 live repro, whose step 4 calls
      `SaveChanges()` -- exactly the path that can raise it.

- [x] A-9  Contract drift found by QC as a P1 and fixed by the coordinator in
      commit `8f72b9f`: `hvo_literal_write_risk` was in `docs/TOOL-CONTRACT.md` but
      never in the code contract -- `AnyDetail` was still a 17-model union, so the
      payload had no detail model and no envelope round-trip coverage. Added
      `HvoLiteralWriteRiskDetail`, put it in the union, corrected three 17->18
      counts, extended the contract tests, and renamed `ALL_17_CODES` ->
      `ALL_ERROR_CODES` (a count baked into an identifier is how the gap survived).

**CHECKPOINT CP-A: CLOSED GREEN (spurt 1).** #103 fixed (`cb3f1b8`); #96 root cause
confirmed in source and both MCP-side halves fixed (`0c9a59b`); contract drift
closed (`8f72b9f`). Gates: **QC no P0** (one P1, since fixed); **Verification PASS
on both commits** for non-live claims; suite **1052 passed / 4 skipped**. The #96
staleness itself is NOT fixed and cannot be until the live repro runs.

### CP-A carryover -- all P2, non-blocking, fold into a later checkpoint

From QC (`reviews/bugfix-cycle2-qc.md`):
1. `session.py:44-85 _ASSISTANCE_HINTS_BY_ERROR_CODE` has no
   `hvo_literal_write_risk` entry, so `_attach_assistance_if_loop` emits the
   generic retry hint for a block whose fix is specific. Best-value item here.
   NOTE: `8f72b9f` fixed the response-model half of this drift but NOT this hint.
2. **The primer's own recommended remedy is not achievable.** The
   `shared_mode_read_back` note says verification "needs a LIVE peer session ...
   not a new one", but `run_module` always opens a fresh session. The wording is
   truthful about the hazard yet points at something the tool cannot do -- revisit
   when #96's real fix lands.
3. The primer lock test uses a blacklist ("18s", "within 30") and would pass
   "wait 45 seconds". Assert a digit+unit regex instead.
4. `_resolve_alias_maps` never clears aliases, so a rebound name
   (`ops = LexEntryOperations(project)` then `ops = MyThing()`) can produce a
   contrived hvo-gate false positive. Not realistically reachable.
5. Only `ImportError` is caught around `HeadlessLcmUI()`; a raising constructor
   aborts the run instead of degrading. Fail-closed, so acceptable.

From verification (`reviews/bugfix-cycle2-verification.md`) -- two honest gaps it
declined to paper over:
6. The "script body already failed, THEN teardown also fails" path is
   source-consistent (the handler is additive, `execution.py:3858-3883`) but not
   unit-tested. QC independently flagged the same branch (`:3869-3873`). Two gates
   converging on one untested branch -- test it.
7. The known `test_flextools_health.py` mtime flake never manifested across two
   full suite runs plus a standalone run, so its "pre-existing flake" status could
   not be positively confirmed. Do not treat that label as established.

## CP-B -- the casting gate (spurt 2)

**BLOCKED ON THE USER.** The read-only severity downgrade (B-1) lets
previously-rejected scripts execute, which is our call to make, not a maintainer's.
The recommendation is with the user; CP-B is not dispatchable until they answer.

**LINE NUMBERS REBASED after `cb3f1b8`** (the #103 commit inserted 182 lines into
`validators.py` at 2273-2454, and a 59-line gate into `execution.py` at 2771-2829).
Content is unchanged in both. Post-`cb3f1b8` numbers -- USE THESE:

| what | pre-`cb3f1b8` | NOW |
|---|---|---|
| casting severity logic (`validators.py`) | 3416 / 3549 | **3598 / 3731** (also 3439, 3710) |
| `casting_check["severity"] = "error"` (`execution.py`) | ~2793 | **2852** |

**CP-B / CP-C LANDED (spurt 2, cycle 3).** Commits: `b5f41d8` (casting gate),
`cea0ca6` (#100/#101), `aba84d8` (the two P2s), plus report commits. Suite
**1100 passed, 4 skipped, 12 subtests**. Gates run in cycle 4.

### The fixture-change STANDARD, established cycle 3 -- follow it from now on

`issue40_negative_control_uncast_category_rejected.yaml` was the highest-risk edit
in the whole campaign: a deliberate negative control whose expected outcome the fix
would flip. It was NOT flipped to `outcome: ok`. Instead `write_enabled` was flipped
`false -> true`, so the fixture still proves detection is active AND now
additionally proves write runs reject the warning tier -- and a NEW fixture
(`issue40_warning_tier_readonly_proceeds.yaml`) covers the read-only path. The
reasoning went into the fixture's own `notes`.
**Rule: when a fix changes a fixture's outcome, change the SCENARIO to preserve
what the fixture was protecting, and add a new fixture for the new behavior. Never
flip the expected outcome to make a test pass.** Only one existing fixture changed
out of the fourteen candidates flagged at planning; the rest were correctly left
alone because known-pattern hits stay `error` tier.

### CYCLE-4 GATE FINDINGS: two P1s, ONE root defect. Lead's design ruling.

No P0. Verification PASS on all four commits at unit/eval level (1107 passed / 4
skipped / 12 subtests; eval corpus 34 passed / 2 skipped; both casting safety
quadrants intact; #97 Bug 2 at 0/4 false positives, was 4/4). But two P1s, and
they are **the same root defect seen twice**: *the typo detector's inputs and the
casting gate's inputs are not the same set, and neither the new resolver nor
Gate 5 accounts for that.* Fix as ONE work item.

- **P1-1 (`b5f41d8`, `validators.py:976/983`) -- the resolver made typo detection
  WEAKER, in the FALSE-NEGATIVE direction.** `_resolve_cast_type_at` can return
  `None` for a name that IS in `cast_aliases`, and `:983 if not interface:
  continue` then drops the issue entirely. Reproduced independently twice, with
  `d = ILexDb(project)` and typo `EntriesOC`: cast-in-`if`-used-after,
  cast-in-`try`-used-in-`except`, and cast-in-`for`-used-after all went
  `has_typos=True` -> `False`. All three previously hard-rejected on read-only AND
  write runs. The commit message's "write runs still hard-reject, unchanged" is
  true of the DECISION but not of what reaches it. **Over-refusal is annoying;
  under-detection is a data risk.** This is strictly the worse direction.
- **P1-2 (`d1f30da`, `execution.py:1783` vs `:2880`) -- `validate_only` shares the
  predicate but NOT the inputs.** `handle_run_module` folds
  `detect_interface_attribute_typos` into `casting_issues` and forces
  `severity="error"` at `:2880-2886`; Gate 5 never calls it at all. So for
  `d = ILexDb(project); d.EntriesOC` at `write_enabled=False`, `run_module`
  REJECTS while `validate_only` returns `passed: True` plus the note "run_module
  would proceed without rejecting". B-5 replaced a pessimistic disagreement with a
  **false reassurance** across the whole #39 typo class -- worse than the bug it
  fixed. The agreement test cannot catch it because it monkeypatches
  `detect_interface_attribute_typos` to return no typos, so it validates the wrong
  thing.

#### RULING -- the fix is a CANDIDATE-UNION FALLBACK, not "recurse into `if` too"

A specialist's instinct will be to add `ast.If` to `_CAST_SCAN_RECURSE_INTO`
(`validators.py:2338`, currently `(ast.Try, ast.With)`). **That is wrong and
reintroduces #97 Bug 2.** `_scan_backward_for_cast` returns the FIRST cast it
finds, so recursing into an `If` picks an arbitrary arm -- last-wins -- which is
precisely the branch-conflation defect. Do not do it.

The correct rule, which fixes P1-1 and QC's P2-1 false positives with one
mechanism:

1. **Positional resolution stays the PREFERRED path.** When
   `_resolve_cast_type_at` resolves a single interface confidently, behave exactly
   as today. That is what kills Bug 2 and it works.
2. **When positional resolution returns `None` but the name is known to be cast
   somewhere, fall back to the CANDIDATE SET** -- every interface that name is
   cast to anywhere in the tree.
3. **Flag only if the property exists on NONE of the candidates.** If it exists on
   at least one, suppress.

Why this is right, checked against all four repros:
- Bug 2's 4-branch MSA case: candidates `{IMoStemMsa, IMoInflAffMsa,
  IMoDerivAffMsa, IMoUnclassifiedAffixMsa}`; `SlotsRC` exists on `IMoInflAffMsa`
  -> suppressed. Still 0 false positives.
- P1-1's case: candidates `{ILexDb}`; `EntriesOC` exists nowhere -> still flagged.
  False negative closed.
- Genuinely ambiguous `if`/`else` both assigning, then `InflectionClassRA` after:
  exists on `IMoStemMsa` -> suppressed. Accepts a false negative to avoid a false
  positive on code that is only conditionally correct. Correct trade for a gate
  whose over-refusal cost 2.5 hours.
- QC P2-1's new casting-gate false positives (cast in both `if` arms used after;
  cast in `for` used after) resolve the same way -- a candidate satisfies, so
  suppress.

Build the candidate map LOCALLY. Do NOT extend `_resolve_alias_maps` -- it is
shared with mutation detection and `detect_hvo_literal_args`, and keeping out of
other gates' blast radius is the discipline that has held for four cycles.

4. **Separately, add `handlers` to the `Try` traversal.** QC P2-1 established that
   `ExceptHandler` is unreachable via `body`/`orelse`/`finalbody`, so
   `_CAST_SCAN_RECURSE_INTO` never helped the `try`/`except` shape at all. Each
   `ExceptHandler.body` is its own statement list, so branch-awareness applies to
   it naturally -- this is a safe addition, unlike `ast.If`.
5. **For P1-2, share the PIPELINE, not the predicate.** Extract the whole casting
   decision -- `detect_casting_needs`, the `detect_interface_attribute_typos`
   merge, the `severity="error"` forcing, and the has-error predicate -- into ONE
   function that `handle_run_module`, `_handle_validate_only` AND
   `tests/evals/preflight_runner.py` Gate 5 all call. Sharing only the predicate is
   what produced P1-2; QC's P2-2 notes Gate 5 models no typo-derived issues either,
   so Tier-1 evals are blind to the same class.

### CYCLE-5 GATES CLEAN. The candidate-union ruling was validated with DATA.

Both cycle-4 P1s genuinely closed. Verification PASS on all six commits: suite
**1115 passed / 4 skipped / 12 subtests**, corpus **34 passed / 2 skipped**, the
P1-1 matrix **4/4 detected** against the real 118-entity index (and with
`did_you_mean=[Entries]`, so it suggests the correction rather than merely
flagging), Bug 2 independently 0 false positives, all four casting quadrants
intact including both safety cells, and the #103 hvo gate unaffected by the
neighbouring edits. QC: no P0, no P1.

**The union-breadth risk I flagged in the ruling was answered empirically, not
rhetorically.** Genuine-typo detection held at ~99% for N = 1, 2, 3, 4, 6, 8, 12,
16, 24 and 32 candidate interfaces (200 mutated-real-member trials per N). The
mechanism: LCM interfaces share a large inherited base, so the union grows
SUB-linearly -- Bug 2's 4-way MSA union goes 72 -> 83 names -- while a
*nonexistent* attribute stays absent from all of them. So no N kills detection,
and suppression bites only real properties valid on one arm, which is exactly the
trade the ruling accepted. Record this: it is the empirical basis for keeping the
union fallback, and it means the design does not need revisiting if candidate sets
grow.

### CYCLE 6 -- ACCEPTED: fix P2-1 and P2-2 before handing off

QC rated the cross-function candidate leak P2 because both shapes merely RESTORE
the pre-`b5f41d8` flat lookup, so it is not a regression. That reasoning is
correct about regression status and wrong about priority. **Regression status is
about blame; priority is about harm.** Three reasons to fix it now:

1. "Hard-rejects correct code at error tier" is issue #40's complaint verbatim.
   Shipping item 3 as fixed while leaving **209 known false-positive combos among
   just 12 common interfaces** in the same gate undercuts the deliverable.
2. **My own ruling under-specified this, and made one direction worse.** I said
   "build the candidate map LOCALLY", meaning do not touch `_resolve_alias_maps` --
   I never specified what the walk should be scoped TO, so the implementer walked
   the whole tree, which is defensible against what I wrote. And while the
   false-POSITIVE half is the four-cycle norm, the union rule adds a NEW
   false-negative direction on top of it: a cast of the same name in an unrelated
   function now SUPPRESSES a genuine uncast access (`_candidates` feeds
   `typed_root` `:3791` and the `& safe_ifaces` intersections `:3961`/`:3985`).
   That direction is new, and it is the dangerous one.
3. It is exactly the class of long-standing baseline defect that never gets fixed
   later, because it is nobody's regression.

#### REFINEMENT to QC's suggested fix -- "nearest enclosing FunctionDef" is NOT enough

QC proposes scoping the map to the nearest enclosing `FunctionDef`. Implemented
literally, that breaks two dominant real shapes:

- **Bare snippets have no `def` at all.** CLAUDE.md documents the "Lightweight op
  form (no `Main`)" as the primitive for exploration, where everything sits at
  module level. Nearest-enclosing-FunctionDef is `None` there, so a naive
  implementation yields an EMPTY candidate map and loses detection for the most
  common exploratory form outright.
- **A cast at module level used inside a function** is legitimately visible per
  Python scoping, and would be lost.

**Correct rule: scope the candidate map to the usage's LEXICAL SCOPE CHAIN** --
the innermost enclosing `FunctionDef`/`AsyncFunctionDef`/`Lambda`, then each
enclosing function outward (so nested helpers still see their enclosing
function's casts), then Module. Sibling and unrelated function bodies are
excluded, which is precisely what kills the 209 combos. Module scope is always in
the chain, so bare snippets keep full detection.

#### P2-2 is the SECOND structurally-blind test this campaign. Treat it as a class.

Tier-1 evals remain 100% blind to #39: the pipeline is correctly rewired, but
`FAKE_API_INDEX.liblcm["entities"] == []` (`preflight_runner.py:73-155`), so
`_interface_member_names` returns `set()` for every interface and the typo
detector can NEVER fire. `:285-287`'s hedge -- "to the extent FAKE_API_INDEX's
entities cover it" -- covers nothing. Cycle-4's P2-2 was rewired, not fixed.

This is the second time in this campaign a test appeared to cover a bug class
while being structurally incapable of detecting it; the monkeypatched agreement
test was the first. **CREW RULE: a test that cannot fail is worse than no test,
because it consumes the credibility of coverage.** When a gate claims to cover a
bug class, PROVE the fixture can fire -- disable the detection and show the test
goes red. A coverage claim without a demonstrated failure mode is not evidence.

### CYCLE 6 CLOSED CLEAN -- spurt 2 ends here

Commits `1e30148` (fix) + `eb2a1f2` (report). Verification PASS, no regression
across the nine earlier campaign commits. Suite **1121 passed / 4 skipped**;
corpus **35 passed / 2 skipped**, up from 34 with the new #39 fixture.

- Cross-function FALSE POSITIVE gone: the 209-combo shape is correct code and is
  no longer flagged.
- Cross-function FALSE NEGATIVE gone: the genuine uncast access is detected again
  (`casting_issues == 1`).
- **The lead's refinement was load-bearing.** QC's literal "nearest enclosing
  FunctionDef" would have killed detection for CLAUDE.md's documented bare-snippet
  "Lightweight op form"; the lexical chain includes Module scope, and the
  bare-snippet case is now an explicit test. Record the general lesson: **when a
  review names a fix, check it against the codebase's documented usage shapes
  before implementing it verbatim.**
- P1-1 matrix 4/4 within one function; #97 Bug 2 still 0 false positives.
- **The "prove it can fail" requirement did its job.** The RED/GREEN eval-coverage
  proof held under the gate's own independent reconstruction, so the new #39 corpus
  coverage is real rather than illusory -- unlike the two structurally-blind tests
  that preceded it. Keep requiring this.
- The gate disclosed two self-inflicted repro errors on its first pass, corrected
  and re-verified. That is the behavior to reward in a gate: a gate that hides its
  own mistakes is worth less than one that reports them.

### CARRIED P2s -- explicitly not fixed, do not lose these

- **QC P2-2 (`validators.py:1022`) slash-joined pseudo-interface label.**
  `"/".join(...)` reaches the user-facing message and
  `object_type`/`missing_on`/`available_on` (`:1053-1058`) as a name no index
  contains. Cosmetic: `imports_needed=[]` / `cast_interface=None` keep auto-fix
  out of it.
- **QC P2-3 (`admin.py:278-289`) primer wording nit.** The parenthetical omits
  that remedy 1 needs `SaveChanges()` BEFORE the `undoable=False` envelope
  (`execution.py:3810`), making the path unreachable from `run_module` today --
  but the same sentence opens by saying exactly that, so it is self-limiting
  rather than misleading. `why` is byte-unchanged, no digit+unit duration.
- **Cross-repo item 6 stays OPEN**: whether the generated runner could call
  `SaveChanges()` right after `OpenProject` was never stress-tested, and
  `execution.py:3810` is now a concrete anchor for that question.

### CP-B residual -- NOT done, carry to the next spurt

- [x] B-3  **DONE (spurt 3, `6e35204` + `97bd304`).** The diagnosis below was
      WRONG in an instructive way: `_pick_cast_interface` was never the culprit --
      it already returned `None` on ambiguity by design. The leak was the `fix`
      f-string at the old `validators.py:4090` taking `defined_on[0]` directly.
      Original (incorrect) framing retained for the record:
      #97 Bug 1: `_pick_cast_interface` still picks a plausible-but-arbitrary
      interface (`defined_on[0]`), so `"fix": "Cast x to Y"` is frequently wrong
      (`IWfiGloss` -> "ILexEtymology", morph type -> "ICmAgent",
      `IMoMorphSynAnalysis` -> "IMoDerivStepMsa", `IFsClosedValue.FeatureRA` ->
      "ICmAgent"). Deferred deliberately from cycle 3: it changes suggestion
      CONTENT rather than the block/warn decision, it builds on the brand-new
      `_resolve_cast_type_at` machinery that the cycle-4 gates have not yet vetted,
      and mixing it into cycle 3 would have made the fixture triage ambiguous.
      **Item 3 is therefore NOT fully fixed** -- do not report #97 as closed.
- [ ] B-5  **`_handle_validate_only` now DISAGREES with the real gate.**
      `execution.py:1771`'s casting check still reports `passed: False` for ANY
      issue regardless of severity or `write_enabled`, so the dry-run tool tells a
      user their read-only script will be refused when `run_module` would now run
      it. A preflight validator that contradicts preflight is a trust bug of the
      same kind #40 complained about. Flagged by the cycle-3 programmer as outside
      the CP-B ruling; needs its own fixture triage in
      `tests/test_issue49_validate_only.py`.
- [ ] B-6  Fragility in the new CP-B code (Pyright flags it possibly-unbound):
      `validators.py:3641` assigns `_parents` inside `if cast_aliases:` at `:3638`,
      but the second walk loop from `:3657` is OUTSIDE that block and uses
      `_parents` at `:3672`, guarded only by `root.id in cast_aliases` at `:3667`.
      Safe TODAY only because an empty `cast_aliases` makes `:3672` unreachable --
      i.e. the safety depends on correlating two guards ~30 lines apart, and it
      breaks silently the moment a third `_parents` use appears under a different
      condition. Hoist it or pass it explicitly.

- [x] B-1  #40: stop hard-rejecting on warning-severity casting issues. DONE in
      `b5f41d8`, gate-local as ruled -- the downgrade lives entirely inside
      `handle_run_module`'s casting block; `unprotected_writes`,
      `hvo_literal_write_risk` and `nested_unit_of_work` are provably untouched,
      and `_resolve_alias_maps` was left alone as another gate's blast radius.
      Retry-loop interaction handled per `record_op_signal`'s own documented
      on-success contract (`error_code=None` resets).
- [x] B-2 + B-4  DONE in `b5f41d8` via a PARALLEL resolver
      (`_resolve_cast_type_at` / `_scan_backward_for_cast` /
      `_find_enclosing_stmt_list` / `_build_parent_map`), wired into
      `detect_interface_attribute_typos` and `detect_casting_needs`. It walks
      outward through enclosing statement lists and recurses into `try`/`with` but
      NOT `if`/`for`/`while`, so a sibling branch's cast is structurally invisible
      to a usage in another arm. #97 Bug 2's verbatim 4-branch MSA repro: 0 false
      positives, versus 4/4 with the fix reverted.

- [x] B-1 (original description, retained for the record) #40: stop hard-rejecting
      on warning-severity casting issues. Per-issue
      severity ALREADY exists in the data (`validators.py:3598` = `"error"` for
      known patterns, `:3710` = `"warning"` for index-derived lookups) but `:3731`
      overwrites it with `"error" if issues else "none"`, and
      `execution.py:2852` gates on `has_casting_issues` alone -- severity is never
      consulted at the decision point. Lead's ruling: honor it, but scope the
      downgrade to `write_enabled=False`; write runs keep rejecting at every
      severity. Keep detection and reporting fully intact (#97 asks for that
      explicitly).

### Lead's ruling on the gate-ladder tension (raised cycle 1, decided)

`cb3f1b8` added a SECOND unconditional hard block on write runs
(`hvo_literal_write_risk`) while #40's whole complaint is that a hard-blocking gate
burned a 2.5-hour session. These do not actually conflict, and the ladder's LENGTH
is not the problem. The two gates differ on the decisive axis, which is
**precision**:

- The hvo gate fires on a bare integer literal in an `*_or_hvo` position -- a
  syntactic fact with essentially no false-positive surface. There is no legitimate
  reason to hardcode an hvo. A `.Hvo` read within the same run is never flagged.
- The casting gate fires on *type inference* over polymorphic receivers. That is
  where the false positives come from: 6 rejects, already-cast variables re-flagged,
  `if`/`elif` branch conflation, `defined_on[0]` guesses.

#40 never argued that hard blocks are wrong; it argued that THIS gate is wrong too
often to be permitted to block. So keep the hvo block and fix the casting gate's
accuracy.

**Guardrail this imposes on B-1:** implement the read-only downgrade as
**gate-local to the casting gate's warning tier**. Do NOT implement it as a generic
"downgrade all preflight gates on read-only runs" refactor. A generic version would
also defang `unprotected_writes` and the #103 advisory, which are precision gates
that earn their blocks, and it would discard the pedagogy that makes the write
guard learnable.
- [ ] B-2  #40: whitelist universally-safe members (`Guid`, `Hvo`, `ClassID`,
      `ClassName`, `Best*Alternative`); track local casts so a var assigned from
      `IWfiAnalysis(...)` stops re-triggering; stop flagging arguments passed INTO
      Operations methods.
- [x] B-3  **DONE (spurt 3).** Neither option as framed: the ranking needed no
      repair (`_pick_cast_interface` already declines on ambiguity). Routed the
      `fix` string through the already-resolved interface, and softened ONLY the
      ambiguous branch to two-tier candidates-with-uncertainty.
- [ ] B-4  #97: flow-sensitive var types so mutually exclusive `if`/`elif` branches
      stop conflating on a shared variable name.

### EXPECTED SIDE EFFECT of CP-B -- read this before verifying

The gate currently **masks flexicon #254**. Per the user's trace, ops #8-#12 all
died on rejects or errors before printing anything, so wrong `GetMorphType` values
never reached output for four consecutive operations. #254 is owned outside this
crew and will very likely still be unfixed when CP-B lands.

Therefore, once the gate stops over-rejecting, scripts that read morph types off an
`IWfiMorphBundle` will begin **executing to completion and emitting wrong morph
types** -- `<MoAffixAllomorph>` / `<MoStemAllomorph>` instead of `prefix` / `suffix`
/ `stem`, or a `TypeError: object does not implement ICmPossibility`.

**That is #254 surfacing, not a regression introduced by the gate fix.** Do not
chase it, do not revert the gate, do not fix it here (flexicon is locked). Record
it and attribute it to #254. Surfacing bugs sooner is the stated point of fixing
the gate.

**Checkpoint:** the gate stops rejecting correct code on read-only runs; write-run
protection unchanged.

## CP-C -- discoverability (spurt 3)

- [ ] C-1  #100: set `access_path` in `analyze_class`
      (`flexicon_analyzer.py:1277-1344`) from `FLExProject.py`'s `@property` bodies
      (`self._x_ops = ClassName(self)`). Note: `access_path` currently greps clean
      across the whole MCP codebase -- it is a genuinely new key.
- [ ] C-1a #100 groundwork verified at spurt-2 planning: `access_path` does NOT
      exist in the codebase, and no existing index field substitutes for it.
      `usage_hint` is present on all 118 flexicon entities but is a generic
      template ("Provides operations for working with lexicon data in FieldWorks")
      and mentions `project.` in **0 of 118**. So the new key is genuinely needed.
      Entity keys today: `base_classes, category, description, example, id,
      lcm_dependencies, methods, name, namespace, properties, source_file, summary,
      tags, type, usage_hint`.
- [ ] C-2  #100 wrinkle -- CONFIRMED by the lead, with proof.
      `_build_entity_import` (`server/handlers/api.py:352-363`) ends in an
      unconditional `return f"from {library} import {entity_name}"` for flexicon and
      never inspects the entity dict at all -- it only receives name + namespace
      strings. It has FOUR call sites: `:410`, `:1092` (search_by_capability),
      `:1291` (find_examples), `:1617` (resolve_type). So adding `access_path` to
      the index alone would be silently ignored by every row builder, exactly as the
      peer suspected. Fix `_build_entity_import` to consult `access_path` and
      advertise `project.MSA` instead of a bogus import line; then confirm
      `paginate_entity`'s summary-mode field allowlist carries the new key
      (`handle_get_object_api`, `api.py:839-908`).
      **SIXTH AND SEVENTH SURFACES, found at spurt-2 planning:**
      `execution.py:1397` (`_inline_discovery_docs`, from `:1324`) and
      `execution.py:1493` (`_search_capability_inline`, from `:1450` -- an in-file
      CLONE of the search_by_capability row builder) both read
      `entity.get("import_statement")`. Verified that **0 of 118 index entities
      carry an `import_statement` key**, so both currently emit `null` -- they do
      NOT advertise a bogus import today, which is why CP-C can stay
      `execution.py`-free. They are a latent gap (no import guidance at all rather
      than wrong guidance); fix in a later checkpoint, and do not touch
      `execution.py` from CP-C while CP-B holds it.
**CP-C LANDED (cycle 3, `cea0ca6`).** Six files, zero touches to `execution.py`,
`validators.py`, `TOOL-CONTRACT.md` or any index JSON -- the lock discipline held.
New keys `access_path` and `not_cmpossibility_warning` are additive and optional,
so no contract-shape change was needed.

Corrections and discoveries from the implementation, all worth keeping:
1. **A premise in my own briefing was WRONG and the implementer caught it.** I said
   the index's `base_classes` already carried #101's inheritance fact. It does not
   -- `base_classes` is empty `[]` for all six relevant entities, because this
   extractor populates `interfaces` for interface entities, not `base_classes`. The
   real signal is `entity["interfaces"]` not containing `"ICmPossibility"`, which
   IS in the shipped index, so the read-path fix still needed no regeneration.
2. **#100's unverified suspicion was correct: `paginate_entity` DID need a fix.**
   It builds its own result dict rather than passing the raw entity through, so
   `access_path` did not surface via `get_object_api` in either mode until added
   explicitly.
3. **An EIGHTH import-advertising surface exists**: `paginate_entity`'s own
   `import_statement` builder on the `is_operations_class` branch. Left untouched
   because `MSAOperations` is not in `constants.KNOWN_OPERATIONS`, so it never fired
   for this bug -- but any facade-only class that IS in `KNOWN_OPERATIONS` would
   still be advertised with a bogus import. Latent; carry it.
4. **#101 is fixed with a CURATED frozenset, not a heuristic** -- and that was the
   right call. A structural rule ("own `Name` + no `ICmPossibility`") matches 76
   other liblcm entities (`CmAgent`, `CmFile`, `LangProject`, ...) that nobody ever
   mistakes for possibility lists. But a curated list is a maintenance liability: it
   cannot catch a fourth type with the same trap, which is exactly why #101
   pre-emptively included `IMoInflClass`. **#87's `interpretation`/`caveats`
   mechanism does NOT exist yet** (grepped clean), so the general facility is still
   owed. Revisit when #87 is picked up.
5. `access_path` lands on **55 of 118** flexicon entities, deliberately including
   classes that are ALSO top-level importable (`LexEntryOperations` is both), since
   `project.X` is always valid once a project exists and is what flexicon's own
   docs teach. Only `MSAOperations` is genuinely broken to import.
6. **CLAUDE.md's Quick Start smoke one-liner does not work as written** --
   `from src.server import ...` does not resolve because there is no
   `src/__init__.py`. The equivalent `from flextoolsmcp.server import ...` works.
   Pre-existing doc/packaging mismatch in the file every agent is told to read
   first. Cheap to fix; not this campaign's bug.

- [ ] C-3  #101: record the inheritance fact that `IMoInflAffixSlot`,
      `IMoInflAffixTemplate` and `IMoInflClass` are NOT `ICmPossibility` (their
      `Name` is each class's own `basic` attribute, a mere name collision with
      `CmPossibility.Name`). Reuse the `interpretation`/`caveats` field proposed in
      #87. **Do NOT over-broaden:** `IMoMorphType` genuinely DOES inherit
      `base="CmPossibility"`, so `ICmPossibility(morphType).Name` is correct there.

**Checkpoint:** advertised imports actually import; the ICmPossibility trap is
answerable from the index without a runtime TypeError.


---

## CP-D -- B-3 (#97 Bug 1) + carried P2s: CLOSED GREEN (2026-09-07, spurt 3, cycles 7-9)

Suite **1133 passed / 4 skipped / 12 subtests**; corpus **35 / 2**; casting
regression set **111 passed**. Verification PASS on all four CP-D code commits;
cycle-9 re-gate **no P0**.

Commits: `6e35204` (B-3), `71576a6` (D-2), `ce267e0` (D-3), `97bd304` (cycle-8
gate P0 + 4 findings); reports `eb66ac4`, `c6cbd25`, `4b43688`.

- [x] D-1 / B-3  #97 Bug 1 -- `fix` routes through the resolved interface;
      ambiguous cases emit two-tier candidates-with-uncertainty (2-6 listed with
      an explicit "alphabetical, not ranked, do not pick the first" warning;
      **>6 emits no interface names at all**). Message-only: severity,
      `cast_interface`, `rewrite`, `imports_needed`, `available_on` byte-identical;
      all four accept/reject quadrants re-verified. **#97 STAYS OPEN.**
- [x] D-2  versioning-cache flake -- reproduced for the first time (5/40, 1/40 in
      true isolation), 0/40 after pinning explicit directory mtimes via `os.utime`.
      Test-only; `versioning.py` untouched by design. **It exposed a real
      production defect -- see carryover.**
- [x] D-3  eighth import-advertising surface -- confirmed **no-op**: 43/43
      `KNOWN_OPERATIONS` members top-level importable in flexicon 4.5.2
      (independently re-confirmed by both gates). `handlers/api.py:689-692`
      unchanged; documented no-op + a tripwire proven REAL, not tautological
      (21/21 hazardous enrollments fail, benign control passes).

### Cycle-8 gate findings, all closed in `97bd304`

- **P0-1 contract drift** -- `docs/TOOL-CONTRACT.md:209-211` still described the
  `defined_on[0]` behavior and called Bug 1 "not yet repaired". Cycle 7's consumer
  audit had certified that exact file clean because it grepped the OUTPUT shape
  (`fix`, `Cast `) and missed the backticked MECHANISM name (`defined_on[0]`).
  Third contract-drift incident of this campaign. **Rule adopted: audit for
  mechanism names, not just output shapes.**
- **P1-1** D-3's rationale claimed MSAOperations was the only facade-only
  Operations class; really 13 of 64 are (8 more unreachable by either route). The
  no-op conclusion held; wording corrected and the tripwire widened.
- **P1-2** the 4-item alphabetical head still led with `ICmAgent` for `Name` -- the
  exact pairing #97 cited. Ruled a residual, not a regression (the old message was
  a bare imperative with zero uncertainty signal), but fixed before closing B-3
  because the headline symptom was still the first token a model saw.
- **P1-3** the escape hatch was circular and emitted a literal
  `context_entity=...` -- valid Python meaning nothing, i.e. copy-paste-broken.
- **P2** `_casting_candidates_for_fix` forked a second normalizer while its comment
  claimed it reused the first. Extracted `_clean_interface_head`
  (`validators.py:3414`, called at `:3456` and `:3515`); equivalence independently
  re-derived over 26,622 combinations + 14 adversarial inputs, 0 mismatches.
- **P2** `tests/test_flextools_health.py` claimed an unsupported "~15-25%";
  replaced with the real measured figures.

### CP-D carryover -- do not lose these

**Needs a USER DECISION (crew must not act):**

1. **The versioning stale-read race -- REAL, measured twice, needs a design call
   plus authorization to file.** `versioning._dir_state_token`
   (`versioning.py:277-295`) keys the file-discovery cache on bare
   `index_dir.stat().st_mtime` (`:323`, `:357`). Verification: **13.3% (40/300)**
   stale results via the real production functions, perfect mtime/staleness
   correlation. QC: **29% (58/200)** of rapid double-writes leave `st_mtime`
   unchanged. NARROW -- `server.py:351` clears the cache on in-process refresh, so
   only out-of-band writers are exposed and it self-heals on the next directory
   change. Note D-2 removed the last same-tick coverage, so that case is now
   covered nowhere. Docstring left deliberately uncorrected so the fix and the
   admission land together. Options: directory listing hash, write counter, or
   bypass-cache-on-miss.
2. **`CastingOperations.cast_to_concrete` is a PHANTOM REMEDY advertised in FIVE
   places** (incl. `handlers/discovery.py:163`) but proven NONEXISTENT in flexicon
   4.5.2. Same failure class as #103 and the import-advertising surfaces.
   PRE-EXISTING, not CP-D's doing. Caught only because the cycle-9 brief required
   verifying a remedy before advertising it. Needs authorization to file.
3. **MCP server PID 19808 still predates every fix.** #96's staleness remains
   UNVERIFIED; no live-LCM evidence is trustworthy until the user restarts it.

**P2/P3, crew-actionable in a later spurt:**

- `tests/test_issue100_access_path.py:399` assigns
  `facade = _extract_facade_access_paths(...)` and never reads it, implying a
  facade cross-check the tripwire does not perform (the hazard set is pure
  `hasattr`). Both gates confirmed the tripwire still works, so this is DEAD CODE,
  not a broken test. Either wire the facade check in or delete the assignment.
- **`fix` is heterogeneous across tiers** -- the known-pattern tier emits pasteable
  code (`validators.py:3910-3926`, documented `docs/CASTING_SYSTEM.md:34`) while
  the index-derived tier now emits prose containing a tool call. Pasted-into-script
  risk. Deferred: moving prose to `flexicon_helper` is a contract decision.
- **QC P2-2 (`validators.py:1022`) slash-joined pseudo-interface label** -- still
  carried, cosmetic (`imports_needed=[]` / `cast_interface=None` keep auto-fix out).
- **QC P2-3 (`admin.py:278-289`) primer wording nit** -- still carried,
  self-limiting.
- **Cross-repo item 6 still OPEN** -- whether the generated runner can call
  `SaveChanges()` right after `OpenProject`; `execution.py:3810` is the anchor.
- **flexicon #254 write-side twin (`SetMorphType`) still UNFILED** -- relay to
  whoever owns #254. The flexicon repo is READ-ONLY for this crew.
- Both helpers `IndexError` on a whitespace-only `defined_on` entry
  (`validators.py:3443`, `:3495`); none shipped, latent.
- The D-3 tripwire `skipTest`s when flexicon is unimportable, leaving it unguarded
  in a flexicon-less CI.
- `_bump_dir_mtime` writes future-dated mtimes (+1s/write).
- The ten `reportOptionalMemberAccess` findings in `handlers/api.py` are confirmed
  PRE-EXISTING and line-shifted, byte-identical to the parent commit's set. Not a
  CP-D defect; a decision on whether they are real latent issues is still open.

### Pyright tally for this campaign

**Ten-plus false positives** reported as real bugs across cycles, including
`fix_msg` "not accessed" at three sites and `_casting_candidates_for_fix` /
`_clean_interface_head` / `head` "not accessed" -- all from stale mid-edit
snapshots, all disproven by targeted runtime checks. **Never report a Pyright
finding without a confirming pytest / `--collect-only` / runtime check.**
