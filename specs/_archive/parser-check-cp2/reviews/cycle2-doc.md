# Cycle 2 -- doc amendment pass on parser-check-cp2/spec.md

Source of truth: `reviews/cycle1-synthesis.md` sections 5-6. Applied all eleven
edits (E7's CP2-SPEC.md table row is out of scope here, per the brief).

| E-id | Applied | Section / line touched | Note |
|---|---|---|---|
| E1 | yes | Verbatim Constraints, "Bundled index" bullet | Replaced non-existent `index/python/...` path with the widened, drift-resistant phrasing naming `src/flextoolsmcp/index/python/`, the refresh command, and both filenames (api + bridge). |
| E2 | yes | FR-043; D2 "Why"/new "Binding detail" paragraph | FR-043 now a two-step obligation (reset, then reload), outcome-phrased, with the silent-failure consequence named. Method names (`HCParser.Update()`, `m_changeListener.Reset()`, `ParserWorker.ReloadGrammarAndLexicon()`, `HCParser.IsUpToDate()`) placed in D2, not FR-043. |
| E3 | yes | FR-041; D1; SC-016; Assumptions D1 bullet | "larger check" replaced with "different and overlapping" throughout; both-direction divergence stated (flexicon gains reload/currency members, this repo keeps the write op); added the accepted residual-risk pointer language to FR-041 and D1's "What it costs". `parser_probe.py` "0 lines" prohibition left untouched. |
| E7 (spec half) | yes | FR-037 | Added the five `parse_morph_unresolved` fields (`morph`, `candidates`, `position`, `hint`, `resolved_to` with its three enum values) verbatim, matching the parent SPEC.md. Did not touch `CP2-SPEC.md` (parallel agent's scope). |
| E8 | yes | FR-033; FR-036 | FR-033 now states the status tool always returns success on a terminal stage, refusing only for an unknown handle. FR-036 states the cancelled-run refusal fires only on calls acting on a dead run, not from status reporting. |
| E12 | yes | New Decisions D4 (+ D5 nearby), FR-011, Risks "Schedule" bullet, Assumptions | D4 records D-00 in full: hard predecessor phase, three-way CP2a/CP2a-bridge/CP2b split, the A1-A3 evidence gate with A4 deferred+human-authorised, and that ratchets passing is not proof. FR-011 and the Schedule risk now cross-reference D4 and note the tag/release are maintainer acts. |
| E5 | yes | FR-010 | Added the object-level-vs-Hvo-only distinction (plain parse vs. XML trace) and the repository-lookup-to-rehydrate caveat. |
| E4 | yes (Requirements only) | FR-008 | Reframed as a wrapper gap over an already-exposed data-model relationship, outcome-phrased (no citations, per house voice -- those already live in cycle1-synthesis). |
| E6 | yes | Edge Cases, 2nd bullet | Named `ParseWordXml`/`TraceWordXml` and the `form`/`word` divergence; noted the plain parse already agrees. |
| E9 | yes | FR-004 | Added the directory-equality-only scope line and the accepted-tradeoff framing. |
| E10 | yes | FR-040; new Decision D5; Assumptions | FR-040 cross-references new D5, which records the defer-to-CP3 decision, the absence evidence, and the re-probe rider. |
| E11 | yes | SC-013 | "the bundled index" -> "every bundled flexicon index artifact". |

## Not cleanly applicable

- E4's "Key Entities entry it touches": no existing Key Entities entry names the
  allomorph-owner relationship (the list covers Parser area, Capability check,
  Parse request, Morph specification, Resolution result, Run, Run record, Trace
  payload, Observation). Applied the reframing to FR-008 only; flagging this in
  case lex-lead intended a new Key Entities row that the current spec structure
  doesn't carry.

All other edits applied cleanly. No source files, `CP2-SPEC.md`, or repo
metadata touched.
