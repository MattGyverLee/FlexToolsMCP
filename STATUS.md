# Project Status

Active feature: **swahili-audit-2026-09 bugfix campaign** (cross-repo defect
follow-through from the live Claude-Swahili audit).
Spec: `specs/swahili-audit-2026-09/SPEC.md`.
Tasks + all durable crew state: `specs/swahili-audit-2026-09/tasks-bugfix-campaign.md`.
Branch: `feat/shared-mode-access` (shared with the feature below -- #96 is
shared-mode territory, so the campaign did not branch away).

Also active, same branch: **shared-mode-access** (let the user keep FLEx open).
Spec: `specs/shared-mode-access/SPEC.md`.
Issues: [#92](https://github.com/MattGyverLee/FlexToolsMCP/issues/92) (CP1 bug),
[#93](https://github.com/MattGyverLee/FlexToolsMCP/issues/93) (the feature).

Paused (not abandoned): **diagnostic-report**, which is green through CP3 and
whose next pickup is CP4 (docs + demo). Its section is retained below.

## Active campaign: swahili-audit-2026-09 bugfix

**CP-A -- data integrity: CLOSED GREEN (2026-09-06, spurt 1, cycles 1-2).**

Commits on `feat/shared-mode-access`: `cb3f1b8` (#103, closes it),
`0c9a59b` (#96 MCP-side halves), `8f72b9f` (contract drift found by QC),
`80630d8` (report). Suite **1052 passed / 4 skipped**. QC: no P0. Verification:
PASS on both code commits, non-live claims only.

- **#103 (hvo instability) is FIXED.** The GUID round-trip already shipped in
  flexicon -- `FLExProject.Object(hvoOrGuid)` accepts `str`/`System.Guid`
  (`FLExProject.py:3212-3226`) -- so no flexicon change was needed, only
  advertising it. Added the primer/tool-description warning plus a preflight gate:
  a bare int literal in an `*_or_hvo` position WARNS on read-only runs and HARD
  BLOCKS write runs (`hvo_literal_write_risk`, error codes 17 -> 18). QC ran 20
  adversarial snippets against the live index and could not construct a realistic
  false positive.
- **#96 (read-after-write staleness) root cause is CONFIRMED, and the bug is NOT
  fixed.** It is worse than filed: a non-master peer's commit lands only in the
  in-memory shared commit log, `.fwdata` advances only when the master writes, and
  a fresh open reads `.fwdata` and NEVER replays commit-log records. So a fresh
  read-only session **structurally cannot** see a peer's write, and the staleness
  window is **unbounded**, not 18 seconds -- the master's `SaveOnIdle` guards are
  human-gated. Full citations: `specs/swahili-audit-2026-09/reviews/bugfix-cycle1-explore-96.md`.
  Consequence for docs: never promise a safe read-back interval; there is no N
  that is safe.
- Two MCP-side halves of #96 fixed in `0c9a59b`: teardown commit failures no
  longer report success under a bare `except: pass`, and the generated runner now
  passes `ui=HeadlessLcmUI()` -- previously it passed no `ui=` at all, so a
  `ConflictingSave()` in a headless subprocess was a modal dialog, i.e. a hang.

**Scope note:** flexicon #254 (`GetMorphType` returns the allomorph) was
reassigned OUTSIDE this crew mid-spurt. The flexicon repo is under an advisory
file lock; this crew must not edit it. Cross-repo findings are recorded in the
tasks file rather than actioned.

**CP-B + CP-C -- CLOSED GREEN (2026-09-07, spurt 2, cycles 3-6).**

Commits: `b5f41d8` (casting gate: read-only severity downgrade for #40, plus
branch-aware variable typing for #97 Bug 2), `cea0ca6` (#100 `access_path` +
#101 non-ICmPossibility warning), `aba84d8` (primer + teardown test),
`d1f30da` (`validate_only` alignment + resolver hardening), `a1f6897` (the
cycle-4 P1 pair), `ffd4bf4` (primer scoping), `1e30148` (lexical-scope candidate
map + unblinded Tier-1 evals), plus report commits and `69626b9` (CLAUDE.md Quick
Start: three commands referenced paths that no longer exist, and "17 error codes"
was 18).

Final gate state: suite **1121 passed / 4 skipped**, eval corpus **35 passed / 2
skipped**. Verification PASS on every commit; QC no P0 across three passes.

- **#40 / #97 Bug 2 (the casting gate) is fixed.** Read-only runs no longer
  hard-reject on warning-tier casting issues; write runs still reject at every
  severity; detection and reporting are fully intact. Branch-aware variable typing
  eliminated #97 Bug 2's false positives (4/4 -> 0/4). Two P1s were found and
  closed along the way, both instances of one root defect -- the typo detector's
  inputs and the casting gate's inputs were not the same set. The most dangerous
  was a FALSE-NEGATIVE regression: the new resolver silently stopped reporting real
  typos in three code shapes on both read-only and write runs.
- **#97 Bug 1 is REPAIRED in spurt 3 (`6e35204` + `97bd304`) -- but #97 ITSELF IS
  STILL OPEN.** See the CP-D section below. Do NOT report #97 as resolved: only the
  user closes issues.
- **#100 / #101 are fixed.** `access_path` now records the real `project.X` facade
  path, and the load-bearing half was the read path -- `_build_entity_import` had
  four call sites that ignored the index entirely. #101 uses a curated set of the
  three trap types; `IMoMorphType`, which genuinely IS an `ICmPossibility`, is
  explicitly not flagged. #100 is DORMANT until someone runs an index refresh,
  which is entangled with the undecided v4.4.1 deletion below.

**CP-D -- B-3 (#97 Bug 1) + carried P2s: CLOSED GREEN (2026-09-07, spurt 3,
cycles 7-9).**

Commits: `6e35204` (the B-3 fix), `71576a6` (D-2 mtime flake), `ce267e0` (D-3
no-op), `97bd304` (the cycle-8 gate's P0 + four findings), plus report commits
`eb66ac4`, `c6cbd25`, `4b43688`. Final gate state: suite **1133 passed / 4
skipped / 12 subtests**, eval corpus **35 passed / 2 skipped**, casting
regression set **111 passed**. Verification PASS on all four CP-D commits; the
cycle-9 re-gate returned **no P0**.

- **#97 Bug 1 is FIXED, and the diagnosis in the issue was wrong.** The defect was
  never the ranking. `_pick_cast_interface` already returned `None` on genuine
  ambiguity by design, for a reason recorded on-record at
  `validators.py:3324-3337` (the Dennis cascade-failure pattern: a
  confidently-wrong rewrite is worse than no rewrite). The single leak was the
  `fix` f-string at the old `validators.py:4090`, which took `defined_on[0]`
  directly and therefore printed a confident "Cast x to Y" naming an arbitrary
  interface **right next to a `cast_interface: null`** on the same payload. The
  LLM reads the prose, not the null. `fix` now reuses the resolved interface, and
  ambiguous cases emit a two-tier candidates-with-uncertainty message: 2-6
  candidates are listed with an explicit "alphabetical, not ranked, do not pick
  the first" warning; **more than 6 candidates emits no interface names at all**,
  because a 4-of-36 alphabetical slice is uninformative and used to lead with
  `ICmAgent` for `Name` -- the exact wrong pairing #97 cited. Behavior is
  message-only: severity, `cast_interface`, `rewrite`, `imports_needed` and
  `available_on` are byte-identical, and all four accept/reject quadrants were
  re-verified.
- **#97 IS NOT CLOSED.** Bug 1 is repaired; the issue stays open (only the user
  closes issues).
- **D-2 (the versioning-cache flake) is fixed test-side, and it exposed a real
  production defect -- see the blocker below.** The flake was reproduced for the
  first time (5/40 and 1/40 in true isolation) and is 0/40 after pinning explicit
  directory mtimes via `os.utime`. `versioning.py` was deliberately NOT patched.
- **D-3 (the eighth import-advertising surface) is a confirmed no-op.** All 43
  `KNOWN_OPERATIONS` members are genuinely top-level importable from flexicon
  4.5.2 (re-confirmed independently by both gates), so `handlers/api.py:689-692`
  was left unchanged behind a documented no-op plus a tripwire proven real, not
  tautological (21/21 hazardous enrollments fail, benign control passes).
- **Process note worth keeping.** The cycle-8 gate caught a P0 contract drift at
  `docs/TOOL-CONTRACT.md:209-211`, which still described the `defined_on[0]`
  behavior and called Bug 1 "not yet repaired". Cycle 7's consumer audit had
  certified that exact file clean, because it grepped for the OUTPUT shape
  (`fix`, `Cast `) and missed the backticked MECHANISM name (`defined_on[0]`).
  This was the campaign's third contract-drift incident. **Audit for mechanism
  names, not just output shapes.**

### Next pickup -- spurt 4

No checkpoint is blocked by us. The carried P2/P3 list is in
`specs/swahili-audit-2026-09/tasks-bugfix-campaign.md` under "CP-D carryover".
Two items there need a USER DECISION before the crew can act (see BLOCKERS
below): the versioning stale-read race and the still-unrestarted MCP server.
(The `cast_to_concrete` phantom remedy was struck 2026-09-07 -- resolved by
`1f8e90b` / issues #112, #113; see item 5.) The #96 live repro remains available only
after the user restarts the MCP server.

### NEW BLOCKERS from spurt 3 -- one needs the user, neither is code
<!-- Was "both need the user"; item 5 struck 2026-09-07 as already resolved. -->


4. **A real latent production defect in the index cache, measured twice by two
   independent methods.** `versioning._dir_state_token`
   (`versioning.py:277-295`) keys the file-discovery cache on bare
   `index_dir.stat().st_mtime`, used at `versioning.py:323` and `:357`. Its
   docstring claims entry creation bumps directory mtime "on both Windows and
   POSIX, which is exactly the 'index changed' signal we need" -- true, but
   insufficient: the failure mode is mtime *resolution*, not whether mtime
   updates. Verification measured **13.3% (40/300)** stale results using the real
   production functions with no test help, with perfect mtime/staleness
   correlation; QC separately measured **29% (58/200)** of rapid double-writes
   leaving `st_mtime` unchanged. The race is REAL but NARROW -- in-process refresh
   clears the cache explicitly (`server.py:351`), so only out-of-band writers are
   exposed and it self-heals on the next directory change. `versioning.py` was
   left untouched on purpose, docstring included: correcting the docstring to
   admit a 13% race without either a fix or an issue to link would be worse than
   bundling both. **Needs: a design call (listing hash vs. write counter vs.
   bypass-cache-on-miss) and authorization to file.**
5. ~~**A phantom remedy advertised in five places.**
   `CastingOperations.cast_to_concrete` is advertised to users in FIVE locations
   (including `handlers/discovery.py:163`) but was proven **NONEXISTENT** in
   flexicon 4.5.2.~~ -- **RESOLVED; superseded by this file's own later entry.**
   The CP-D framing conflated two symbols with different statuses, and the real
   defect was fixed and filed in `1f8e90b` as issues **#112** and **#113**. No
   authorization is outstanding. Re-verified 2026-09-07 against the current tree:
   `CastingOperations` has **zero** occurrences in `src/` or `docs/` (the phantom
   Symbol A is gone), and every surviving advertisement -- `handlers/api.py:1621,1636`,
   `handlers/discovery.py:163,169`, `validators.py:3642,3927`,
   `templates/00-FLAVOR-GUIDE.md:110,167` -- names the correct
   `flexicon.code.lcm_casting` path. Symbol B is real and unary:
   `from flexicon.code.lcm_casting import cast_to_concrete` imports cleanly with
   signature `(obj)` (`flexicon/code/lcm_casting.py:408`). Caveat: verified against
   the sibling checkout on `main` (`7e0fdf2`), which is past the 4.5.2 release;
   `cast_to_concrete` predates the `flexlibs2 -> flexicon` rename (`9b82ffaf`),
   so it is long-standing rather than newly added.

### BLOCKERS -- all three need the user

1. **#96 live repro.** Authorized in principle for project `Target`, but
   preconditions unmet: `Target` has `projectSharing="false"` (so the write would
   be refused by the #93 gate, reproducing nothing) and is not open in FLEx. Needs
   authorization to flip `projectSharing` and to park FLEx on a non-editing view.
2. **CP-B's read-only casting-severity downgrade.** It lets previously-rejected
   scripts execute, so it is the user's call. Recommendation is with them.
3. **Filing the new liblcm bug.** `XMLBackendProvider.WriteCommitWork:518-527`
   returns without writing when the file changed underneath it, but
   `SharedXMLBackendProvider.WriteCommitWork:499` sets `FileGeneration`
   unconditionally afterwards -- metadata claims a flush that never happened.
   Confirmed in source; filing needs authorization.

## Active feature: shared-mode-access

**CP1 -- Fix the write path; delete undo: CODE COMPLETE, STATIC GATES GREEN,
NOT MERGEABLE YET (2026-08-14, spurt 1, cycles 1-3).**

Commits on `feat/shared-mode-access`: `8a4fae5` (the CP1 fix, closes #92 --
`d17105f` amended to carry the pattern audit) and `af79d81` (review trail +
SPEC Section 8). `main` is unmoved at `b8533f0`.

All six CP1 line-items (T1.1-T1.6) landed: `undoable=False` hardcoded at the
generated `OpenProject` call, the `undoable` session flag and its plumbing
removed, `flextools_undo_last_operation` and the whole dead Feature-3 undo
machinery deleted, the false "can reverse them across MCP sessions" warning
and the `undo_available`/`redo_available` fields removed, success no longer
reported over a run that emitted `report.Error`, and the end-to-end write
test added (`tests/test_issue92_write_path_e2e.py`, `requires_flex`).

Gate results:

- **Verification PASS** (cycle 2) -- `python -m pytest -q`: **961 passed, 3
  skipped**; `python scripts/validate_integrity.py all`: all 5 checks passed,
  21 tools.
- **QC 92/100 APPROVE** (cycle 3 re-review, was 75/100 FIX ISSUES in cycle 2).
  The cycle-2 pattern-audit gate **P0 block is cleared** and the cycle-2 **P1
  is RESOLVED**.
- **Domain** (cycle 2) -- CP1's semantics are correct as written; the only ask
  was a caller-facing retry note, now captured as **T6.7** under CP6.
- **Scope-creep check PASS** -- QC could not run `git diff` itself (no Bash in
  its tool grant), so the orchestrator executed it: `git diff d17105f 8a4fae5
  --stat` touches `tests/test_v1_3_0_upgrade.py` only (1 file, +14/-5), and
  the same diff scoped to `-- src/` is **empty**. Zero production files were
  touched by the amend. Recorded as a clearly-separated addendum in
  `specs/shared-mode-access/reviews/cycle3-qc.md`.

**CP1 is verified STATIC-ONLY.** Every green gate above is the test suite and
static review. The one gate that actually proves #92 is fixed -- driving a real
write against a real FieldWorks project -- has **not** been run, because it
needs a live FLEx target and the user's authorization. See the blocker below.

**CP1 pattern audit (from `8a4fae5`'s commit body):** no HIGH siblings. One
**[MED]** -- `src/flextoolsmcp/server/handlers/execution.py:326`, the
`"liblcm"` API-mode `OpenProject(self, projectName, writeEnabled=False)` stub
ignores `writeEnabled` and has no `undoable` param at all. It is dead today
(`_get_api_mode_imports()` has zero callers in `src/`), but it is the same bug
shape lying dormant: if rewired, CP1's hardcoded `undoable=False` call site
would `TypeError` against it. Left unfixed as out of CP1 scope. Two **[LOW]**
siblings (a safe-direction `modifyAllowed=False` default whose sole call site
always passes explicitly, and a flexicon index docstring that already
self-documents an identical landmine) are FYI only.

**Deferred -- NOW FILED as [#119](https://github.com/MattGyverLee/FlexToolsMCP/issues/119)**
(2026-09-08, SPEC.md Section 8): pre-existing P2 --
`docs/TOOL-CONTRACT.md:13-26` claims all success responses carry
`_contract`/`status`/`op_id`, but `run_module`'s raw success dict never does.
Verified at `execution.py:4723`: it returns `execution_result` verbatim and
never passes through `build_response_with_context()`, the sole `_contract`
stamper. Predates CP1.

**CP2-CP6 are UNSTARTED.** No access probe, no read-only-always-works path, no
shared-mode writes, no close-FLEx gate, no docs. CP1 was specced to ship
standalone and it does -- but only once the live check passes.

> **CORRECTION (2026-09-06, recorded at the bugfix campaign's CP-A close).** The
> paragraph above is STALE. Commits have since landed on this branch for CP2
> (`39d1caf`, access probe -- detection only) and CP4 (`6dc459a` + `4b70f74` +
> `db52c3a`, shared-peer write path with live evidence). Do not reason about merge
> scope from the "CP2-CP6 UNSTARTED" claim; reconcile this section against
> `git log origin/main..HEAD` first. The CP1 live-write blocker below is unaffected
> and still stands.

### MERGE READINESS (asked by the user, answered 2026-09-06; reconciled 2026-09-07): READY

The branch is 50+ commits ahead of `origin/main` and unpushed; re-derive the
exact count with `git rev-list --count origin/main..HEAD` rather than
trusting a recorded figure (the earlier "10" and "48" figures both went
stale within a day). The four items that previously blocked a merge are now
resolved or explicitly deferred by the user:

1. ~~**The CP1 live write check for #92 has still never been run**~~ -- **CLEARED
   2026-09-07.** The check was run with the user's explicit authorization and
   **BOTH legs PASSED**. See "RESOLVED -- the CP1 live write check" below. This
   was the binding blocker; it no longer blocks.
2. ~~**This section is stale**~~ -- **RECONCILED 2026-09-07** (this pass):
   commit count, index-migration status, and the spec-artifact call below are
   all re-derived against the current tree rather than carried forward from
   2026-09-06.
3. ~~**The flexicon 4.4.1 -> 4.5.2 index migration is uncommitted and
   undecided**~~ -- **DEFERRED 2026-09-07 by explicit user decision** ("We'll
   build new indexes before the next release"). The working tree was reverted
   to the committed v4.4.1 state (`common_patterns_flexicon-v4.4.1.json`,
   `python/flexicon_api_v4.4.1.json`, `python/flexicon_lcm_bridge_v4.4.1.json`,
   `liblcm/liblcm_api_v11.0.0.json`, `reverse_mapping_liblcm-v11.0.0.json`);
   `scripts/validate_integrity.py all` still PASSES against the committed
   v4.4.1 index even though the installed flexicon runtime is 4.5.2. The
   v4.5.2 artifacts (3 files) were preserved, untracked, outside the repo at
   `C:\Users\thoua\AppData\Local\Temp\claude\d--Github--Projects--LEX-FlexToolsMCP\6c4256f8-2cb3-439f-98c3-883ed21d18f5\scratchpad\index-migration-deferred\`
   for deliberate regeneration before the next release -- nothing from this
   migration is committed on this branch.
4. ~~**Two prior-session spec artifacts await a keep-or-drop call**~~ --
   **RESOLVED**: the user delegated the call, the lead ruled KEEP, and
   `specs/swahili-audit-2026-09/reviews/cycle1-domain.md` and
   `cycle1-explore-nullmorph.md` are committed this cycle.

Safe on merge -- CORRECTED (cycle 12 adjudication, see
`specs/swahili-audit-2026-09/reviews/cycle12-adjudication.md`): the "FOUR
closing-keyword mentions across THREE commits" claim above was itself
stale. A full re-scan of `origin/main..HEAD` found FIVE closing-keyword
mentions across FIVE commits, targeting THREE distinct issue numbers:
`97bd304`'s body ("(closes #97 Bug 1)"), `6e35204`'s body ("closes #97 Bug
1"), `cb3f1b8`'s subject ("(closes #103)"), `250469c`'s body ("closes #103",
quoting cb3f1b8), and `69e0260`'s body ("residual of closed #74"). GitHub
parses closing keywords anywhere in a commit message, not just the first
one, so a merge to `main` will auto-close #97, #103, and re-trigger a close
action on #74. The `69e0260`/#74 mention is a no-op: issue 74 is already
CLOSED going into the merge, so it is expected to remain CLOSED and
untouched in substance -- see the adjudication doc for the full four-ground
ruling. #103's close is expected and accepted -- this document's own "#103
genuinely is fixed" finding stands. #97 is NOT resolved (only Bug 1 of #97
is; Bug 2's ranking fix is deliberately deferred as B-3) and must be
REOPENED immediately after the merge lands. Nothing in range auto-closes
#96, #40, #100 or #101 -- those four remain open by design.

### RESOLVED -- the CP1 live write check (2026-09-07): BOTH LEGS PASS

**This no longer blocks a merge.** Run 2026-09-07 with the user's explicit
authorization ("go. mutating Sena is fine"), FLEx closed:

```
FLEXTOOLSMCP_E2E_SCRATCH_PROJECT="Sena 3"
pytest tests/test_issue92_write_path_e2e.py -m requires_flex -v
-> test_setgloss_persists_across_close_and_reopen              PASSED
-> test_applysyncableproperties_persists_across_close_and_reopen PASSED
   2 passed in 29.71s
```

Independent disk-level confirmation, not just the tests' own assertions: the
marker `cp1-asp-3e1d2c0a` appears twice in `Sena 3.fwdata` (the `Definition`
and `ScientificName` writes), file mtime 2026-09-07 12:33:28, size grown
55989135 -> 55989325 bytes. So the multi-mutation path reached DISK, which is
the whole point of the check.

Two corrections to what this section used to say:

- **The scratch project cannot be `Target`.** A first run against `Target`
  failed both legs with `IndexError: list index out of range` at
  `entry = entries[0]`. `Target` has **0 LexEntry and 0 LexSense records**
  (verified directly in its `.fwdata`); so does `GT038 NKP2 Throwaway`. Neither
  can host this test. `Sena 3` has 1464 entries / 1728 senses. Note the
  campaign handoff's `target_preconditions: MET` was about **#96** and does not
  extend to #92.
- **The "gap to close by hand" below is stale.** Both legs are automated now --
  `test_applysyncableproperties_persists_across_close_and_reopen` exists and
  covers the multi-mutation `TypeError` path alongside the simple-setter
  `InvalidOperationException` path. There is no manual leg; the single pytest
  command above is the whole of SPEC Verification step 1.

Incidental evidence from the failed `Target` run, still worth keeping: the
session opened with `writeEnabled=True with an explicit undoable=False` and
preflight passed at `tier=none`, i.e. CP1's hardcoded fix was demonstrably
live in the running code even before the passing run.

The original blocker text follows, kept for the procedure and the rationale.

---

**(HISTORICAL)** Do not merge `feat/shared-mode-access` to `main` until this passes. CP1 is
a write-path fix whose entire point is that writes reach disk; every test that
currently passes stubs `run_script_async`, which is exactly why the original
#92 breakage survived 27 `write_enabled: true` runs undetected. A static-only
green board cannot close this bug.

SPEC.md Verification step 1: with **FLEx closed**, `run_module` a `SetGloss`
**and** an `ApplySyncableProperties` against a disposable scratch project, then
reopen and confirm both persisted.

The automated half (`SetGloss`) is written and skips by default:

```
set FLEXTOOLSMCP_E2E_SCRATCH_PROJECT=<disposable-project-name>
pytest tests/test_issue92_write_path_e2e.py -m requires_flex -v
```

- The project must be **disposable**, must have at least one entry with at
  least one sense, and must not be open in FLEx.
- **Pass looks like:** `test_setgloss_persists_across_close_and_reopen` PASSES.
  It drives the real `flextools_run_module` handler (not a stub), sets a gloss
  to a unique marker, closes the project, reopens it, and asserts the marker
  survived the round trip. A pre-CP1 build fails this.
- **Gap to close by hand:** the test file covers **`SetGloss` only**. The
  `ApplySyncableProperties` leg of Verification step 1 has no automated
  coverage yet -- run it manually against the same scratch project, or add a
  second case to that file, before calling step 1 done.

This is a live, mutating operation against a real FieldWorks project. The crew
will not run it unattended; only the user authorizes it.

## Next pickup -- shared-mode-access

> **SUPERSEDED 2026-09-08 (cycle 8).** This section is a historical record of the
> CP1 hand-off. The live authority is the final section of this file,
> "shared-mode-access (#93) -- spurt 5 CLOSED GREEN (cycle 8)", plus
> `specs/shared-mode-access/.crew-handoff.json`.

1. ~~User runs the CP1 live write check above and reports the result.~~ **DONE
   2026-09-07 -- PASSED (both legs, against `Sena 3`). See the RESOLVED section
   above.** The remaining merge blockers are the index migration, the
   `cycle1-*.md` keep-or-drop call, and the stale-section reconciliation --
   none of which are live-verification items.
2. On pass: merge CP1 to `main` closing #92, then start **CP2 -- access probe**
   (`project_access.py`, `read_lock_holder`, `probe_project_access`), which is
   new detection with no behavior change.
3. On fail: reopen CP1 with the live failure output; do not proceed to CP2.

## Where we are (paused feature: diagnostic-report)

**CP1 -- Foundation: COMPLETE and green (2026-07-13).** All six checklist items
landed; both cycle-2 P1s resolved (`save_store` fail-open fixed in cycle 3;
casting-recurrence heuristic deferred into CP2 and now closed there). See
`specs/diagnostic-report/tasks.md` CP1 checkpoint for detail.

**CP2 -- Reconstruction + normalization: COMPLETE and green (2026-07-13, spurt 2,
cycles 4-6).**

All six CP2 line-items landed: slice reconstruction, rotation stitching,
`MAX_REPORT_OPS` summarize-not-drop, path-scoped machine-hygiene normalization,
report rendering, and casting-recurrence signature precision. Gate results:

- **Verification PASS.** Full suite **511 passed / 0 failed** (+1 from the 510
  baseline, no regressions). All six spec section-12 Reconstruction clauses are
  test-backed; zero forbidden imports.
- **Domain E2 privacy gate PASS** -- home-dir / OS-username substitution is
  anchored on path-shaped tokens only, never a document-wide username
  find/replace.
- **Cycle-2 casting-recurrence P1 CLOSED** -- real `casting_signature` threaded
  into the JSONL schema; recurrence keys on it, not the bare code.
- **Cycle-6 post-auto-fix stale-`issues` P1 FIXED + verified.** Cycle 5 found
  that `handlers/execution.py` left `issues` bound to the pre-auto-fix casting
  set after the Issue #46 auto-fix reran `detect_casting_needs`, so a partial
  auto-fix reported the stale (resolved+residual) set instead of only the
  residual issue. Fixed by re-deriving `issues` right after the post-fix
  `casting_check` reassignment; regression test
  `test_partial_auto_fix_reports_only_residual_casting_issue` confirmed failing
  pre-fix and passing post-fix. See `reviews/cycle5-*` and `reviews/cycle6-*`.

**CP2 carryover (P2, non-blocking):** two P2s deferred to harden during CP3 --
`reconstruct.py` mismatched-`End` silent truncation, and `render.py`
`_CODE_STOP_MARKERS` substring false-positive.

**CP3 -- Surface + transport + guard: COMPLETE and green (2026-07-13, spurt 3,
cycles 7-9; commit e5ef733).**

All five CP3 line-items landed and are green: `flextools_prepare_report` tool,
the `diagnostic_report` advisory block on `RunModuleSuccess`, the three
transports (`gh` CLI / prefilled issue URL / `mailto:`), the
`likely_contains_lexical_data` code-shape flag, and the two-layer
no-transmission guard. Cycle-8 gates:

- **Verification PASS.** Full suite **577 passed / 0 failed** (511 + 66 new,
  matches exactly, no regressions). Two-layer no-transmission guard confirmed
  (static AST ban unconditional across all socket import styles; dynamic layer
  drives all three transports with zero invocations, exactly one write each).
- **QC 92/100 APPROVE, 0 P0 / 0 P1.** Fail-open contract on
  `build_advisory_for_success_close` verified total. Five P2s recorded as CP3
  carryover in `tasks.md`.
- **Domain 4/5 code-pass.** Items 1-4 pass (sensitivity-by-shape, path-scoped
  normalization, structural never-auto-send, preview fidelity). Item 5 was the
  abandoned-turn auto-offer gap below; now accepted as scope (documented v1
  limitation), which `tasks.md` renders as 5/5 accepted-scope.

**CP3 BLOCKER RESOLVED -- maintainer decision: option (c) (2026-07-13, cycle-9
doc pass).** Domain item 5 (the `diagnostic_report` auto-offer attaches only at a
same-turn `ok` close, so a reportably-failed-then-**abandoned** turn never
auto-offers -- the canonical unreported-inconsistency case from §1) is **not a
code defect**; it is the trigger-timing consequence of maintainer-resolved Q5
(advisory on `RunModuleSuccess` only). The maintainer chose **option (c): accept
it as a documented v1 limitation**, with recovery via the explicit
`flextools_prepare_report` tool (plus Claude proactively offering it on an
un-actioned reportable failure). Documented in **SPEC.md §6.5/§10** and
`tasks.md` CP3; a future revisit is tracked in
[issue #72](https://github.com/MattGyverLee/FlexToolsMCP/issues/72). Q5 itself is
unchanged -- option (c) accepts the consequence rather than reopening the
mechanism.

## Next pickup for diagnostic-report (paused) -- CP4 (docs + demo)

CP3 is closed; the feature is **not** complete. When diagnostic-report resumes,
the next spurt starts **CP4 -- docs + demo** (see `tasks.md` CP4 line-items, currently "not started"). Fold the CP2+CP3
P2 carryover (eight items, listed in `.crew-handoff.json` `carryover_p2` and in
`tasks.md`) into CP4 or a follow-up as appropriate -- all non-blocking.

## Housekeeping note (not part of diagnostic-report)

The working tree carries unrelated pre-existing changes to
`src/flextoolsmcp/server/validators.py` and
`tests/test_validator_cluster_fixes.py`. These are NOT part of the
diagnostic-report feature -- do not sweep them into a diagnostic-report commit;
commit or revert them deliberately on their own.

## Closed interrupt: inheritance-resolution (#85 / #86) -- CLOSED, was not part of diagnostic-report

A separate, higher-priority bug chain (#85 navigation-path crash -> #88 BFS
reconstruction bug -> #86 inherited properties hidden from `get_object_api` /
`resolve_property`) was worked as its own feature,
`specs/inheritance-resolution/SPEC.md`, in parallel with diagnostic-report.
The feature is now COMPLETE and closed out as of 2026-08-13 (cycle 6
close-out -- see `specs/inheritance-resolution/reviews/cycle6-archivist.md`).
Diagnostic-report (above) is once again the sole active feature; this
section is retained as the historical record of the interrupt.

**CP1 -- Navigation path actually works: COMPLETE and green
(commit `d693e26`, closes #85 and #88).** `find_path_bfs()` reconstruction
fixed; `IFsFeatStruc -> IFsFeatDefn` verified resolving its real 2-hop path;
`ILexSense -> IFsSymFeatVal` verified still `found:false` for the *correct*
reason (missing downcast edge, not a bug).

**CP2 -- Inheritance merge: COMPLETE and green (commit `13f69f8`, #86
read-path).** `collect_inherited_members` merges ancestor-declared members
into `get_object_api` / `resolve_property` for `I*` interface entities;
additive `inherited_from` / `*_including_inherited` fields; `has_more`
repointed to combined totals (DEC-7). Canonical case `IFsClosedValue`: 2 own
-> 31 total properties, `FeatureRA` now visible. Issue **#86 CLOSED this
cycle** (cycle 6, status comment recorded by the main session). Class-side
(non-`I*`) ancestor merging is explicitly **descoped from #86**, not left as
an open policy question blocking the issue -- it is tracked separately in
`specs/inheritance-resolution/SPEC.md` section 6 item 4, blocked on an
override-semantics policy, with its own issue still to be filed when picked
up.

**CP4 -- Docs: COMPLETE, independently verified (cycles 4 + 5), and
COMMITTED as `f930908`** ("docs: complete the #86 inheritance-resolution
contract docs (CP4)"). A parallel `/lex-doc` pass in cycle 4 wrote
`docs/TOOL-CONTRACT.md`, `CHANGELOG.md`, and the new
`docs/LIBLCM_EXTRACTION_SEMANTICS.md`; concurrency gate cleared when
`bd066a0` landed the other crew's `workspace_notice` work and #90 closed. A
cycle-5 precision pass then closed four gaps found while verifying that
landing (`specs/inheritance-resolution/reviews/cycle5-doc.md`):

- **P1** -- `total_methods_including_inherited` was documented nowhere. Now
  has its own contract table row (`docs/TOOL-CONTRACT.md:198`) and is named
  in the CHANGELOG bullet (`CHANGELOG.md:112-115`).
- **P2** -- TOOL-CONTRACT over-claimed that both `*_including_inherited`
  totals come from `resolve_property`; they are `paginate_entity()`-only and
  appear on `get_object_api` alone. Lead sentence reworded (lines 183-192).
  Stale citation `api.py:420` corrected to `api.py:575` (line 214).
- **P3** -- "this fields" -> "these fields" (line 201); the
  "full transitive closure" claim in `LIBLCM_EXTRACTION_SEMANTICS.md:9` now
  carries the real exclusion caveat (`IDisposable`, `IEnumerable`,
  `IComparable` are filtered out at `liblcm_extractor.py:700`).

All four re-verified against source by lex-lead on 2026-08-13. Regression
suite green and unchanged from cycle 4: `pytest
tests/test_issue86_inheritance_resolution.py
tests/test_issue85_navigation_path.py -q` -> **31 passed**. No `.py` file was
modified in cycles 4-5 (docs-only). CP4 docs were committed in cycle 6 as
`f930908`.

**Resolved (was Deferred P2): `total_methods_including_inherited` test
coverage.** Cycle 6 added two tests to
`tests/test_issue86_inheritance_resolution.py` --
`test_total_methods_byte_identical_own_only` (line 178, unfiltered branch
`api.py:634-635`, `IFsClosedValue` 0 own / 14 combined) and
`test_total_methods_including_inherited_counts_filtered_inherited` (line
192, filtered branch `api.py:630-631`, `IReversalIndex` 1 own / 2 combined,
pinning the own-then-inherited ordering). Both were independently certified
by the verification agent via two separate targeted mutations (api.py:630
`<` -> `<=`, and api.py:635 `len(methods)` -> `len(methods) - 1`), each
breaking exactly the predicted test with the predicted assertion error;
full suite re-run green after revert: **979 passed, 2 skipped, 0 failed**.
See `specs/inheritance-resolution/reviews/cycle6-verification.md`.

**CP3 -- `required_cast` downcast edges: design ready, FILED as
`#91`, NOT started.** Draft body in
`specs/inheritance-resolution/PROPOSED-ISSUE-cp3.md` was corrected in cycle
6 (wrong script attribution, crew-internal cycle numbers replaced with
commit hashes, and a clarifying paragraph on why #86's mechanism cannot
cover this case) and then filed with explicit user authorization.

**Feature status: CLOSED (cycle 6).** All checkpoints (CP1-CP4) are landed,
committed, and verified; #86 and #85/#88 are closed; CP3 is filed and
tracked as its own issue for future work. The repo's active feature reverts
to diagnostic-report (line 3).

## Log-triage run: 2026-09-07 (merged August + September window scan)

Three peer `/lex-logscan` agents scanned in parallel (August window
2026-08-10 -> 2026-08-28, September window 2026-09-06/09-07) and filed
concurrently; this archivist pass performed the single consolidated write to
`docs/logscan-state.json` plus two cross-link comments. Full ledger detail
and before/after values: `specs/logscan-2026-09-07/reviews/cycle2-archivist.md`.

**Filed (7 new issues):** flexicon #260-#263 (AllomorphOperations missing
IMoForm cast; DataNotebookOperations raw `LcmCache.GetObject`; undocumented
`KeyNotFoundException` on a stale GUID; `FLExProject.pyi` `WriteEnabled`
stub/impl casing drift) and MCP #108-#110 (polymorphic-cast hint quality,
three merged facets; harness telemetry leak to a cwd-relative
`operations.jsonl`; `operations.log` silently lost 10 days across rotation).

**Commented (14 targets, no state changes):** flexicon#34, flexicon#257;
MCP #93, #70, #40, #101, #100, #98, #74 (comment-only, not reopened); MCP
#84, #39, #75, #80, #69 (regression comments on closed issues, comment-only).

**Ledger corrections applied:** six stale `state: open` entries (issues #39,
#48, #80 [retargeted from a wrong #53 attribution], #69, #75, #74) were
verified against live GitHub and corrected to their real closed states,
all closing within ~36 hours of the 2026-07-20 ledger write that went stale.
The #48 aggregate bucket was re-marked `closed-not-a-tracker` with a causal
note (the stale state is what caused the September scanner's mis-dedup
against it).

**Awaiting user confirmation (nothing below was acted on without it):**
1. `.gitignore` edit to add `operations.jsonl*` / `operations.log*` -- not
   made this run (out of this agent's authorized scope).
2. Removal of the stray repo-root `operations.jsonl` (harness leak, see
   MCP#109) -- not deleted; a copy should be preserved as evidence first if
   removal is approved.
3. The ranked reopen recommendation for the five regression-commented closed
   issues: **#84 > #39 > #80 > #69 > #75** (differs from the lead's original
   ordering -- #80 was moved up because its recurrence is a hard
   `preflight_reject`, the exact behavior #80's own fix was supposed to
   replace with a soft advisory). No issue was reopened.
4. Explicit decision **NOT** to close #40 -- it stays open for facets beyond
   the B-1 mitigation already confirmed live in production this scan.

### Follow-up: user-authorized reopens + cleanup (2026-09-07, same day)

The user authorized lex-lead's ranked reopen recommendation and the two
pending cleanup items above. All four are now actioned:

- **Reopened, ranked 1-4 of 5:** MCP#84 (documentation-only fix could not
  plausibly have prevented the identical AttributeError recurring 58 minutes
  after close), MCP#39 (10 recurrences matching the window's entire
  PolymorphicAttributeError tally, at least two NOT user casting mistakes --
  one a library-internal flexicon bug now flexicon#261, one a discoverability
  trap now MCP#108 facet a), MCP#80 (recurred twice as a HARD
  `preflight_reject`, precisely the behavior Part 1 of its own fix was meant
  to replace with a soft advisory), MCP#69 (recurred with a second wrong
  guess at the same target in the same session, so the user was never
  steered to `project.lp` either time).
- **Deliberately left closed (not reopened), with reasons on record:**
  MCP#75 (rank 5 of 5 -- the recurrence is at a third, previously
  unenumerated call site, `ISilDataAccess.BeginUndoTask`, so the original fix
  holds for its known sites while the gap generalizes; tracked instead by new
  MCP#111) and flexicon#34 (a cookbook issue whose docs fix was the correct
  deliverable; the verbatim 3-month recurrence points at a surfacing gap in
  `find_examples`/`search_by_capability`, not a bad fix -- contrast with
  MCP#84, reopened on the opposite reasoning).
- **New issue filed:** MCP#111 -- overload-resolution hinting is per-call-site
  rather than general; asks for a mechanism that parses the pythonnet
  `OverloadResolutionError` shape and emits candidate signatures from the
  liblcm index instead of enumerating sites one at a time.
- **Cleanup completed:** the stray repo-root `operations.jsonl` was removed
  after a byte-identical copy was preserved at
  `specs/logscan-2026-09-07/evidence/stray-root-operations-2026-09-07.jsonl`
  and its contents inlined into a comment on MCP#109; `.gitignore` now
  ignores `operations.jsonl*`/`operations.log*`, closing the
  accidental-commit exposure (the underlying `log_dir_fn` defect itself
  remains open, tracked by MCP#109).

Full before/after ledger detail: `specs/logscan-2026-09-07/reviews/cycle3-archivist.md`.
The only remaining un-filed follow-up from this run is the FlexToolsMCP-side
recipe-surfacing gap implied by flexicon#34 (no issue number assigned yet;
scope decision pending).

## swahili-audit-2026-09 -- CP-E closed green (spurt 4, 2026-09-07)

Spurt 4 resumed on the user's "continue" and closed **CP-E**. Suite
**1138 passed, 4 skipped, 12 subtests** (1133 entering the spurt, +5 new tests,
no regressions). Verification PASS on all 8 gate items, every number re-derived
from the code rather than from the reports. Branch is **45 commits ahead of
origin/main, unpushed** (46 including this closing commit).

**What landed:**

- **The `versioning` stale-read race is FIXED** (`36a5a1c`). `_dir_state_token()`
  moved off a bare `st_mtime` to a hybrid `(dir_mtime, entry_count,
  max_child_mtime)` token from a single `os.scandir()` pass. The overclaiming
  docstring was corrected in the *same* commit, as designed at CP-D, so the fix
  and the admission landed together. Deterministic same-tick RED/GREEN tests
  restore the coverage D-2 had removed.
- **The `cast_to_concrete` phantom remedy split into two different bugs, both
  fixed and filed** (`1f8e90b`; issues **#112** and **#113**). The CP-D framing
  ("five places, nonexistent") had conflated two symbols with *different*
  statuses. Symbol A (`CastingOperations.cast_to_concrete`) is a true phantom --
  zero occurrences in pyflexicon 4.5.2 -- but confined to 5 advisory strings.
  Symbol B (`flexicon.code.lcm_casting.cast_to_concrete`) is **real but unary**
  while every shipped call site passed two arguments, and two docs imported
  `ILexEntry` from a module that never exports it. That made the LibLCM template
  **served by `flextools_get_module_template`** crash at runtime -- code users
  run, not just a hint they read. Verified through the served path, not by
  reading the template file.
- The dead `facade` assignment at `tests/test_issue100_access_path.py:399` is
  gone (`ffafb8c`), and `test_issue48_inline_casting.py` -- previously this
  campaign's own example of an assertion that passed both before *and* after its
  bug -- was tightened and proven to bite.
- **The `#96` restart precondition is now MET.** Old PID 19808 is dead; PID 4556
  serves this session and postdates every fix, confirmed on three independent
  read-only lines of evidence. Live evidence would now be trustworthy.
  **`#96` staleness nonetheless remains UNVERIFIED** -- the repro was not run and
  is not authorized.

**MCP#80: the campaign answered the question, and found the trap in the answer.**
The other crew reopened #80 because it recurred as a hard `preflight_reject`,
the exact behavior its own fix was meant to soften. Cycle 10 proved at runtime
that CP-B's severity downgrade is *unreachable* for #80's code (its entry guard
sees no casting issues at all) and that the reject fires ~200 lines later at
`execution.py:3138`, where `if write_enabled:` keys a hard gate on the **session
write flag** rather than on whether the submitted code mutates. Both recurrences
were certified-read-only introspection in a write-enabled session.

The obvious fix -- key the gate on `cert["is_certified_readonly"]` -- **is a
data-integrity hole**. The certifier's own contract (`validators.py:2969`) defines
that field as "no *unprotected* mutations", not "no mutations", and keeps
`protected_liblcm_calls` in a separate bucket. So code that mutates inside an
`if modifyAllowed:` guard certifies `True`, and the naive fix would let guarded
mutations run **without discovery in a write-enabled session** -- opening a write
hazard while closing an over-refusal. The safe form is a conjunction requiring
provably no mutation of any kind; it is recorded in full in
`specs/swahili-audit-2026-09/.crew-handoff.json` under `mcp80_fix_design`.

**STOPPED: `status: needs_human`.** The fix is designed, proven, and ready, but
it relaxes a gate on a **write-enabled** session, whereas the user-approved B-1
precedent only relaxed read-only runs where no write was possible even if the
checker erred. The gate was left alone deliberately -- its own comment reads
"Write isolation is non-negotiable". CP-B escalated the equivalent "lets
previously-rejected scripts execute" call to the user rather than deciding it,
so this crew is holding to that precedent rather than stretching the standing
"fix and file at your discretion" delegation across that line.
**Lead recommendation: authorize, using the conjunction predicate.**

`#97` stays **NOT-CLOSED** -- Bug 1 is repaired, the issue is not. No issue was
closed, commented on, or reopened this spurt; only #112/#113 were filed. The
never-run CP1 live write check for `#92` remains the **binding** merge blocker.
The flexicon 4.4.1 -> 4.5.2 index migration and both `cycle1-*.md` reports are
still preserved byte-for-byte, awaiting a user call.

## Campaign closed: swahili-audit-2026-09 + shared-mode-access merged as PR #114 (2026-09-07)

The combined branch `feat/shared-mode-access` -- carrying both the
shared-mode-access feature and the swahili-audit-2026-09 bugfix campaign --
merged to `main` as **PR #114, merge SHA `ae73eef`**, a true two-parent merge
(parents `f0089a4` and `7a75232`; not a squash, not a rebase). The branch was
fully absorbed (`git diff origin/main origin/feat/shared-mode-access --stat`
is empty) and left on the remote, undeleted. The binding merge blocker -- the
never-run CP1 live write check for #92 -- was cleared earlier in spurt 4
(both legs PASSED against `Sena 3`, with disk-level confirmation); nothing
else in `merge_blockers_remaining` was ever binding, since the index
migration and the two `cycle1-*.md` reviews were untracked working-tree
state that cannot enter a merge, and the STATUS.md stale-section
reconciliation was already done. See `.crew-handoff.json`'s
`merge_blockers_retired_cycle14` for the full accounting.

**Post-merge CI on `main` is GREEN across all three matrix jobs** (run
`34165957555`: py3.10-windows 3m36s, py3.12-windows 3m31s, py3.12-ubuntu-no-flex
2m31s) -- the **first green run on `main` since 2026-08-12**.

**Issue states after the merge** (`gh issue view <n> --json number,state`,
independently re-derived, not trusted from any report):

| Issue | State | Why |
|-------|-------|-----|
| #97   | **OPEN** | The merge mechanically auto-closed it via pre-existing closing keywords in commit bodies `6e35204`/`97bd304`; the main session ran `gh issue reopen 97` immediately and left an explanatory comment (id `5576130418`). #97 stays open on purpose: only Bug 1 (the ranking/`fix`-string leak) is repaired -- Bug 2's variable-typing fix landed separately in CP-B/C -- and only the user closes issues. |
| #103  | CLOSED | Expected auto-close from `cb3f1b8`. Substantively reasonable (18 new tests, an `hvo_stability` primer block, and a hard write-gate all target the issue's stated defect), but it does not change liblcm's underlying per-session hvo renumbering and one cross-repo flexicon doc example remains unfixed -- so whether #103 should stay closed or be reopened to track that follow-up is a **user call**, not decided here. |
| #74   | CLOSED | Already closed *before* this merge; not attributable to it. |
| #115  | OPEN | Untouched by the merge, as expected. |
| #100  | OPEN | Untouched by the merge. Genuinely still live: the tracked `flexicon_api_v4.4.1.json` does not carry `access_path` for `MSAOperations` (a prior programmer report claiming otherwise was disproved by direct JSON inspection at cycle 13 verification). Depends on the index migration below. |
| #96   | OPEN | Untouched by the merge. Staleness remains **unverified** -- the restart precondition is met (a fresh MCP server PID postdates every fix) but the live repro itself was never authorized or run. |
| #80   | OPEN | Untouched by the merge. Reopened by a separate crew as a hard `preflight_reject` recurrence; this campaign's cycle 10 proved the reject fires at `execution.py:3138`, and designed (but did not implement) a safe conjunction-predicate fix -- see below. |

**Remaining USER decisions** (nothing further is dispatchable without one):

1. **MCP#80 gate-design authorization.** The fix at `execution.py:3138` is
   designed and proven (`mcp80_fix_design` in `.crew-handoff.json`) but
   relaxes a hard gate on a **write-enabled** session -- a step beyond the
   user-approved B-1 precedent, which only relaxed read-only runs. Needs
   explicit authorization before any code change; `execution.py:3138`
   remains in `do_not_touch` until then.
2. **#96 live repro authorization.** Preconditions are now met (server
   restarted, postdates every relevant fix), but this campaign will not run
   a live, potentially dialog-hanging repro without the user's go-ahead.
3. **The flexicon 4.4.1 -> 4.5.2 index migration.** Deferred by the user's
   own prior decision ("we'll build new indexes before the next release");
   the working tree's v4.4.1 files are the committed, load-bearing index and
   must not be replaced ad hoc. Blocks #100 from going fully live.
4. **Whether #103 stays closed.** The auto-close is substantively reasonable
   but incomplete (see table above); a user ruling decides whether to leave
   it closed or reopen to track the unfixed flexicon-side follow-up.

Two carried process notes worth keeping visible: `scripts/check_project_accessors.py`'s
drift check is wired into zero CI workflows (local/manual-only protection,
conceptually tracked by #115), and the two in-place `test_issue100_access_path.py`
full-suite failures are a working-tree artifact of the untracked v4.5.2 index
sitting beside the committed v4.4.1 index -- a clean worktree at `HEAD` gives
1135 passed / 0 failed.

## shared-mode-access (#93) - spurt 4 in progress

STATUS.md's prior tail covered the swahili-audit / MCP-issue campaign only;
this section tracks the shared-mode-access spurt that followed PR #114, per
`.crew-handoff.json` (authoritative for this feature -- `.spec-context.json`
is unreliable here and should be ignored).

**Checkpoint state:**
- CP2: DONE (`39d1caf`).
- CP3: CODE ACCEPTED, unconditional -- the P1-1 atomicity fix landed across
  `6677fd8` + `520dba4` and QC confirmed it atomic. Sign-off is blocked ONLY
  on a live FieldWorks observation (a sharing-off project, FLEx open, must
  return the enable-sharing recipe rather than the generic lock hint); no
  code work remains.
- CP4: code done; the live `open_shared` gate observation (write with FLEx
  actually running, change visible in the FLEx UI) is the outstanding half.
- CP5: scoped (`cycle5-cp5-scope.md`) and the SPEC amended this cycle
  (Section 3 split, T5.1/T5.3/T5.5 drift fixed, new T5.6) -- not yet
  implemented.
- CP6: partial -- CHANGELOG entries (T6.5) done; `docs/SHARED-MODE.md` and
  T6.1-T6.4/T6.6/T6.7 outstanding.

**Unpushed / unopened -- RESOLVED 2026-09-08.** The seven commits (`6677fd8`,
`520dba4`, `ad1d50c`, `d0b360f`, `d278cc6`, `7a4fa5c`, `a805e91`) were **pushed
directly to `main`** at the user's direction: `433f3a0..a805e91`, a clean
fast-forward (`origin/main` was a strict ancestor of `HEAD`; no force, no
reset). `origin/main` == local `main` == `a805e91`. lex-lead had recommended a
branch + PR instead; the user was told this bypasses the repo's PR-per-change
convention (PRs #114/#116/#117) and directed the direct push anyway. There is
consequently **no PR for #93**, so live sign-off status lives only in issue #93
and this file -- no PR body carries "live sign-off pending". See
`.crew-handoff.json` -> `push_pr_ruling.OUTCOME`.

## shared-mode-access (#93) -- spurt 4 CLOSED GREEN on a human gate (cycle 7)

**Both P1s are CLOSED** (`7a4fa5c`), along with both cycle-7 P2s. P1-A was the
`validate_only` enrichment's half-mocked seam (now stubs `probe_project_access`
in `_stub_validate_only_env`/`_stub_agreement_env`, with a 4-case
`TestValidateOnlyProjectLockEnrichment`); P1-B was `project_discovery.py`'s
unknown-holder branch declaring "Stale lock detected" + "Close FieldWorks" from
bare lock existence, the exact inversion of `probe_project_access`'s documented
safe fallback (now mirrors `build_access_remedy`'s unknown-holder text). Suite
**1148 passed / 4 skipped** (baseline 1144/4; delta is exactly the 4 new tests);
`validate_integrity.py all` exit 0.

**The `pattern_audit_gate` now PASSES.** The mechanical enumeration
(`reviews/lock-site-inventory.md`, 38 sites: 26 in `src/`, 12 in `tests/`)
reproduced the 26/21/152 grep baseline exactly, rediscovered both known defects
independently, and found **two more** that three consecutive judgement-based
sweeps never named -- including a test that justified its assertion by citing a
dependency in another file that provably does not exist. The method is
vindicated; that table is a living artifact and must be re-run and diffed before
any future lock-related sweep claims completeness. Prose completeness claims stay
inadmissible.

**Deferred, deliberately:** the `check_project_locked` -> `find_lock_file`
rename (P3; contract now documented in the docstring, no issue filed -- do it as
a mechanical commit in the CP6 cleanup pass) and a new P3, that
`sweep_stale_locks()` runs at server startup with no `try/except` around its
per-lock loop. Both are in SPEC.md Section 8.

**Remaining human gates -- ONE. Two of the original three closed 2026-09-08:**
1. **The live FieldWorks session -- STILL OPEN, and now the only gate.**
   `specs/shared-mode-access/evidence/live-session-checklist.md` is a single
   ordered checklist for one sitting: pre-flight backup, CP4-a/b/c, CP3's
   sharing-off recipe check (both parts), and the three OPEN questions
   (writing systems, possibility lists, reversal indexes) that classify SPEC
   Section 3c. The binding item is 3 leg 3 -- a write with FLEx actually open
   appearing in the FLEx UI without a restart. If legs 1-2 pass and leg 3
   fails, STOP before item 5: that is the #96 commit-log staleness shape and
   CP4's "writes are expected to succeed" wording must be re-ruled before CP5
   is built on it. CP5-a is Session 2, after the gate code exists.
2. ~~**Push + PR authorization**~~ -- **CLOSED 2026-09-08**: pushed direct to
   `main` per the user's direction (see above).
3. ~~**Authorization to file two issues**~~ -- **CLOSED 2026-09-08, both
   FILED**: [#118](https://github.com/MattGyverLee/FlexToolsMCP/issues/118)
   (the fail-open probe -- `probe_project_access` reporting `verdict="free"`
   without ever inspecting a lock file; the interim `probed` flag has landed,
   the `verdict="unknown"` enum widening is the real fix; labels `bug`, `P1`)
   and [#119](https://github.com/MattGyverLee/FlexToolsMCP/issues/119) (the
   pre-existing `docs/TOOL-CONTRACT.md` vs `run_module` envelope gap; labels
   `bug`, `documentation`, `P2`). Both issue bodies carry the recorded
   rulings and the verified line references, so the rationale does not need
   relitigating.

**Next crew work needs none of the above:** CP5 T5.2-T5.6, a custom-fields-only
core against the amended SPEC, then CP6 docs plus the two P3 cleanups.

**Environment caveat found this cycle:** the installed `flexicon` resolves to
the *sibling source repo* at `D:\Github\_Projects\_LEX\flexicon\flexicon`
(editable install, `main` at `7e0fdf2`, past the 4.5.2 release), not a
site-packages wheel -- contrary to CLAUDE.md, which says flexicon is PyPI-only
and no longer a cloned sibling. Any "verified against flexicon 4.5.2" claim made
on this machine is really "verified against main@7e0fdf2". State the resolved
path explicitly in future live evidence.


## shared-mode-access (#93) -- spurt 5 CLOSED GREEN (cycle 8, 2026-09-08)

**The feature's last red gate went green.** CP2, CP3 and CP4 are all SIGNED OFF,
and CP4 was confirmed *live* against a real FieldWorks master (PID 40664,
sharing ON): `validate_only` returned `verdict=open_shared`, `blocking=false`,
11/11 gates, and the load-bearing human observation -- a peer write visible in
the FLEx UI after F5 with no FLEx restart -- PASSED. The live FieldWorks session
that has blocked this feature since spurt 3 is retired.

**Two fixes landed, one of them a genuine safety hole.**

- `a8cf35b` -- finding (k). `_pid_is_alive` now calls `GetExitCodeProcess`, so a
  freshly-dead PID whose kernel handle is still retained (the crash-reporter
  shape) no longer reports ALIVE. Confirmed by an independent throwaway-process
  reproduction: old code `True/True/True` at t=0/5/30 s on a dead PID, new code
  `False/False/False`. An earlier claim that (k) was reproduced live was
  **withdrawn** -- a *graceful* FLEx close deletes the `.fwdata.lock`, so the
  verdict correctly collapses to `free`; (k) needs a crashed or hard-killed
  holder.
- `ee53b11` -- **the Rung-3 write gate was BYPASSED on a live schema mutation.**
  A guarded `project.CustomFields.CreateField(...)` ran with
  `write_enabled=True, confirmed=False` and no lock, because
  `is_mutating_script` came back `false` for a method the API index marks
  `is_mutating: true`: the `project.<Accessor>.<Method>` facade idiom never
  reached the index lookup at all. Only flexicon's internal transaction guard
  stopped the write. Fixed with index-based `access_path` resolution plus a
  shared `compute_is_mutating_script()` behind *both* the confirmation preview
  and the real `needs_lock` gate. **This contradicts the earlier finding-(d)
  scope bound that this was "not a safety hole" -- that bound held for
  `SetGloss` and did not generalise. Do not re-adopt it.** Suite
  **1159 passed / 4 skipped** (baseline 1148/4, all +11 mapped to named tests);
  `validate_integrity.py` clean.

**CP5 is OPEN by the user's decision, and that is deliberate.** Rather than
implement a gate, the user adopted an interim conservative policy, now recorded
as a CP5 status block in `SPEC.md` (`502ab92`): **both writing-system and
custom-field operations are assumed to require exclusive access** -- as
documentation and review policy only, with nothing enforcing it in code. This
settles the scope question T5.1 left open: writing systems and custom fields are
both in CP5's scope from the start, not a custom-fields-only core with a
fast-follow row.

**CP5-a is WITHDRAWN, not blocked.** `CustomFieldOperations.CreateField` refuses
*unconditionally* with `FP_TransactionError` in Phase 1 transaction mode --
independent of FLEx state and of shared mode -- because `OpenProject()` holds a
non-undoable UnitOfWork open until `CloseProject()`. CP5-a's second leg ("close
FLEx, re-submit, succeeds") therefore cannot pass, and its first leg would pass
for entirely the wrong reason. **Class B (`silently_lost`, custom fields)
remains UNOBSERVED**; SPEC Section 3b rests on the liblcm-source derivation, not
on live evidence. Do not re-queue CP5-a as written.

**Section 3 was reclassified, and lex-lead ratified a deviation.** The table is
now 3a `refused` / 3a-ii `safe` / 3b `silently_lost` / 3c `crashes_holder` /
3d retired. The writing-system row went to a **new Class C**, not Class A as the
cycle-8 brief proposed: Class A is defined by its *mechanism* (LCM raises before
anything is written) and carries the entitlement "safe by construction, needs no
alarm". The WS write reached disk on both legs with nothing refusing it and then
crashed the live FLEx holder (`NullReferenceException`,
`WritingSystemListHandler.AddWritingSystemList`, `TextListeners.cs:286`). Filing
it under Class A would have attached "needs no alarm" to the one row that must
be REFUSED. **Classify by mechanism, never by outcome-similarity.**

**One new bug, unfixed, now OWNED.** The `flextools_health` `warnings` array is
computed once at server startup and frozen for the life of the process, so a
single response can contradict its own body -- it asserted a live FieldWorks
holder ("53 s old ... process still running") in a payload whose own
`verbose.project_access` read `verdict: "free"`, `holder: null`, with no lock
file on disk. Three sites: `server.py:1048-1050`, `diagnostic_health.py:245`,
and `validators.py:221` (so CP2/CP3 share the stale cache). Recorded as a P1 in
`SPEC.md` Section 8 and **assigned to the next spurt's programmer as the first
item of the CP6 cleanup pass**, ahead of the two P3s.

**`#93` was auto-closed TWICE in one day.** Both `7a4fa5c` ("closes #93 P1s")
and `ee53b11` ("closes #93 findings (a)/(d)") lead with a closing keyword;
GitHub ignores the qualifying words and closes the whole feature issue. The user
reopened it at 15:56Z, the `ee53b11` push re-closed it at 16:13Z, and lex-lead
reopened it again at cycle-8 close with an explanatory comment. **Standing rule:
reference it as a bare `(#93)` only -- no `closes`/`fixes`/`resolves` until CP5
and CP6 are both done.**

**Correction to a cycle-8 report:** the claim that main was "14 commits ahead of
origin/main, NOTHING PUSHED" is **false**. Verified at close:
`origin/main == local main == 502ab92`, 0 ahead / 0 behind. Everything is pushed.

**Issue filing: 13 drafted, roughly 5-6 genuinely new.** Nothing is filed;
drafts live in `specs/shared-mode-access/issues/DRAFT-issues.md`. Dedup found
the FlexToolsMCP `mutations_detected` draft is a near-duplicate of open
[#105](https://github.com/MattGyverLee/FlexToolsMCP/issues/105); flexicon
finding 2 recurs explicitly-declined scope in closed #183; findings 1, 7 and 9
overlap closed #100 / closed #179 / the open #262-#269-#270 cluster. Genuinely
new: flexicon 3, 4, 5, 6, 8 and FlexToolsMCP 1, 3, 4. Three further library
findings from this sitting are not yet drafted at all (see the handoff json's
`dedup_results_cycle8.three_more_not_in_the_13`) -- notably that
`ReversalIndexOperations` has **no method to create a reversal entry**, which
means Session 2 test 3 cannot be executed through flexicon.

**Ruling on #105: `ee53b11` does NOT close it.** Verified empirically at close
by running #105's own repros through `build_writeability_payload` /
`certify_script_readonly`: both of its `writeability` repros now report
`is_mutating_script: true` with a populated `mutations_detected`. But its third
evidence block is untouched -- `write_certification.mutating_calls_detected`
(`handlers/execution.py:4502`) filters `cert["mutating_calls"]` only and never
reads the new `cert["protected_calls"]`, so a guarded mutation still reports
`[]` alongside `is_certified_readonly: true` on a real run. Comment on #105 and
narrow it; keep it open. The comment is drafted but **not posted** -- outbound
issue writes need the user.

### Next pickup (spurt 6) -- CP6

1. **Item G, the stale-warnings P1** (SPEC Section 8, owner assigned). Recompute
   the sweep inside `_build_warnings()`, or give `startup_lock_warnings` a
   timestamp and short TTL; `validators.py:221` must pick up the same freshening.
2. The two P3 cleanups: `check_project_locked` -> `find_lock_file` (16
   occurrences, zero behaviour change) and the unguarded `sweep_stale_locks()`
   loop at `server.py:1048`.
3. `docs/SHARED-MODE.md` (T6.1-T6.4, T6.6, T6.7) -- it does not exist yet.

**Two items need the user, and they are the only reason this is not
`feature_complete`:**

- **Authorize the issue-filing batch** (~5-6 issues, not 13) plus the #105
  comment. Draft the three incidental library findings into the batch *first* so
  the user approves one complete list rather than two.
- **Restart the MCP server.** The crew cannot -- the sandbox classifier denies
  `Stop-Process` -- and the running server (PID 15852, started 10:39:09)
  predates both cycle-8 fixes, so no post-fix live verification is possible
  until the user restarts it.

**Machine state at close:** FieldWorks CLOSED. `Sena 3` project sharing ON
(as-found; the *user* set it -- leave it). No lock file on disk. `Sena 3`
UNMUTATED this cycle -- the user declined the wider live mutating group, so no
restore is needed.

---

## Write-gate bypass batch (branch `flexicon-project-bridge-mcp`) -- spurt closed on a human gate (cycles 1-2, 2026-09-10)

**Not a `flexicon-project-bridge` task.** That feature's own tasks T001-T025 are
all checked off in `specs/flexicon-project-bridge/tasks.md`; this batch is the
two write-gate **defects** cycle-1 QC and verification surfaced while reviewing
it. It is tracked only in `specs/flexicon-project-bridge/reviews/`, and it is
**UNCOMMITTED**: `src/flextoolsmcp/server/validators.py` (+183/-38) plus new
`tests/test_cycle2_step2b_finding_a_b.py`, on top of `def958a`.

**Both findings are implemented as ratified.**

- **Finding A -- Step 2b line-keyed self-suppression (`certify_script_readonly`,
  now :3841-3908).** The `_resolved_pairs` line-key set is *structurally gone*;
  each `ast.Call` is now decided on its own via `_resolve_receiver_ops_class`,
  so a call is skipped only because IT was authoritatively classified, never
  because of what shares its line. The old bug: any same-name/same-line regex
  hit -- including a **comment or string decoy** -- silently suppressed a real
  unresolved-receiver mutation. Cycle-1 QC chose Option 1 ("invert the
  question") over node-identity and composite-key; the addendum's **tightened**
  fallback (`_recv.id in _known_ops_classes`, backed by the new
  `_indexed_operations_class_names` at :2838) was adopted, so the three
  pre-existing naming-convention holes (`myOperations`, `ZzzOperations`, a
  `fooOperations` parameter) close too rather than being preserved.
- **Finding B -- binding-form blindness.** New `_BindingNode` union (:1204) and
  a **third** return list `bindings` from `_collect_assign_call_nodes` (:2654).
  The structural constraint held: `assigns` stays `List[ast.Assign]`, so Step 4b's
  `_find_cast_alias_property_writes(ast_assigns, ...)` (:3943) still receives
  bare `ast.Assign` only -- verified, it is the lone call site. All four
  facade/alias call sites now pass `assigns + bindings` (:1002, :3281, :3699,
  :4830). This closes the 2x2 cell where `annotated`/`walrus`/`with-as` bindings
  **without a usable index** were certified read-only at *high* confidence.

**Evidence, produced independently of the programmer** (orchestrator harnesses in
the session scratchpad: `verify_real_code.py`, `verify_no_overblock.py`,
`head_baseline.py`), run against the PATCHED module and the shipped
`flexicon_api_v4.7.0.json`, not a prototype:

- Suite **1336 passed / 8 skipped / 36 subtests** (baseline 1312 + 24 new), re-run
  independently and matching the programmer's numbers exactly.
- **All 12 attack vectors BLOCKED end-to-end through `certify_script_readonly`**
  (`certified=False`, `confidence=low`, `unknown_calls>=1`): same-line `;`,
  reversed order, comprehension, ternary, one-line `for`, trailing-comment decoy,
  string-literal decoy, bogus-ops comment decoy, plus J/K/L. The two-unresolved-
  calls-on-one-line case now yields **two** rows -- direct proof the self-
  suppression is gone.
- All five Finding-B binding forms blocked, including the index-less cell.
- **No over-block:** four legitimate resolvable shapes classify authoritatively
  (`unknown_calls=0`, `confidence=high`); ten read-only scripts across
  index/no-index (plain, facade, annotated, walrus, with-as) still certify True;
  a *guarded* case-K variant yields `unprotected=0`, so the tightening stays
  protection-checked.
- Fresh IDE diagnostics on `validators.py`: **empty**. The four
  `_parents is possibly unbound` pyright warnings near :5405/:5468 are
  **pre-existing** (9 occurrences in both HEAD and the working tree, untouched).

**Verification gate: PASS, and lex-verification is NOT applicable to this change
class.** These are pure static-analysis edits -- no live FLEx database, no LCM
write, nothing to `-restore`. The right evidence standard is suite parity +
end-to-end probes through the public entrypoint + no-over-block controls + a
pristine-worktree baseline, and all four exist above, produced by a party other
than the author. Re-dispatching lex-verification here would burn a cycle to
re-run the same suite.

**Contract question closed so QC need not re-litigate it:** the added
`"col": col_offset` key is contract-safe. `docs/TOOL-CONTRACT.md:102` lists
`mutating_calls` as an opaque `(list)`, and `UnprotectedWritesDetail`
(`src/flextoolsmcp/server/response_models.py:178`) types it
`Optional[List[Any]]` -- the `extra="forbid"` on that model constrains detail
*fields*, not row keys. The programmer's ~40-hit consumer audit found no exact-
key-set or full-dict assertion.

**One residual FALSE POSITIVE, confirmed PRE-EXISTING, not a regression.** A
script whose only mention of a mutating call sits in a **comment or docstring**
returns `is_certified_readonly=False` with `mutating_calls=1` when an index is
loaded (with `api_index=None` it correctly certifies True). Reproduced
identically in a pristine worktree at `def958a`. This is the out-of-scope
stripping defect Explore documented
(`reviews/cycle1-explore-strip-scope.md`) and the archivist has now drafted
(`reviews/cycle2-archivist-strip-issue.md`) -- so the follow-up is empirically
real, not theoretical. Its meta-finding matters: **do not "just call
`_strip_comments` more"** -- that helper eats real code on `t = "a#b"` and can
make `ast.parse` raise, which `certify_script_readonly` swallows at :3550
(`tree = None`), silently disabling Steps 1b/2b/4b. Converge on AST-ification or
a `tokenize`-based stripper.

### Next pickup -- the pre-commit QC gate

1. **lex-qc on the diff itself** (the only gate still genuinely open): the new
   `_BindingNode` union and the third return value threaded through four call
   sites; the documented `For` over-typing (issue #8) and its claimed disjointness
   from `detect_casting_needs`' `loop_element_types`; and the quality/coverage of
   the 24 new tests in `tests/test_cycle2_step2b_finding_a_b.py`. Skip
   verification and domain -- see above.
2. Optionally lex-simplify on the same diff: a Union alias + a 3rd tuple element
   is added structural surface, and `_collect_assign_call_nodes` now has three
   consumers with two different expectations.

**Two items need the user, and they are the only reason this batch is not
closed:**

- **Authorize the disposition of the uncommitted diff.** The user has NOT
  sanctioned a commit for this batch and asked to see it first. The Ralph
  standing prompt would otherwise auto-commit it -- hence this spurt stops on
  `needs_human` rather than `in_progress`.
- **Authorize filing the drafted stripping issue.** The draft is ready in
  `reviews/cycle2-archivist-strip-issue.md`; dedup found no match (nearest, #126
  and #131, are both open false-*negative* write-gate bugs, opposite direction).
  Only the user opens issues.

**Machine state at close:** no FLEx involvement at any point in this batch --
static analysis only. Nothing to restore.

## liblcm-core-coverage (#135 / #136) -- FEATURE COMPLETE (cycles 1-2, 2026-09-10)

Both issues landed and pushed to `origin main`:
`d50689f` (#135, ReflectionTypeLoadException type recovery) and
`98c0fa4` (#136, parameterized-accessor recovery). All gates green.

**147 members recovered across 26 types** -- an exact match to lex-qc's cycle-1
prediction, which is the strongest signal here: the fix landed the size the
analysis said it would, so nothing extra crept in. Verification confirmed the
change is **purely additive** (147 methods added, 0 removed); the raw `git diff`'s
1086 minus-lines are pure JSON key-order churn inside untouched entities, not
losses. Zero `get_Item`/`set_Item` duplicates across all 12 named entities.
ITsString gained exactly the 8 expected members. Field discipline is clean across
all 147 entries (not just the 8): zero `is_property`, and `index_param_type`
present iff `indexed==true`.

Signatures were checked against **live .NET reflection on the installed
FieldWorks 9 DLL**, not against source -- ground truth. That caught that the
cycle-2 prompt's `get_Properties(int ich)` was a typo in my own briefing: the real
parameter is `irun` (`ich` belongs to `get_PropertiesAt`/`get_RunAt`). The index
and the DLL agree; only the prompt was wrong. Server serves `get_Properties` in
the default summary view. Suite: **1394 passed / 8 skipped / 0 failed**.

Crew reports are committed under `specs/liblcm-core-coverage/reviews/`
(5 files, cycles 1-2), per the tracked-reviews convention.

### Two spinoffs, both deliberately left OUT of this feature (need the user)

> **Spinoff A: RESOLVED in release 2.12.0 (2026-09-10).** The user chose
> **delete v4.7.0** and made 4.8.0 the new `pyflexicon` floor, which settles the
> policy question below: with the floor at `>=4.8.0` no supported install can
> resolve 4.7.0, so keeping its index files serves no audience. The stale pip
> metadata was also fixed (`pip install -e . --no-deps` re-run on the flexicon
> checkout; `pip show pyflexicon` now reports 4.8.0). See the 2.12.0 CHANGELOG
> entry for the reviewed index diff.

**A. flexicon index 4.7.0 -> 4.8.0 supersede.** My cycle-2 briefing told the
programmer to restore the deleted `*_flexicon-v4.7.0.json` files because
`pip show pyflexicon` said 4.7.0. That instruction was wrong and the cycle-2
`refresh` correctly re-deleted them. Root cause: `flexicon.__file__` resolves to
`D:\Github\_Projects\_LEX\flexicon\flexicon` -- an **editable install of the
sibling repo**, whose tree is tagged `v4.8.0` ("chore(release): cut 4.8.0").
pip's recorded metadata is simply stale because the editable install was never
re-run after the bump. So **v4.8.0 is the real released version and the v4.8.0
index files are the correct ones.**

Not committed, on purpose: this is an unrelated index version bump and must not
ride along inside a liblcm bugfix spurt. It also carries a genuine policy choice
that is the user's, not the crew's -- v4.7.0 has never been superseded before, so
there is no precedent to follow: **delete v4.7.0** (clean, but a PyPI user still
on 4.7.0 eats a first-run lazy refresh) vs. **keep both** (additive, larger repo,
serves both audiences). Recommend also re-running `pip install -e` on the
flexicon checkout so the metadata stops lying to future tooling -- that stale
metadata is what misled this spurt in the first place.

**B. Pyright hygiene (optional, non-blocking).** `#136` added two new instances
(`liblcm_extractor.py:790,809`, "Public/Instance/DeclaredOnly is not a known
attribute of None") of a pythonnet-unavailable idiom that already exists
pre-change at `:332`, `:402`, `:922`. Consistent with the file, not a regression;
a real fix is one typed helper/assert across all five sites. Plus three trivial
unused-variable warnings in `tests/test_issue136_indexed_accessor_recovery.py`
(`_pythonnet_available` L105, `non_public` L97/L100). Nothing fails. Worth one
small issue only if the user wants pyright clean.

**Also still dirty, and NOT ours:** `reports/upstream-flexicon-docstring-findings.*`
(217 -> 139 findings) is uncommitted fallout from the earlier `5330f25` scanner
change, left over from the previous campaign. Untouched by this spurt.

**Machine state at close:** no FLEx writes at any point -- static analysis and
read-only reflection only. Nothing to restore.
