# QC Report — Diagnostic-report CP1 (Foundation)

**Date:** 2026-07-13
**Quality Score:** 89/100
**Status:** ISSUES (one P1 fix recommended before CP2 wires `offered_store` into a live handler path; not blocking CP1 acceptance itself)

## Pattern-Audit Gate
- Applicability: **N/A** — this is new-feature work (spec-driven checkpoint plan, no `bug`-labelled issue, no `closes #N`/`fixes #N` reference). Not a bugfix.
- Sweep present in PR body: N/A (one-off/feature, justified above)
- Spot-check on a listed [HIGH] sibling: N/A
- Gate status: **PASS** (exempt)

## Code Quality: 23/25
- Readability: high — docstrings consistently explain spec-section provenance, rationale, and CP2/CP3 seams (`triggers.py`, `signature.py`, `offered_store.py` all follow this pattern).
- Maintainability: good — pure-function design in `triggers.py`/`signature.py` (verified: only `typing`, `hashlib`, `re` imported — stdlib-only, confirmed against source) keeps CP1 cleanly separable from CP2 reconstruction work.
- Consistency: matches existing `server/` idioms (uppercase module constants, `Dict[str, Any]` record shape, fail-open patterns mirroring `op_telemetry`).

**Issues:**
- P2 — `src/flextoolsmcp/server/diagnostic/offered_store.py:57-60`: docstring on `default_store_path()` claims `path_fn` "mirrors `op_telemetry`'s `log_dir_fn` convention," but `op_telemetry._write_jsonl_line`'s `log_dir_fn: Any` (`src/flextoolsmcp/server/handlers/op_telemetry.py:134`) is a **required** kwarg with no default and weak typing, while `offered_store`'s `path_fn: Callable[[], Path] = default_store_path` has a default and a precise type. Functionally fine (arguably better), but the "mirrors" claim overstates the parity — cosmetic doc-precision nit only.

## Standards Compliance: 24/25
- Style guide: Pass — consistent with project's `#!/usr/bin/env python3` / `# -*- coding: utf-8 -*-` header convention, docstring density matches `session.py`/`execution.py`.
- Naming: Pass — `STATE_OFFERED`/`STATE_DECLINED`/`STATE_DONT_ASK_AGAIN`, `NON_REPORTABLE_CODES`, `_CASTING_CODE`/`_INVALID_CHAIN_CODE` all clear and consistently cased.
- Organization: Pass — dedicated `diagnostic/` subpackage with `__all__: list = []` and a rationale docstring explaining the future AST no-transmission-scan boundary (`src/flextoolsmcp/server/diagnostic/__init__.py:8-24`). No dead code found; every public function in the three new modules is exercised by `tests/test_diagnostic_report_foundation.py`.

**Issues:** none blocking.

## Error Handling: 20/25
- Exceptions appropriate: mostly Pass. `record_decision` correctly raises `ValueError` on an invalid `decision` string (`offered_store.py:214-215`) — appropriate, since that's a programmer-misuse guard, not an I/O fail-open path.
- Edge cases handled: Pass for `load_store` (`offered_store.py:71-97`) — wraps `path_fn()` call in a broad `except Exception`, and JSON/shape problems in a narrower but sufficient `except (OSError, ValueError, UnicodeDecodeError)`. Confirmed by test (`test_corrupt_offered_json_fails_open`, `test_missing_offered_json_is_treated_as_empty`).
- Error messages clear: Pass.

