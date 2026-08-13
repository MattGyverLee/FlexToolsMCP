# Project Status

Active feature: **diagnostic-report** ("send this to the maintainer" flow).
Spec: `specs/diagnostic-report/SPEC.md` (APPROVED-WITH-EDITS).
Checkpoint plan: `specs/diagnostic-report/tasks.md`.

## Where we are

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

## Next pickup -- CP4 (docs + demo)

CP3 is closed; the feature is **not** complete. Next spurt starts **CP4 -- docs +
demo** (see `tasks.md` CP4 line-items, currently "not started"). Fold the CP2+CP3
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
`#CP3-TBD`, NOT started.** Draft body in
`specs/inheritance-resolution/PROPOSED-ISSUE-cp3.md` was corrected in cycle
6 (wrong script attribution, crew-internal cycle numbers replaced with
commit hashes, and a clarifying paragraph on why #86's mechanism cannot
cover this case) and then filed with explicit user authorization.

**Feature status: CLOSED (cycle 6).** All checkpoints (CP1-CP4) are landed,
committed, and verified; #86 and #85/#88 are closed; CP3 is filed and
tracked as its own issue for future work. The repo's active feature reverts
to diagnostic-report (line 3).
