# Decision memo: analysis-readback for a normal parse (CP2b vs CP3)

**Author:** /lex-archivist, cycle 1. Read-only cycle; no code or spec edited.

## A. Which checkpoint owns "how many analyses succeeded, queryable"

**Verdict: split.** The count belongs to CP2b (it already ships there). The
*queryable* half -- retrieving analyses after the call, across runs -- belongs
to CP3.

`_summarize_plain` (`src/flextoolsmcp/server/parse/worker_main.py:754-782`)
already returns `{"parsed": bool, "analysis_count": int}` on the plain level of
`flextools_try_word`. That is the count, shipped, additive, no delta needed.

The user's second verb -- "QUERY those analyses" -- is a persistence and
retrieval capability CP3 Part B/C own by name: the run artifact set
(`run.json`, `results.jsonl`, CP3-SPEC.md:208-284), the per-word append-only
record CP3 mandates so a job's output survives past the call (CP3-SPEC.md
§4.2, §4.4), and `flextools_parse_log` (CP3-SPEC.md §9) as the read surface.
A second, CP2b-owned persistence/query mechanism for single words would
duplicate that artifact under a different name -- the "second execution
model" CP3-SPEC.md:33-37 forbids CP3 from growing, one layer up in storage.

**CP3 sections pre-empted by a full readback:** §4.2-4.4 (the run artifact
is the contract; an invented shape migrates later, §15's stated risk), §6.2
(the durable signature -- must not be reinvented), and indirectly §7.6
(the deletion/duplicate projections assume the per-word record already
exists in CP3's shape). Part E's oracle (§7.2-7.4) is not at risk from a
narrow single-word summary -- tiering and provenance are batch/segment
joins, not properties of one `ParseWord` call.

## B. The narrow version CP2b may ship, and exactly where the line falls

**Verdict: CP2b may serialize what one already-completed `ParseWord` call
holds; it may not persist or accumulate that across calls.**

Line: extend `_summarize_plain` (worker_main.py:754-782) to also emit, per
analysis, the CP3 §6.2 durable signature -- **the ordered `(MorphRA.Hvo,
MsaRA.Hvo)` pairs plus rendered morph form and MSA label** -- not a second
serialization shape. Reusing §6.2 verbatim is what keeps CP3's diff (§6.2)
from being undermined: the signature CP3 reads out of `results.jsonl`
tomorrow is the one CP2b hands back inline today -- one definition, not two
that drift.

What stays out, as Part E territory: no tier (§7.2's `IsComplete` join), no
oracle wording, no affirmed/indeterminate provenance split (§7.3), no
candidate pairing (§7.4). CP2b reports "the parser said X"; "and the human
agreed/disagreed" is CP3's synthesis, per §7.2-7.4's mandatory wording.

## C. Shape: block on `flextools_try_word` vs a separate run_id-keyed tool

**Verdict: block on the existing response surfaces; no new tool.** The
premise that "a fast word never gets a run_id back inline" is **false**.

`_inline_response` (`src/flextoolsmcp/server/handlers/parse.py:508-531`)
puts `run_id` on the result dict for the grace-window (fast) path, not only
the overflow path (`_overflow_response`, same file, ~478-487). That `run_id`
**stays pollable** afterward: `ParserRunner.start_run` registers the handle
in `self._runs[handle.run_id]` unconditionally at submission
(`src/flextoolsmcp/server/parse/runner.py:336`), *before* the grace-window
wait, and `runner.py` has no eviction, pop, or TTL logic on `_runs` --
`get()` (runner.py:255) just reads the dict. `flextools_parse_status`
already can be, and is, queried against a run that finished inline.

Given that, a second run_id-keyed tool is redundant with
`flextools_parse_status`, and risks becoming the "separate synchronous path"
the run contract forbids in spirit if it re-derives results instead of
reading the one runner. The shape is to enrich the two existing payloads --
the `parse` block on `try_word`'s inline response and `_result_summary`
(handlers/parse.py:880-899, currently `words`/`parsed`/`traces_written`/
`record_dir`) on `parse_status` -- not add a third tool.

## D. Delta mechanics

**Verdict: piece 1 (the count) needs no delta -- already shipped, additive.
Piece 2 (the narrow signature readback) needs a new Delta 6 in spec.md plus
three of the four FR-037 obligations; contract stays at tool-responses/1.0.**

Piece 1: `_summarize_plain`'s `parsed`/`analysis_count` are already in the
shipped CP2b surface. No file changes.

Piece 2, files:

- `specs/parser-check-cp2b/spec.md` -- new **Delta 6**, following the
  Delta 1-5 pattern at lines 105-169. States: (a) the plain level's `parse`
  block may carry a per-analysis signature drawn from CP3-SPEC.md §6.2's
  `(MorphRA.Hvo, MsaRA.Hvo)` shape, verbatim, not reinvented; (b) it is
  computed from the single already-completed `ParseWord` call only -- no
  persistence, no cross-call accumulation, no tier/oracle synthesis.
- `specs/parser-check-cp2b/contracts/tools.md` -- the "Output" section of
  `flextools_try_word` (lines 117-120) gets a new paragraph naming the field;
  the "Contract-document obligations" table (lines 190-199) is where the
  concrete model changes are tracked.
- FR-037 table, three of four rows touched:
  - `docs/TOOL-CONTRACT.md` -- a new subsection alongside "RunModuleSuccess
    envelope" / "Inherited member fields" (docs/TOOL-CONTRACT.md:172, :255)
    documenting the new `parse` block field. No error-code count change
    (`_contract` stays `tool-responses/1.0`, docs/TOOL-CONTRACT.md:19) -- a
    success-payload addition, not a refusal code.
  - `CHANGELOG.md` -- one entry under **"Tool contract"**, the convention
    CP3-SPEC.md:674 uses for its own additive codes.
  - `server/response_models.py` -- a new detail model (e.g.
    `AnalysisSignature`), `extra="forbid"`, nested in the plain-level model.
  - `server/tool_definitions.py` -- **not required**: no new input
    argument, only a response field. Touch only for a one-line description
    truthfulness update per SPEC 10.

**Piece 2 is additive-only.** New response field, nothing removed or
renamed, no new error code -- contract stays at `tool-responses/1.0`, the
posture CP3-SPEC.md:674 states for its own codes.

## RECOMMENDATION

**piece 2 -> CP2b delta** (Delta 6, narrow signature only, inline, no
persistence) -- it reuses data CP2b's worker already holds mid-call and
CP3's own §6.2 shape, costing one delta now versus a migration later, and
pins the signature CP3's diff needs before Part D is written.

The **persistent/queryable-after-the-fact** half of the ask (results
outliving the call, browsable by run_id across many words) stays with CP3
Parts B/C (`results.jsonl`, `flextools_parse_log`) as already specced.
