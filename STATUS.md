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
Three items there need a USER DECISION before the crew can act (see BLOCKERS
below): the versioning stale-read race, the `cast_to_concrete` phantom remedy,
and the still-unrestarted MCP server. The #96 live repro remains available only
after the user restarts the MCP server.

### NEW BLOCKERS from spurt 3 -- both need the user, neither is code

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
5. **A phantom remedy advertised in five places.**
   `CastingOperations.cast_to_concrete` is advertised to users in FIVE locations
   (including `handlers/discovery.py:163`) but was proven **NONEXISTENT** in
   flexicon 4.5.2. This is the #103 / import-advertising failure class again: the
   tool tells users to call something that isn't there. Found because the cycle-9
   brief required verifying a remedy before advertising it -- the programmer
   checked before adding a sixth advertisement and the check failed. PRE-EXISTING,
   not introduced by CP-D. **Needs: authorization to file as a new issue.**

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

**Deferred, no issue filed** (SPEC.md Section 8): pre-existing P2 --
`docs/TOOL-CONTRACT.md:13-26` claims all success responses carry
`_contract`/`status`/`op_id`, but `run_module`'s raw success dict never does.
Predates CP1. Issue filing needs the user's authorization.

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

### MERGE READINESS (asked by the user, answered 2026-09-06): NOT READY

The branch is 10 commits ahead of `origin/main` and unpushed. Four things block a
merge; only the last two came from the bugfix campaign:

1. **The CP1 live write check for #92 has still never been run** -- see the blocker
   immediately below, which says in its own words "Do not merge
   `feat/shared-mode-access` to `main` until this passes." This is the binding one.
2. **This section is stale** (see the correction above) -- reconcile before
   reasoning about what merging would ship.
3. **The flexicon 4.4.1 -> 4.5.2 index migration is uncommitted and undecided**:
   3 deleted v4.4.1 files, 3 untracked v4.5.2 replacements, plus modified
   `liblcm_api_v11.0.0.json` and `reverse_mapping_liblcm-v11.0.0.json`. Commit it
   deliberately or revert it; never sweep it into a code commit. Because this repo
   supports multiple index versions side by side (`docs/VERSIONING.md`), deleting
   the v4.4.1 files is a real decision -- anyone still on flexicon 4.4.1 loses
   their index. `docs/logscan-state.json` is also modified and belongs to logscan,
   not to either feature here.
4. **Two prior-session spec artifacts await a keep-or-drop call**:
   `specs/swahili-audit-2026-09/reviews/cycle1-domain.md` and
   `cycle1-explore-nullmorph.md`, left untracked on purpose so the user decides.

Safe on merge: `cb3f1b8` is the ONLY commit in `origin/main..HEAD` carrying an
auto-close keyword (`closes #103`), and #103 genuinely is fixed. Nothing
auto-closes #96, #40, #97, #100 or #101 -- all six remain open by design.

### BLOCKER -- needs the user: the CP1 live write check

**Do not merge `feat/shared-mode-access` to `main` until this passes.** CP1 is
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

1. User runs the CP1 live write check above and reports the result.
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
