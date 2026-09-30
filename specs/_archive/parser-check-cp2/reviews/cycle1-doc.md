# Doc Agent Report -- CP2 contract-fit brief

**Date:** 2026-09-18
**Trigger:** planning input for `parser-check CP2` (read-only analysis, no edits made)

## 1. Envelope fit

**`flextools_try_word` (three answer levels).** All three fit the existing
success envelope (`_contract`, `status:"ok"`, `op_id`, free-form extra keys,
`extra="ignore"`) with no version bump -- same additive pattern as
`diagnostic_report`/`auto_discovered`. Suggested per-level shape:
- Mode A (restricted-to-hypothesis): `result` + a `restricted: true` flag +
  the 5.1.3 divergence observation (never a verdict, per SPEC 9.3.2).
- Mode B (yes/no): `result: {parsed: bool}` only -- per FR-013 it must not
  smuggle in analyses; pair with a `hint`/`next_step` pointing at A or C, never
  claiming to explain.
- Mode C (full explanation): `result` + trace payload.

**FR-028 (inline result OR run handle from one call) is not expressible as a
single fixed shape today**, but it does not need a contract-version bump --
`run_module`'s `discovery_redirect` already establishes the precedent of one
tool emitting materially different `status:"ok"` shapes distinguished by which
keys are present. Recommend the same discriminator style here: presence of
`result` (fast path, job finished inside the grace window) XOR presence of
`run_id` with no `result` (async handle). Document this explicitly in the new
contract file as its own named block, the way `RunModuleSuccess` fields are
documented -- do not leave it implicit.

**Large `TraceWordXml` payload (mode C / open question 3 in CP2-SPEC.md
section 10):** the contract has a real precedent for keeping bulk data out of
the response body -- `diagnostic_report.report_path` (points at a file) and
the casting-warning line cap (10 lines, "capped"). Recommend the trace XML
live in the run artifact (5.5) and the response carry a summary plus a
pointer field, not the raw XML inline. This should be a resolved design
decision before the CP2 contract file is written, not left to the
implementer.

**`flextools_parse_status` per stage.** `starting`/`loading_grammar`/`parsing`
map cleanly to `status:"ok"` + `state` + progress fields. `completed` adds the
result summary. **`failed` and `cancelled` are ambiguous and need a
classification call, not a guess:** FR-034 wants a `failed` terminal state to
carry `next_step` (sounds like a success envelope reporting a dead job, not
an error response), and FR-036 says a cancelled run "MUST be reportable" with
`words_completed`/`state_at_cancel` -- also success-envelope language. But
`parse_job_cancelled` is listed in CP2-SPEC.md section 7 as an **error code**
with exactly those two fields plus `run_id`. Two readings are both plausible:
(a) `parse_status` always returns `status:"ok"` with `state:"cancelled"|
"failed"` and the three new codes only fire from *other* calls that touch a
dead/cancelled run (e.g., a second cancel request, or `try_word` polling a
run that was cancelled from elsewhere); or (b) `parse_status` itself rejects
with `parse_job_cancelled` when asked about a cancelled run. **Flag for
`/lex-lead` or the user** -- this decides whether `flextools_parse_status`
ever emits `status:"error"` at all.

## 2. The three codes

Current table in `docs/TOOL-CONTRACT.md` has **22 rows** today (verified by
count and by its own line 69, "one of the 22 codes below" -- CP2-SPEC.md's
"count bumped from 22" is correct, not an assumption to correct). Adding
three brings the **documented count to 25**.

- `parse_run_not_found` and `parse_morph_unresolved` -- no collision with any
  existing code; both are new leaf checks.
- `parse_job_cancelled` -- no collision, but see the ambiguity above.
- **Field-count drift already exists between the two specs, before CP2 even
  starts:** `SPEC.md` section 14 (line 1987) lists `parse_morph_unresolved`
  with **five** fields (`morph, position, resolved_to, candidates, hint`),
  while `CP2-SPEC.md` section 7 (and this task's brief) lists **four**
  (`morph, candidates, position, hint`), dropping `resolved_to`. Since
  `resolved_to` (`none`/`ambiguous`/`no_msa`) is exactly the distinction 5.1.2
  needs (unresolved vs. no-MSA vs. ambiguous), dropping it silently would
  lose diagnostic value FR-012's caller likely wants. This needs a resolved
  answer before the CP2 contract file is authored -- flag to `/lex-lead`.
- All three additive under `tool-responses/1.0`; no version bump. Same
  `extra="forbid"` detail-model + `Literal` discriminator pattern as CP1's
  four codes (`response_models.py:142+`).
- CHANGELOG mechanics (from the current `[Unreleased]` entry, lines 3-21):
  one prose paragraph per code under `### Tool contract`, naming what each
  code means, closing with an explicit count-bump sentence ("moves from 22 to
  25 accordingly").

## 3. `READ_ONLY_SAFE`

Declared once as a shared `ToolAnnotations(readOnlyHint=True,
destructiveHint=False, idempotentHint=True)` constant
(`src/flextoolsmcp/server/tool_definitions.py:81`) and applied per-tool via
`annotations=READ_ONLY_SAFE` on each `ToolDef` entry -- every existing
read-only tool uses the identical line. Applying it to the two new tools is
mechanical (one kwarg each), but per CP2-SPEC.md section 1, the annotation's
truth rests entirely on `HCParser_DoesNotLoadXCore` (a call-path guarantee,
not a class-level one) -- the contract file should say so explicitly, the way
the CP1 contract files already state "Annotation: `READ_ONLY_SAFE`" in their
header line.

## 4. Guidance/`hint` conventions

Two distinct fields exist and CP2 needs both: `hint` (plain string, on error
detail models, e.g. `parser_tool_missing.install_hint`) and the structured
`next_step` object (`SPEC.md` 10.1: `{action, tool, args, rationale,
est_cost}`, `est_cost` mandatory, values `inline|seconds|minutes|hours|
unbounded`). House rule already established and directly answers FR-014/
FR-022: **never propose a tool that does not exist** -- SPEC 10.1 states there
is no lexicon-query tool, so any "look it up" guidance must route through a
`flextools_run_module` snippet, never an imagined tool name. For FR-013,
precedent is CP1's degraded rows (`flextools_health-parser-block.md` lines
102-113): when the real answer would name a not-yet-real tool/capability, the
text is rewritten to describe only the state, never claim an explanation that
isn't there.

## 5. Documentation deliverables

- New `specs/parser-check/contracts/flextools_try_word.md` and
  `flextools_parse_status.md`, following the CP1 contract-file format
  (header line with Checkpoint/Annotation/Contract version, Input, Output,
  Errors table, Behavioural guarantees).
- Update `specs/parser-check/contracts/error-codes.md` (or a CP2-scoped
  sibling) with the three new codes -- resolve the field-count drift first.
- `docs/TOOL-CONTRACT.md`: add three rows to the error-code table, bump "22"
  to "25" in the `error_code` row description (line 69).
- `CHANGELOG.md`: new `### Tool contract` entry under `[Unreleased]` (or a
  fresh block if the CP1 one has been released) matching the prose pattern
  above.
- No `CLAUDE.md` count reference exists today (checked: none found) --
  nothing to update there.

## Open items for `/lex-lead`

1. Resolve `parse_morph_unresolved` field-count drift (4 vs 5 fields,
   `resolved_to`).
2. Resolve whether `parse_status` on a cancelled/failed run is a success
   envelope or triggers `parse_job_cancelled` as an error.
3. Confirm the inline-vs-run_id discriminator keys before the contract file
   is drafted.
