# Archivist ledger -- CP1 carry-overs for parser-check CP2

**Cycle:** 1 | **Scope:** FR-037..FR-040 evidence, no decisions made.

## 1. FR-038 -- dangling flextools_try_word guidance (exhaustive)

All CP1 guidance strings that had to point at nothing, with exact locations:

1. `src/flextoolsmcp/server/handlers/diagnostic_health.py:298-301` -- constant
   `_WRITE_UNAVAILABLE_READ_READY_ACTION`, text "filing is unavailable on this
   install; read-only parser diagnosis is unaffected." Replaces the contract's
   original wording ("use read-only Try A Word; filing unavailable"), which
   named the tool in prose. Emitted at line ~373 (`elif read["status"] ==
   "ready":` branch) with `tool: None`.
2. `diagnostic_health.py:352-361` -- `parser_agent_missing` rung, emitted
   with `tool: None`.
3. `diagnostic_health.py:303-317` and `:334-336` -- both docstrings state in
   prose "the two rows that name flextools_try_word degrade to tool: None",
   a maintainer signpost, not a caller-visible string.
4. `specs/parser-check/contracts/flextools_health-parser-block.md`, table
   "next_step per unhealthy state" (the two rows above) plus its "CP1
   caveat"/"CP1 degradation, as shipped (T013)" prose -- the contract-level
   source of both degraded rows.
5. `tests/test_parser_health_block.py` (T008) -- asserts `next_step` "never
   names flextools_try_word, which does not exist until CP2"; must invert to
   a positive assertion once T013's code is un-degraded.

**Work list for CP2:** restore `tool="flextools_try_word"` on both rows
(and row 1's original/updated action text), update the two docstrings and
the contract's caveat prose to read as historical, flip T008's assertion.

## 2. FR-039 -- four deferred test groups

All four are enumerated together in `specs/parser-check/SPEC.md:2063-2148`
(section 16) and named as excluded in `specs/parser-check/tasks.md:204` (T028).

1. **No-UI-code guarantee (HCParser_DoesNotLoadXCore).** Deferred at SPEC.md
   `2138-2141` ("Standing guarantees" group, bullet 1 -- "isolated process;
   after a real Update() + ParseWord(), assert no XCore /
   System.Windows.Forms assembly is loaded"); excluded per tasks.md:204 ("not
   HCParser_DoesNotLoadXCore ... both CP2+"). Deferred because it requires a
   real Update()+ParseWord() call -- T026 forbids constructing HCParser at CP1.
2. **No-oracle case.** SPEC.md `2141` ("A never-parsed project reports the
   oracle as absent, not as all-unreviewed"); excluded per tasks.md:204 ("the
   oracle-absent bullet, both CP2+"). Deferred because it depends on
   project.Parser/the oracle machinery from S9's flexicon facade.
3. **Conditional-proposal case.** SPEC.md `2119-2121` (G4/grammar health
   group -- "A try_word that misses the fast-path window emits a next_step
   proposing the static scan; one that answers inline does not -- the
   proposal is conditional (9.5.5)"); excluded per tasks.md:204 ("not the
   conditional-proposal bullet, which defers to CP2"). Deferred because it
   names try_word, CP2's own tool.
4. **Script-library facade group.** SPEC.md `2063-2068` ("flexicon facade
   (S9, 5.4)" group, both bullets -- lazy-import succeeds on no-ParserCore
   machines; the capability probe runs on flexicon's own side); excluded per
   tasks.md:204 ("flexicon facade ... out of CP1 scope"). Deferred because it
   tests the not-yet-released pyflexicon surface (CP2's FR-011 gate).

## 3. FR-040 -- three grammar lints, evidence only (no decision)

Named hc-undeclared-segment, hc-duplicate-feature-bundle,
hc-partial-morpheme (PanGloss-ported). Deferral recorded at:
`specs/parser-check/research.md:288-295` (decision D10), probe task
`tasks.md:126` (T031).

**D10's finding:** SIL.Machine.Morphology.HermitCrab.GrammarHealthChecker
does **not exist** in the installed HermitCrab assembly (v3.8.2.0,
`research.md:290-311`) -- a full, successfully-resolved 195-type scan found
no type named GrammarHealthChecker and none containing Grammar, Checker or
Health anywhere in the assembly (`research.md:319-324`). Stronger than
"present but not public": absent outright.

**Cost evidence (not a recommendation):**
- *Fold in at CP2*: since the type is absent on the probed install, "fold in"
  means writing the three lints' logic independently against LCM/HermitCrab
  data -- net-new scan code with its own correctness risk, not a free
  wrapper. No task/research entry sizes that effort.
- *Defer again*: `flextools_grammar_health` ships without these three
  PanGloss-parity checks; SPEC.md 9.5.6 already adopts PanGloss vocabulary
  for the checks that do ship, so deferring leaves a named gap, not a silent
  one.
- D10's probe is HermitCrab-version-specific (3.8.2.0 here); re-probing at
  CP2 planning time, not reusing D10's cached verdict, is part of either
  path's cost.

## 4. FR-037 -- error-code count

Current documented count is **22** in both places, consistent with CP2-SPEC's
"raised from 22":
- `docs/TOOL-CONTRACT.md:69` -- "one of the 22 codes below".
- `specs/parser-check/contracts/error-codes.md:3` -- "Four of SPEC 14's
  fourteen codes land at CP1" (18 + 4 = 22, consistent).
- `response_models.py:10` (docstring), `:423` ("...all 22 per-code detail
  models"), `:491` (validate_detail() docstring -- "22 known codes").
- CHANGELOG.md `:5` -- "Tool contract" entry recording the four additive
  codes, no version bump, per T005.
- Test coverage: `tests/test_parser_error_models.py` (T006) validates each
  new model's contract example through validate_detail() and rejects
  unknown fields/enum values, but does not assert the literal count "22" --
  that number lives only in hand-maintained docstrings/tables, not in a test
  that fails on drift.
- CLAUDE.md's "18" is CP1's pre-shipped baseline; already stale relative to
  22 and not a file any of the above defer to.

## 5. Other explicit CP1 -> CP2 deferrals not covered above

- `SPEC.md:1999` -- the master CP-row table's CP2 line lists, as one row,
  everything CP2 must ship: flexicon facade, Texts.GetGenres(),
  flextools_try_word (HCParser, ParseWord, TraceWordXml, all three trace
  modes of 5.1.1 including the morph-spec -> MSA-HVO resolver), the job
  runner (5.6), flextools_parse_status, and HCParser_DoesNotLoadXCore "that
  test **is** the safety story" -- the parent spec's own restatement of
  FR-039's four groups plus FR-038's tool.
- `tasks.md:26,163-166` -- the two parser_probe.py refusal helpers
  (check_active_parser, HC-agent probe) "ship with tests; first caller
  arrives at CP2": a caller gap, not a test group -- CP2's spine-executing
  handlers must call these first (FR-015), new wiring not new logic.
- `tasks.md:127` (T029) -- CP1 corrected its own "covered by the existing
  preflight/casting validators" claim (research D1) as not achievable as
  scoped; background for whichever CP2 task extends the subprocess seam for
  flextools_try_word.

## Files consulted
specs/parser-check-cp2/spec.md; specs/parser-check/{tasks,plan,SPEC,research}.md;
specs/parser-check/contracts/{error-codes,flextools_health-parser-block}.md;
docs/TOOL-CONTRACT.md; CHANGELOG.md;
src/flextoolsmcp/server/handlers/diagnostic_health.py;
src/flextoolsmcp/server/response_models.py
