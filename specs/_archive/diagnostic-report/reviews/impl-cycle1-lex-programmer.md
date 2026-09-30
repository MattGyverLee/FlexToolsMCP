# Implementation report -- CP1 (Foundation), lex-programmer

Spec: [`../SPEC.md`](../SPEC.md) (APPROVED-WITH-EDITS). Feasibility review
used as anchor source: [`cycle1-lex-programmer.md`](cycle1-lex-programmer.md).
Checkpoint plan: [`../tasks.md`](../tasks.md) (CP1 checked off there).

## Files created

- `src/flextoolsmcp/server/diagnostic/__init__.py` -- package docstring
  explaining the dedicated-subpackage rationale (clean tree for the future
  section-12 AST no-transmission scan).
- `src/flextoolsmcp/server/diagnostic/triggers.py` -- section 6.1 trigger
  predicate (`is_reportable_close`, `find_reportable_closes`) +
  `NON_REPORTABLE_CODES`; section 6.1.3 casting-recurrence detection
  (`casting_recurrence_signature`, `detect_casting_recurrence`); section 6.2
  inferred workaround signal (`infer_workaround`).
- `src/flextoolsmcp/server/diagnostic/signature.py` -- section 6.3
  code-independent signature: `signature_for_runtime_fail`,
  `signature_for_invalid_api_chain`, `signature_for_casting_recurrence`,
  and a dispatcher `compute_signature`. Pure functions, hashing only
  `(exception-class, normalized failing symbol)` / normalized chain /
  casting signature -- never `code_sha256`.
- `src/flextoolsmcp/server/diagnostic/offered_store.py` -- section 6.4
  `offered.json` persistence: `load_store`/`save_store` (fail-open on
  corrupt/missing file, never raises), `prune` (LRU by `last_seen`, default
  cap 500), `should_offer`, `record_offer`, `record_decision`. Path is
  injectable via `path_fn` (mirrors `op_telemetry`'s `log_dir_fn`
  convention) so tests point at a temp dir.
- `tests/test_diagnostic_report_foundation.py` -- 35 unit tests (see
  "Tests" below).
- `specs/diagnostic-report/tasks.md` -- durable 4-checkpoint plan (CP1
  checked off; CP2-CP4 unchecked with a `**Checkpoint:**` status line each).

CP2/CP3 modules (`reconstruct.py`, `normalize.py`, `render.py`,
`transports.py`) were deliberately **deferred**, not stubbed -- per the
brief's "or defer" option -- to avoid dead code with no tests this
checkpoint.

## Files modified

- `src/flextoolsmcp/server/models.py` -- added optional `user_request`
  field (verbatim text, `max_length=4000`) to `FlexToolsStartInput`
  (turn-level, primary) and `RunModuleInput` (per-op override).
- `src/flextoolsmcp/server/tool_definitions.py` -- documented
  `user_request` in the `flextools_start` and `flextools_run_module` tool
  descriptions, next to the existing `user_intent` guidance.
- `src/flextoolsmcp/server/session.py` -- `SessionState` gained a
  `user_request: str = ""` field (turn-level; **reset, not inherited**, on
  every `configure()` call, since a fresh `flextools_start` call marks a
  new turn boundary per the Q3 rotation-stitching review note), a
  `get_user_request()` accessor, and `configure()`'s known-kwargs handling.
- `src/flextoolsmcp/server/handlers/admin.py` -- `handle_start()` reads
  `args.get("user_request")` and threads it into
  `session_state.configure(user_request=...)`.
- `src/flextoolsmcp/server/handlers/execution.py` -- `handle_run_module()`
  reads `args.get("user_request")` and falls back to
  `session_state.get_user_request()` when the op didn't supply its own
  (mid-turn-drift override semantics per spec section 4/Q6). Both
  `_log_operation_start()` call sites (the early `SyntaxError` branch and
  the main path) now pass `user_request=user_request`.
  `_log_operation_start()` itself gained a `user_request` parameter, a new
  `User request:` log line, and computes the effective value (explicit
  value, else fall back to `user_intent`, else `"(not provided)"` for
  display) before stashing.
