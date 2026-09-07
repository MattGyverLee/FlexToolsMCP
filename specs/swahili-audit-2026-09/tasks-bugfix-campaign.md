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

## Open blockers -- plan AROUND these, not through them

1. **#96 live repro: authorized by the user for `Target`, but preconditions
   UNMET.** `Target` has `projectSharing="false"`, so it would open exclusive and
   the write would be refused by the #93 access gate -- reproducing nothing -- and
   `Target` is not currently open in FLEx. Awaiting the user's authorization to flip
   `projectSharing` and to park FLEx on a non-editing view so
   `TopMarkHandle == 0` (`UnitOfWorkService.cs:249`). **Do not dispatch the repro
   until both are true.** Also: land A-8 (`ui=HeadlessLcmUI()`) FIRST, or repro
   step 4's `SaveChanges()` can hit `ConflictingSave()` as a modal dialog and hang.
2. **CP-B (item 3) severity downgrade: awaiting the user's answer.** See CP-B.
3. **Filing the liblcm `WriteCommitWork`/`FileGeneration` issue: awaiting the
   user's authorization.** Confirmed in source; citations ready in cross-repo item
   5 below. Do not file unprompted.

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

- [ ] B-1  #40: stop hard-rejecting on warning-severity casting issues. Per-issue
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
- [ ] B-3  #97: repair `_pick_cast_interface` ranking (it currently picks
      `defined_on[0]`, which is the arbitrary-selection defect #97 diagnosed), or
      soften the assertive `"fix": "Cast x to Y"` to candidates-with-uncertainty.
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
- [ ] C-3  #101: record the inheritance fact that `IMoInflAffixSlot`,
      `IMoInflAffixTemplate` and `IMoInflClass` are NOT `ICmPossibility` (their
      `Name` is each class's own `basic` attribute, a mere name collision with
      `CmPossibility.Name`). Reuse the `interpretation`/`caveats` field proposed in
      #87. **Do NOT over-broaden:** `IMoMorphType` genuinely DOES inherit
      `base="CmPossibility"`, so `ICmPossibility(morphType).Name` is correct there.

**Checkpoint:** advertised imports actually import; the ICmPossibility trap is
answerable from the index without a runtime TypeError.