**Issues:**
- **P1 — `src/flextoolsmcp/server/diagnostic/offered_store.py:100-114` (`save_store`)**: the fail-open guarantee is narrower than `load_store`'s. `save_store` wraps its body in `try: ... except OSError: pass` — but `path_fn()` is called *inside* that same try, same as `load_store`, EXCEPT `load_store` guards `path_fn()` with a separate broad `except Exception` (lines 76-79) while `save_store` does not (lines 108-114 catch only `OSError` for the whole block, including the `path_fn()` call). Concretely: if `path_fn` is the default `default_store_path` -> `get_reports_dir` -> `Path.home()`, and `Path.home()` raises `RuntimeError` (documented CPython behavior when the home directory can't be resolved, e.g. some locked-down service accounts), `save_store` — and therefore `record_offer`/`record_decision`, which call it unconditionally — would raise all the way up. This directly contradicts the module header's explicit contract ("A corrupt/unparseable file is treated as EMPTY ... NEVER crash the op path") and the QC brief's specific ask that offered_store's fail-open paths "must never raise." Currently dormant (CP1 doesn't wire `offered_store` into any live handler yet, per the programmer's own report), but must be closed before CP2/CP3 calls `record_offer`/`record_decision` from `handle_run_module`. **Fix:** widen `save_store`'s except clause to `except Exception` (or explicitly separate the `path_fn()` call into its own guarded step, matching `load_store`'s structure).

## Best Practices: 22/25
- Design patterns: good — dispatcher pattern in `signature.compute_signature()` (`signature.py:84-119`), LRU-prune-by-`last_seen` in `offered_store.prune()` (`offered_store.py:117-129`, correctly sorts ascending and pops the oldest `overflow` entries — verified against `test_prune_caps_entries_by_lru_last_seen`, which checks the three highest-index/most-recent entries survive).
- No anti-patterns: Pass — no god functions, no magic numbers without named constants (`_DIGEST_LEN`, `DEFAULT_ENTRY_CAP`, `STORE_VERSION` all named).
- Performance: Pass — O(n log n) sort in `prune`, O(n) grouping in `group_records_by_intent`; no obvious inefficiency for expected data volumes (hundreds of entries per the module's own comment).

**Issues:**
- P1 (heuristic, per review brief's explicit ask) — `src/flextoolsmcp/server/diagnostic/triggers.py:62-77` (`casting_recurrence_signature`): the documented v1 fallback — "if `casting_signature` and `preflight_gate` are both blank, ANY two `casting_issues_detected` closes in the same turn count as a recurrence" — is an acceptable CP1 simplification (correctly self-documented as a known simplification, and it only ever widens the offer surface, never suppresses a genuine report, so it's safe-by-construction rather than silently wrong). However it is a real precision gap: two *unrelated* casting issues in the same turn would currently be treated as a recurrence of "the same" bug. Recommend tracking explicitly as a P1 backlog item for CP2 (when `casting_signature` gets threaded into the JSONL schema) rather than letting it ride as an implicit assumption — the programmer's report already flags this as a "natural CP2/CP3 follow-up," which I'd formalize as a checkpoint-plan line item so it doesn't silently become permanent.
- P2 — verification of `op_telemetry.group_records_by_intent()`'s "behavior unchanged" claim (`src/flextoolsmcp/server/handlers/op_telemetry.py:213-250`) was done via the programmer's reported full-suite regression (486 passed) plus a new direct test (`test_group_records_by_intent_reused_for_turn_scoping`) rather than an independent pre/post diff — no git-diff tooling available in this review session to independently confirm the extraction was byte-for-byte behavior-preserving beyond what the test suite already covers. The extracted function's logic (three-way branch: no-intent standalone group, intent-change breaks group, intent-continuation appends) is internally consistent and matches the docstring's stated turn-boundary semantics, so no specific reason to doubt it, but flagging the verification-method gap for completeness.

## Purity claims — confirmed
`triggers.py` imports only `typing`; `signature.py` imports `hashlib`, `re`, `typing`. Both stdlib-only, no I/O, no network, matching the package docstring's no-transmission-guard rationale (`diagnostic/__init__.py:8-14`).

## Path-injection convention — confirmed with one nit
`offered_store.path_fn` and `op_telemetry.log_dir_fn` both follow the "inject a zero-arg callable returning a `Path`" idiom used throughout the codebase for testability. Functionally equivalent; see P2 doc-precision nit above re: default-value ergonomics differing.

## user_request plumbing — confirmed correct
Traced end-to-end: `models.py` (`FlexToolsStartInput.user_request`, `RunModuleInput.user_request`, both `max_length=4000`) -> `tool_definitions.py` (documented on both tool descriptions) -> `handlers/admin.py:307,379` (`handle_start` reads arg, passes to `configure()`, always resets — never inherited, matching `session.py:253-256`) -> `handlers/execution.py:1839` (`handle_run_module` falls back to `session_state.get_user_request()`) -> `_log_operation_start` (`execution.py:396-421`, computes effective value with `user_intent` fallback, logs it, stashes it) -> `op_telemetry._stash_op_start`/`_write_jsonl_line` (`op_telemetry.py:91,157`, defensive re-application of the same fallback). E7 preserved: `group_records_by_intent`'s grouping key stays `user_intent` alone (`op_telemetry.py:231`), `user_request` never affects turn boundaries. All claims in the programmer's report check out against the actual diffs.

## Test Quality
`tests/test_diagnostic_report_foundation.py` — real assertions throughout, not smoke tests: exact-membership dedupe checks (`test_dedupe_two_edited_attempts_yield_exactly_one_offered_entry`), LRU-survivor-set assertions (`test_prune_caps_entries_by_lru_last_seen`), restart-simulation via fresh `load_store()` call rather than in-memory state reuse (`test_dont_ask_again_persists_across_simulated_restart`), and full trigger-matrix parametrization over all 13 `NON_REPORTABLE_CODES` under two outcome pairings. No gaps found for CP1's stated scope.

## Final Assessment
**Overall Score:** 89/100
**Recommendation:** APPROVE for CP1 as scoped, WITH one P1 fix required before CP2 wires `offered_store.record_offer`/`record_decision` into a live handler call path: widen `save_store`'s exception handling to match `load_store`'s broad-except-around-`path_fn()` pattern (`offered_store.py:100-114`). The casting-recurrence v1 heuristic (also P1) is acceptable to ship as-is for CP1 but should become an explicit CP2 checkpoint-plan line item rather than an implicit follow-up.

**Reviewed By:** QC Agent