- `src/flextoolsmcp/server/handlers/op_telemetry.py` -- `_stash_op_start()`
  gained a `user_request` parameter (stored with the same fallback-to-
  `user_intent` logic applied defensively inside the function too, so the
  stash is correct even if a caller doesn't pre-apply it);
  `_write_jsonl_line()`'s record dict gained a `user_request` field next to
  `user_intent`. Extracted the existing intent-grouping loop out of
  `compute_jsonl_statistics()` into a new public
  `group_records_by_intent()` function (behavior unchanged) so
  `diagnostic/triggers.py` can reuse the exact same turn-boundary logic
  (spec section 5) instead of duplicating it. **E7 preserved**: the
  grouping key is still `user_intent` alone; `user_request` is not part of
  the key.

## Module layout rationale

`diagnostic/` is a standalone subpackage under `server/` with no imports
back into `execution.py`/`op_telemetry.py`/`session.py` -- it only imports
stdlib (`hashlib`, `json`, `re`, `time`, `pathlib`). `triggers.py` and
`signature.py` are pure functions operating on plain dicts (the JSONL
record shape), so CP1 has zero coupling to session-log parsing; CP2's
reconstruction code will supply the extra context (`failing_symbol`,
`chain`, `casting_signature`) that isn't present on the bare JSONL record.
This keeps the future section-12 AST scan scoped tightly to
`diagnostic/*.py` with no risk of false positives/negatives from unrelated
server code, and keeps CP1's surface are exactly the three files named in
the brief.

## Tests

`python -m pytest tests/test_diagnostic_report_foundation.py -q` ->
**36 passed** (0 failed). Full suite regression check:
`python -m pytest tests -q` -> **486 passed** (0 failed), confirming no
existing behavior (including `op_telemetry`'s green-rate/turns-to-green
analytics, which depend on the refactored grouping helper) regressed.

Coverage highlights against the section 12 CP1-relevant criteria:
- Trigger matrix: `runtime_fail` (both a named exception class and a
  generic one) offers; `timeout` never does, even with an
  exception-shaped `error_code`; `invalid_api_chain` offers;
  `casting_issues_detected` offers only on same-signature recurrence
  within a turn (first occurrence, and a recurrence with a *different*
  signature, both correctly do not fire); every one of the 13
  `NON_REPORTABLE_CODES` is parametrized and asserted never to fire under
  either a `preflight_reject` or (defensively) a `runtime_fail` outcome.
- Dedupe: two same-turn ops with different `code_sha256` but the same
  exception class + failing symbol produce the identical signature and
  collapse to exactly one `offered.json` entry (`offer_count == 2`).
- `dont_ask_again` persists across a simulated restart (fresh
  `load_store()` call, no in-memory state carried over); a corrupt
  `offered.json` (invalid JSON) fails open -- `load_store`/`should_offer`
  never raise, and a subsequent `record_offer()` correctly overwrites the
  corrupt file with valid JSON.
- `user_request` round-trips into the JSONL record verbatim when supplied,
  falls back to `user_intent` when absent, and round-trips as `""` when
  both are absent.

## Deviations from the brief / decisions made

1. **Session-level `user_request` carry-through was added**, beyond the
   literal three-file list in the brief's STEP 2 (`tool_definitions.py`,
   `execution.py`, `op_telemetry.py`). The brief's own spec anchor (section
   4/Q6: "Primary/mandatory on `flextools_start` (turn-level); optional
   override on `run_module` only when intent drifts mid-turn") only makes
   sense operationally if the turn-level value set at `flextools_start`
   actually reaches ops that don't repeat it -- otherwise the field would
   sit in the schema unused. Implemented via the same inheritance idiom
   already used for `project_name`/`write_enabled` (`session.py` +
   `admin.py`), reset (not inherited) on every `configure()` call so it
   never leaks across a real turn boundary. This is plumbing only --
   no reconstruction/rendering logic was touched.
2. **Casting-recurrence signature is a coarse v1 heuristic**
   (`triggers.casting_recurrence_signature`): the JSONL record has no
   per-issue casting detail (property/pattern) today, only
   `error_code == "casting_issues_detected"` and `preflight_gate`. Absent
   a richer signal, any two `casting_issues_detected` closes in the same
   turn sharing the same `preflight_gate` (or, if that's also blank, any
   two at all) count as a recurrence. Documented inline as a known
   simplification to refine once per-issue casting signatures are threaded
   into the JSONL schema (a natural CP2/CP3 follow-up, not blocking CP1's
   acceptance criteria as written).
3. **`signature.compute_signature()` takes `failing_symbol`/`chain`/
   `casting_signature` as explicit optional parameters** rather than
   requiring them on the record, because the bare JSONL record (CP1's only
   input) doesn't carry traceback/chain detail -- that lives in the
   session-log prose and is CP2's reconstruction job. CP1 ships the hashing
   primitives with a clean seam for CP2 to fill in.
4. **CP2/CP3 modules were deferred, not stubbed** (`reconstruct.py`,
   `normalize.py`, `render.py`, `transports.py` do not exist yet) -- the
   brief allowed either option and stub files with no tests would just be
   dead code to delete/rewrite next spurt.
5. No live FLEx/LCM code paths were touched; all new/modified code is
   offline log/telemetry plumbing and pure functions, consistent with the
   constraint.

No blocking deviations. All STEP 0-7 items from the brief are complete.
