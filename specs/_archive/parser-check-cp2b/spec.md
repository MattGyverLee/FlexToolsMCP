# Feature Specification: parser-check CP2a-bridge + CP2b -- the assistant reaches the parser

**Feature Branch**: `feat/parser-check-cp2` (proposed; this repository is still on
`feat/parser-check-cp1` -- see "Open maintainer decision" below)

**Created**: 2026-09-19

**Status**: Ready for planning -- CP2a's evidence gate is satisfied

**Input**: `/speckit-plan specs/parser-check/CP2-SPEC.md`, scoped by the user to the
remaining, never-planned half of CP2.

---

## This is a scoping specification, not a new one

**The authoritative requirement text is [`../parser-check-cp2/spec.md`](../parser-check-cp2/spec.md).**
That document specifies *all* of CP2 -- US1 through US4, FR-001 through FR-043,
SC-001 through SC-017, Decisions D1-D5, the Verbatim Constraints and the risk
register. Nothing here restates it and nothing here overrides it. This file exists
because Decision D4 split CP2 into three parts that are planned and built
separately, and the part planned here is the last two:

| Part | Requirements | Repository | Status |
|---|---|---|---|
| **CP2a** | US1 -- FR-001..FR-010, FR-041..FR-043 | `flexicon` | **complete** -- 31/31 tasks, evidence recorded, release commit `1b6f5533`; **`pyflexicon` 4.9.0 is published** |
| **CP2a-bridge** | FR-011 (this repository's half) | FlexToolsMCP | **not started** -- planned here |
| **CP2b** | US2, US3, US4 -- FR-012..FR-040 | FlexToolsMCP | **not started** -- planned here |

Source document: [`../parser-check/CP2-SPEC.md`](../parser-check/CP2-SPEC.md),
sections 4 (Part B), 5 (Part C), 6 (inherited from CP1), 7 (error codes),
8 (test plan) and 9 (exit criteria). Parent: [`../parser-check/SPEC.md`](../parser-check/SPEC.md)
section 15, CP2 row.

---

## Entry gate -- satisfied

CP2b may not start until CP2a's evidence gate
([`../parser-check-cp2/contracts/evidence-gate.md`](../parser-check-cp2/contracts/evidence-gate.md))
is satisfied. It is.

| Condition | Required | Status |
|---|---|---|
| A1 complete and recorded | yes | **PASS** -- 1923 passed, 0 failed |
| A2 complete and recorded | yes | **PASS** -- 11 passed; `Reset()` and `IsUpToDate()` verified on the real installed component for the first time |
| A3 complete and recorded, **including A3.3** | yes | **PASS** -- 18 passed, `run_mode: live`; the unconditional discard witnessed by morpher identity |
| A4 (live stale branch) | no -- deferred to CP2b | carried forward as **E-D**, below |
| `4.9.0` tag pushed | **no** -- the seam is at *proven*, not *released* | **done anyway** -- 4.9.0 published 2026-09-19, **E-C resolved** |
| CP2a-bridge landed | yes, before CP2b's first parser task | **this specification's first phase** |

Evidence: [`../parser-check-cp2/evidence/cp2a-evidence.md`](../parser-check-cp2/evidence/cp2a-evidence.md).

---

## Scope

### In scope

**CP2a-bridge** -- FR-011's repository-side half:

- Raise the declared minimum to `pyflexicon>=4.9.0,<5` in `pyproject.toml` **and**
  `requirements.txt`.
- Regenerate the bundled index artifacts so the indexed version equals the declared
  floor.
- A standing test asserting floor/index equality, so the 2.10.0 incident (an index
  built at 4.5.2 shipped against a `>=4.3.0` floor) cannot recur silently.

**CP2b** -- US2, US3 and US4 of the parent spec:

- **FR-012..FR-017** -- `flextools_try_word` with all three answer levels, the engine
  gate as first action, and the `READ_ONLY_SAFE` annotation backed by the
  `HCParser_DoesNotLoadXCore` standing test.
- **FR-018..FR-025** -- the morph resolver: headword / headword+sense / identifier
  input, refusal on any unresolvable piece, the once-per-run lookup index, the
  bounded proposal assist, and the observation-not-verdict rule.
- **FR-026..FR-036** -- the run mechanism: one execution path, seven stages, the
  grace window, incremental result persistence, priority ordering, word-boundary
  interleave, cooperative cancellation, and `flextools_parse_status`.
- **FR-037..FR-040** -- three additive refusal codes with the contract count raised
  from 22 to 25, the CP1 `next_step` rows that degraded to `tool: null` repointed,
  the SPEC 16 test groups CP1 deferred, and D5's grammar-lint deferral recorded.

### Out of scope

Everything the parent spec already excludes -- filing (CP4), batch scoping and run
comparison (CP3), the sandbox (CP5), any general segmenter -- plus:

| Out of scope here | Where it belongs | Why |
|---|---|---|
| The `v4.9.0` tag push and `gh release create` | **done** -- maintainer performed it, E-C resolved | The bridge may therefore raise the floor to a version that genuinely resolves. It is still not *installed* here; see `research.md` R-01 for what that does and does not let this slice prove. |
| Re-planning or re-running any CP2a task | done | 31/31 complete, evidence recorded. |
| `parser_probe.py` | FR-041 / SC-016 | This checkpoint changes **0 lines** of it, exactly as CP2a did. |

---

## Requirements

**Verbatim.** All functional requirements, success criteria, key entities,
assumptions, dependencies, decisions and risks are those of
[`../parser-check-cp2/spec.md`](../parser-check-cp2/spec.md). This section records
only what CP2a's execution *changed* about how they must be read -- the deltas a
planner working from the parent text alone would get wrong.

### Delta 1 -- the facade's real names differ from CP2-SPEC section 3.1

`CP2-SPEC.md` section 3.1 tabulates the facade as `TryWord` / `TryWordXml` /
`TraceWord`. **That table describes a design that was not built.** The shipped
`4.9.0` surface, frozen by a set-equality test in flexicon
(`tests/test_parser_offline.py`, A1.4), is exactly six members:

```
GetAvailability()                          -> ParserAvailability(available, reason, version)
ParseWord(word)                            -> structured result, live object references
ParseWordXml(word)                         -> serialized parse document
TraceWordXml(word, analyses=None)          -> serialized trace document
Reload()                                   -> None   (reset, then update)
IsUpToDate()                               -> bool
```

Anything in CP2b that binds `TryWord`, `TryWordXml` or `TraceWord` binds a name
that does not exist. The parent spec's FR-001 is satisfied by the six above.

### Delta 2 -- an empty restriction is refused, not widened

`TraceWordXml(word, analyses)` raises `FP_ParameterError` on an **empty** iterable.
`None` means unrestricted; empty means the underlying component admits nothing --
near-opposites, and the setting **outlives the call**.

This is the defect CP2a's live tier caught after a green offline suite and four
green structural ratchets. CP2b's mode-A tool sits directly on this call, so:

- **FR-019's refusal must fire before the facade is reached.** A decomposition that
  resolves to an empty analysis set is `parse_morph_unresolved`, not an
  `FP_ParameterError` leaking out as an internal error.
- CP2b inherits both the null-vs-empty contract and the outlives-the-call property.
  The facade clears its restriction before the next plain parse; CP2b must not
  assume it, and must not add a second clearing path.

### Delta 3 -- the three read gaps shipped with no tests

FR-007 (`Texts.GetGenres`), FR-008 (`Allomorphs.GetOwningEntry`) and FR-009
(`MSA.GetAll`) each had an implementation task in CP2a and **no test task**. Nothing
pins the empty-collection contract, the null-owner branch, or the MSA wiring.

CP2b's resolver terminates in FR-009's surface (`MSA.GetAll`) and CP3's genre
scoping depends on FR-007. This specification treats closing that gap as a
**precondition of the resolver**, not as inherited debt to mention: a resolver built
on an untested accessor reproduces the silent-narrowing failure mode FR-019 exists
to prevent.

### Delta 4 -- a CAPABILITIES token is not a runtime probe

`flexicon.CAPABILITIES` gained `"parser"`, meaning *this build implements the
surface*. It does **not** mean the parser is reachable on the machine. CP2b must
call `GetAvailability()` and must never infer reachability from the token.

### Delta 5 -- E-D is now this checkpoint's obligation

Tier A4 -- proving FR-043's *stale* half **live** -- was deferred to CP2b. It
requires editing a project so the model registers as changed, which is a live write.
It requires human authorisation against a backed-up or copied project, and an
unattended run must stop with `needs_human` rather than perform it.

Precisely what is unproven today: A3.3 shows `Reload()` discards unconditionally and
A1.6 shows the facade reloads before parsing when currency reads false. What is
**not** proven live is the automatic path firing when the model genuinely changes
underneath a held grammar. That link is covered only against a stubbed currency read.

### Delta 6 -- the diagnostic levels report their result, not just their trace

`explain` and `restricted` were silent about outcome. `worker_main.py`'s
`BackendFacade.parse()` returns `{"parse": None, ...}` for both branches
(`:728` restricted, `:732` explain), so `handlers/parse.py`'s
`_inline_response` else-branch (`:538-554`, concretely `:539-543`) had nothing
to report but `trace_available` / `trace_path` / `trace_bytes`. A caller at a
diagnostic level could not tell success from failure without opening the trace
file itself.

**The fix derives the answer from the trace document already in hand, for a
document we can read -- no second parser call.** A trace that has no `Root`
at all cannot be read, so nothing is derived from it; that case is not an
exception to the derivation claim, it is the boundary of it, and it is
covered on its own terms below. `TraceWordXml` and `ParseWordXml` are the same C# method
(`HCParser.cs:120-131`): both build one `<Wordform>` document from
`m_morpher.ParseWord(...)` and append an `<Analysis>` child per surviving
analysis (`:213-215`), independently of the `tracing` flag. `<Trace>`
(`:217-218`) is a separate sibling holding only the rejected paths that
tracing adds; those are never promoted into `<Analysis>`. `HCParser.cs:104-113`
shows the non-XML `ParseWord` applies the identical `GetMorphs` filter, so
counting `<Analysis>` children on the trace document does not approximate
`ParseResult.Analyses.Count` -- it **equals** it. `FormatHCTrace.xsl:194`
corroborates that FieldWorks itself already treats `/Wordform/Analysis` as the
success marker.

`explain` reports `parsed` and `analysis_count`, derived this way, alongside
the trace fields already shipped.

**`restricted` reports different field names, and that is not cosmetic.**
`ParseToXml` installs `LexEntrySelector`/`RuleSelector` from
`selectTraceMorphs` **before** calling `ParseWord` (`HCParser.cs:186-199,211`)
-- a real narrowing of the search space, not a post-hoc filter on trace
output. The `<Analysis>` survivors of a restricted trace answer "does my
restriction still admit an analysis", never "does this word parse at all".
Naming that count `parsed`/`analysis_count` -- the names `plain` uses for the
unrestricted question -- would let a caller compare a restricted `false`
against a genuine unrestricted failure as though they meant the same thing.
**`restricted` therefore reports `hypothesis_held: bool` and
`restricted_analysis_count: int`, and never `parsed`.**

**The `<Error>` case is a contract, stated plainly.** `ParseToXml` catches
exceptions during tracing and appends `<Error>` instead of any `<Analysis>`
(`HCParser.cs:219-222`), so a zero-`<Analysis>` document is ambiguous between
"genuinely no analysis" and "the parse itself errored". A document carrying
`<Error>` reports `parse_error` and emits **neither** `parsed` **nor**
`hypothesis_held` -- there is nothing honest to say about either question.
This is a deliberate asymmetry with the `plain` level, where `ParseWord`
propagates the exception and the request fails outright: the diagnostic
levels have already written the trace to disk by the time the error occurs,
and that trace remains useful, so the *request* succeeded even though the
*parse* did not.

**A document with no `Root` at all joins the `<Error>` case rather than
being folded into "zero `<Analysis>`".** `_summarize_trace` previously
treated a rootless trace the same as a document with a `Root` but no
`<Analysis>` children, returning `{"parsed": False, "analysis_count": 0}` --
a manufactured answer, not a derived one, because a document that cannot be
read offers nothing to count in the first place. As of cycle 4 this branch
reports `parse_error` instead, the same as an `<Error>` element: both are
"the parse produced nothing this response can honestly call parsed or not,"
and both emit **neither** `parsed` **nor** `hypothesis_held`. This closes
alongside the `<Error>` fix rather than after it, because the defect is the
same one -- asserting a negative the document does not support -- reached
by a different route.

**Two defects this closes, and one it was found alongside.** `parse.py:465`'s
guard -- `if level != "restricted" and not result.get("parsed", False):` --
read a key the `explain`/`restricted` branch of `_inline_response` never
wrote, so it was always true and `_propose_decomposition` fired the
"proposed, unverified" assist on every explain call, including successful
ones -- against `contracts/tools.md:97` ("Agreement produces no commentary")
and FR-025. `parse.py:776-784`'s `_level_guidance` explain branch had the same
root cause: no gate existed, so it returned `explains_failure: True`
unconditionally, for successful and failed explain calls alike. Found
alongside these: a new HIGH sibling at `parse.py:891-892`, where
`_result_summary`'s loop tested `parse.get("parsed")` against the same
never-populated key, so **every** completed `explain`/`restricted` run polled
through `flextools_parse_status` reported `result_summary.parsed: 0` --
indistinguishable from "every word failed to parse," even when the traces on
disk showed successful analyses. `_result_summary` now counts `parsed` only
over entries that actually carry that key (`plain` results), and adds a
separate `hypotheses_held` count for `restricted` results. One integer is not
allowed to stand for two different questions.

**A fourth instance, closed this cycle rather than deferred.**
`_level_guidance`'s `restricted` branch (`parse.py:852-855`) had the
identical shape, one level up: it returned `explains_failure: True`
unconditionally, written before `hypothesis_held` existed to gate on and
never revisited once it did. The lead ruled this closes now, not later. The
branch reads the now-populated key: a held hypothesis reports
`explains_failure: False` with no rungs -- the caller's restriction
succeeded, there is nothing to steer them toward. A hypothesis that did not
hold is unchanged (`explains_failure: True`, still no rungs -- the caller
already committed to a level appropriate to their hypothesis, so nothing
new to suggest). A `parse_error` claims neither: `explains_failure` is
omitted entirely, the same "presence of the key is the fact" discipline
already applied to the `explain` branch immediately above.

### Delta 7 -- a narrow analysis signature, inline only (spec only; not built this spurt)

Nobody implements this delta in the current cycle; it is recorded so the
shape is pinned before anyone does. It answers the cycle 1 archivist review's
part B: CP2b may serialize what a single already-completed `ParseWord` call
holds; it may not persist or accumulate anything across calls.

**Shape, reused verbatim.** If and when the plain level's `parse` block
carries a per-analysis signature, it is `CP3-SPEC.md` section 6.2's durable
signature, unchanged: the **ordered sequence of `(MorphRA.Hvo, MsaRA.Hvo)`
pairs**, carried alongside the rendered morph form and MSA label for each
pair (`CP3-SPEC.md:395-402`). This is `MatchesIWfiAnalysis`'s own predicate
(`ParseResult.cs:102-133`) expressed durably, not a second serialization
invented for this checkpoint. Reusing it here rather than inventing a
CP2b-flavoured shape is what keeps the signature CP3's diff (Part D, section
6) reads out of `results.jsonl` tomorrow identical to the one CP2b would hand
back inline today -- one definition, not two that drift apart.

