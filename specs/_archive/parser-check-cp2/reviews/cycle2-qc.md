# Cycle 2 QC Audit -- parser-check-cp2 amendment pass

Auditor: lex-qc (read-only; report persisted by the main session, as
lex-qc has no Write tool -- see crew_note in .crew-handoff.json).
Scope: the twelve-edit amendment set (E1..E12) from
reviews/cycle1-synthesis.md section 6, as applied to
specs/parser-check-cp2/spec.md and specs/parser-check/CP2-SPEC.md.

## Bottom line

**GREEN -- 0 blocking failures.** Safe to plan CP2a against.
Two non-blocking wording follow-ups and one out-of-scope drift finding,
all recorded below.

## 1. Verdict table

| #   | Verdict      | Evidence |
|-----|--------------|----------|
| E1  | PASS         | spec.md:540-543 -- path corrected to `src/flextoolsmcp/index/python/`, covers both `flexicon_api_v4.9.0.json` and `flexicon_lcm_bridge_v4.9.0.json` |
| E2  | PASS         | spec.md:381-387 (FR-043 reset-then-reload two-step) + spec.md:607-615 (D2 "Binding detail" cites `HCParser.Update()`'s conditional, `ParserWorker.ReloadGrammarAndLexicon()`, and states the silent-stale-serve consequence) |
| E3  | PASS         | spec.md:366-376 (FR-041), 562-588 (D1), 461-464 (SC-016), 478-485 (Assumptions) -- "different and overlapping", both directions named, `parser_probe.py` prohibition intact |
| E4  | PASS         | spec.md:242-245 (FR-008 wrapper-gap framing); Key Entities list (spec.md:396-417) verified to contain no allomorph-owner row, so the FR-008-only landing is correct, not PARTIAL |
| E5  | PASS         | spec.md:248-254 |
| E6  | PASS         | spec.md:193-197 |
| E7  | PASS, caveat | spec.md:348-355 and CP2-SPEC.md:373 agree character-for-character on names, order and enums. See section 2. |
| E8  | PASS         | spec.md:329-334 (FR-033), 339-344 (FR-036) |
| E9  | PASS         | spec.md:229-234 |
| E10 | PASS         | spec.md:361-362 (FR-040 cross-ref) + 678-694 (D5) |
| E11 | PASS         | spec.md:452-454 (SC-013 "every bundled flexicon index artifact") |
| E12 | PASS, caveat | spec.md:641-676 (D4: constraint, FR-043 justification, three-way split, A1-A3 required / A4 deferred), 255-260 (FR-011), 698-702 (Risks/Schedule). See section 2. |

## 2. Blocking failures

None.

Two caveats carried at PASS, both wording-precision rather than factual
error:

- **E7 field order.** The two amended documents agree with each other,
  which was E7's stated acceptance test -- hence PASS. Residual: both
  diverge in field ORDER from the parent SPEC.md:1987
  (`morph, position, resolved_to, candidates, hint`). FR-037's own claim
  that it matches "the parent specification's contract" therefore
  overclaims. Recommend either reordering spec.md/CP2-SPEC.md to the
  parent's order (SPEC.md is the D-03 authority), or softening FR-037's
  phrase to fields-and-values only.
- **E12 / FR-011.** FR-011's phrase "This release is the exit gate of the
  predecessor phase" re-conflates the tag with the evidence gate that D4
  establishes as primary. D4's own text is unambiguous -- the evidence
  gate precedes any CP2b start regardless of when the tag lands -- so
  this is a wording risk, not a factual reversal.

## 3. Drift-grep survivors

Outside the twelve-edit scope (only CP2-SPEC.md section 7 was in scope),
but live cross-document contradictions on facts this pass corrected:

- `specs/parser-check/CP2-SPEC.md:56` and `:189` -- still read
  `index/python/flexicon_api_v4.9.0.json`, missing the `src/` prefix.
  That is the exact string E1 retired in spec.md.
- `specs/parser-check/CP2-SPEC.md:93` -- facade table still maps
  `Reload() | Update()`, the exact fact D2/E2 corrected in spec.md.

No surviving "larger check" phrasing and no surviving four-field
`parse_morph_unresolved` listing in either target spec.

## 4. Collateral changes

New Decision block **D5** appeared alongside the plan-named D4. Verified
legitimate: it is E10's required recorded grammar-lint deferral, which
FR-040 cross-references explicitly, and it is written in the same idiom
as D1-D4. Not unrequested scope.

No other unrequested edits found in User Scenarios, Edge Cases,
Requirements or Success Criteria.

## 5. Exclusions honoured

`.spec-context.json` was not opened (a parallel agent owned it this
cycle). Source files, CLAUDE.md, TOOL-CONTRACT.md and response_models.py
were not audited; the repo-wide error-code count reconciliation is CP2b
work and deliberately out of scope here.
