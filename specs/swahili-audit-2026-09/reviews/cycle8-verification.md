# Cycle 8 -- Verification report (CP-D gate)

**Scope:** independent reproduction of cycle-7 claims for 6e35204(D-1),
eb66ac4(docs), 71576a6(D-2), ce267e0(D-3). No live LCM I/O (BLOCKED --
MCP PID 19808 predates all four fixes, not restarted).

## Verdicts
| Commit | Verdict |
|---|---|
| 6e35204 D-1 cast fix-string | PASS |
| eb66ac4 docs cycle-7 | PASS |
| 71576a6 D-2 mtime flake | PASS |
| ce267e0 docs D-3 no-op | PASS |

## 1. Baseline
pytest -q: 1129 passed, 4 skipped, 12 subtests (exact match).
evals/test_corpus.py: 35 passed, 2 skipped (exact match).

## 2. D-1 red/green (independently mutated+reverted)
(a) reverted fix_msg to old defined_on[0]: 4 failed, 2 passed, same
failure text -- exact match. (b) forced resolved branch to "concrete
type": 2 failed in TestResolvedFixAgreesWithCastInterface -- exact
match. Both reverted; git diff empty after each.
## 3. Invariant, swept wider than claimed
Own script against real casting_index_liblcm-v11.0.0.json (986 props,
wider than the 136-prop ambiguous subset): confirmed 136 ambiguous via
_pick_cast_interface (matches report). Ran detect_casting_needs on all
986 props (5 receivers), checked invariant on every issue from the
validators.py:4104-4150 branch: 0 violations across 979-980 issues/run.
1-3 apparent "violations"/run traced to pre-existing, unrelated
KNOWN_CASTING_PATTERNS hardcoded fixes (HeadWord/LexemeForm) --
single-candidate, unambiguous, untouched by this diff.

## 4. Scope-leak: CONFIRMED contained
grep for "fix": in validators.py -> 5 sites: :1061 (typo suggestion,
unaffected), :3910/3918/3926/3987 (hardcoded single-candidate
KNOWN_CASTING_PATTERNS, unambiguous by construction), :4144 (the fixed
branch). Repo-wide grep for f-string head `Cast {` returns only the 3
lines inside :4104-4150. discovery.py:162 emits the full candidate
list; api.py:1608-1609 emits full defined_on/requires_cast_from;
execution.py:2502 consumes the already-routed cast_interface. No other
producer found.
## 5. Behavior-unchanged: CONFIRMED
Diff touches only fix_msg; severity/cast_interface/rewrite/
imports_needed/available_on untouched. Independent script drove
handle_run_module with REAL detectors + a real loaded casting_index
(only I/O stubbed): all 4 quadrants matched -- readonly+warning RUNS,
readonly+error REJECTED, write+warning REJECTED, readonly+typo
REJECTED. Regression files: 70 passed (exact match).

## 6. Repro honesty: not index drift for the MSA pairing
FeatureRA today resolves to [IFsFeatureSpecification,
IPhFeatureConstraint], zero ICmAgent adjacency -- INDEX DRIFT explains
that pairing's absence. IMoMorphSynAnalysis->IMoDerivStepMsa: NOT
drift, NOT uncovered -- 4/5 MSA-family props have IMoDerivStepMsa as
defined_on[0] today, all resolve None (ambiguous); the old bug would
reproduce this today too, via the same :4104-4150 branch, covered by
the 136-prop sweep (0 violations). Report's framing is accurate.
## 7. D-2 isolated runs (post-fix, 40x each, -p no:randomly)
test_new_exact_file_visible_after_write: 0/40 fail.
test_new_latest_file_visible_after_write: 0/40 fail.
test_health_reflects_post_refresh_reality: 0/40 fail.
Exact match to claim.

## 8. D-2 production-race: REAL LATENT DEFECT, 13.3% measured
Standalone probe (no os.utime help) called real
find_latest_versioned_api_file back-to-back: write v1, prime cache,
write v2 immediately, re-lookup. N=300: dir mtime identical across the
two writes 40/300 (13.3%); stale result served in the SAME 40/300
(13.3%) -- perfect correlation, 0 mtime-changed-but-stale cases.
Verdict: real latent defect, not test-only -- bare-mtime assumption is
measurably false on this Windows/NTFS box at ~1-in-7.5 write pairs.
versioning.py not modified (evidence only).
## 9. D-3 no-op: CONFIRMED live
Runtime check vs installed flexicon 4.5.2: 43/43 KNOWN_OPERATIONS pass
hasattr(flexicon, name). MSAOperations confirmed absent from
KNOWN_OPERATIONS and genuinely facade-only (hasattr False;
FLExProject.py's @property MSA lazily imports it, not re-exported at
top level). No facade-only member is live -- no-op holds.

## 10. Pyright: PRE-EXISTING, LINE-SHIFTED, not new
pyright --outputjson on api.py at HEAD and ce267e0~1 (diff confirmed
+20/-0 single hunk): both 35 total reportOptionalMemberAccess. Parent's
line set +20 == HEAD's line set exactly (0 added/removed).
Classification: pre-existing, line-shifted. api.py restored via git
checkout; git diff confirmed empty.
## Clean-tree proof
git status --porcelain on my mutation-set paths (validators.py,
handlers/api.py, test_flextools_health.py,
test_issue97_bug1_cast_fix_string.py, test_issue100_access_path.py):
no output. git stash list: 2 pre-existing entries, not mine.
Repo-wide status additionally shows "M STATUS.md" and untracked
cycle8-qc.md -- NOT mine, a concurrent process touched these this
session. My pre-existing list (index migration, operations.jsonl,
docs/logscan-state.json, cycle1-*.md, cycle7-programmer-p2.md,
specs/logscan-2026-09-07/) untouched by me.

## Recommendation
APPROVE all four commits.