**Computed from the call already made, nothing more.** The signature would be
built from the single `ParseWord` call's live result before it is discarded
-- the same object `_summarize_plain` (`worker_main.py:754-785`) already
reduces to a count. No second facade call, no caching, no cross-call
accumulation.

**What stays out, explicitly.** No persistence and no queryable-after-the-fact
half -- browsable by run_id, across many words, after the call has returned --
and none of CP3 Part E's synthesis on top of a signature: no tier
(`CP3-SPEC.md` section 7.2's `IsComplete` join), no affirmed/indeterminate
provenance split (section 7.3), no candidate pairing or promotion-only ranking
(section 7.4). CP2b, if it ever ships this, reports "the parser said X"; "and
the human agreed/disagreed" stays CP3's synthesis.

**Why the boundary is drawn here, not moved.** The persistent, queryable-
across-runs half of the original ask is already owned by CP3 Parts B/C --
`run.json`, `results.jsonl`, and `flextools_parse_log` as the read surface
(`CP3-SPEC.md` sections 4.2-4.4, 9). A second CP2b-owned persistence
mechanism for single words would duplicate that artifact under a different
name, which is exactly the "second execution model" `CP3-SPEC.md:33-37`
already forbids CP3 itself from growing -- one layer up, in storage rather
than execution.

---

## Success Criteria

Those of the parent spec. The ones this slice must actually discharge, since CP2a
discharged the rest:

| SC | What discharges it here |
|---|---|
| SC-003 | `HCParser_DoesNotLoadXCore`, asserted against the **worker process's** loaded-assembly list after a real update and parse |
| SC-004 | inline answer within the 5-second grace window, >=95% of attempts, single word against a loaded grammar |
| SC-005 | 100% refusal with piece and candidates named; **0** parses run |
| SC-006 | 0 substitutions, widenings, reorderings, scores or demotions; 0 confidence figures; 0 remarks on agreement |
| SC-007 | lookup structures built exactly once per run |
| SC-008 | 0 results lost across kill or cancel |
| SC-009 | urgent word begins within one word boundary; 0 words repeated; grammar loaded exactly once |
| SC-010 | 0 runs cancelled or slowed by the grace window closing |
| SC-011 | 0 `next_step` references to tools that do not exist; every CP1 `tool: null` row repointed |
| SC-012 / SC-017 | all three levels live against `IndonesianHC-Complete`; long-run behaviours live against `Malay Parsing-20230810withHC` |
| SC-013 | full suite green including CP1's deferred groups; **declared minimum equals the version of every bundled flexicon index artifact** |
| SC-014 / SC-015 | at most one held grammar; 0 parses from unconfirmed currency |
| SC-016 | 0 lines changed in `parser_probe.py`; each check states what the other carries that it lacks |

SC-001, SC-002 (flexicon side) are discharged by CP2a's evidence. SC-002's
FlexToolsMCP-side standing test already ships from CP1 and must stay green.

---

## Verbatim Constraints

Those of the parent spec. The ones this slice consumes, reproduced exactly:

- Declared minimum, in both `pyproject.toml` and `requirements.txt`:
  `pyflexicon>=4.9.0,<5`
- Bundled index artifacts that must exist and match that floor: the complete output
  of `python -m flextoolsmcp.refresh` for `4.9.0` under
  `src/flextoolsmcp/index/python/`, which currently comprises
  `flexicon_api_v4.9.0.json` and `flexicon_lcm_bridge_v4.9.0.json`
- New assistant tools: `flextools_try_word`, `flextools_parse_status`
- Standing test name: `HCParser_DoesNotLoadXCore`
- Run stages, exactly these names:
  `starting | loading_grammar | parsing | filing | completed | failed | cancelled`
- Priority levels and values, lowest wins:
  `ReloadGrammarAndLexicon = 0, TryAWord = 1, High = 2, Medium = 3, Low = 4`
- The shipped capability check this checkpoint must not modify:
  `src/flextoolsmcp/server/parser_probe.py`
- Live verification projects: `IndonesianHC-Complete`, `Malay Parsing-20230810withHC`
- Read-only annotation applied to both new tools: `READ_ONLY_SAFE`
- Refusal codes added: `parse_morph_unresolved`, `parse_run_not_found`,
  `parse_job_cancelled`; documented count raised **22 -> 25**

`parse_morph_unresolved`'s five detail fields, **in this order**:
`morph`, `position`, `resolved_to`, `candidates`, `hint`, where `resolved_to` is one
of `none` | `ambiguous` | `no_msa`.

**A third version-locked artifact the parent spec's list does not name.**
`src/flextoolsmcp/index/common_patterns_flexicon-v4.8.0.json` is also keyed to the
flexicon version, lives one directory above the path the Verbatim Constraints quote,
and is produced by the same refresh. It is treated in `research.md` (R-04); the
Verbatim Constraints' "currently comprises" is a statement about
`index/python/`, not a closed list of every flexicon-version-locked file in the repo.

---

## Escalations carried into this slice

| ID | What | Status |
|---|---|---|
| **E-C** | the `v4.9.0` tag push and `gh release create` | **RESOLVED 2026-09-19** -- `pyflexicon` 4.9.0 is published. The residual constraint is environmental, not procedural: the published distribution is not installed in this verification environment and will not be within this session, so the floor's *resolvability* is proved by its own task, not by the equality test. See `research.md` R-01. |
| **E-D** | tier A4, the live half of FR-043's stale branch | **standing, unresolved.** Requires a live write and human authorisation. An unattended run must stop with `needs_human`. |

## Open maintainer decision

This repository is on branch `feat/parser-check-cp1`. All CP2 spec work to date is
committed there, and CP2a's only deliverable here was its evidence artifact, so
continuing was consistent rather than a new deviation. **CP2b writes production code
in this repository**, which is the point at which the branch question stops being
cosmetic. The CP2 handoff `branch_note` asked for `feat/parser-check-cp2`. A
maintainer should decide before the first CP2b implementation task.
