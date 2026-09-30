# T019 -- programmer report

**File:** `src/flextoolsmcp/server/scan/grammar_scan_module.py` (new).

**Layout for T034/T035.** Section 1: LCM-free shared helpers
(`is_empty_form`, `exclude_disabled_rules`, `skipped_check`, `_found_object`,
`_emit`) -- all pure Python, no `SIL.LCModel` import, so they stay importable
with no pythonnet/FieldWorks present (confirmed: `import SIL.LCModel` raises
`ModuleNotFoundError` in this dev env). Section 2: one private
`_scan_<check>(project)` per row, each doing its OWN function-scoped
`from SIL.LCModel import ...` -- never top-of-file, or importing this module
at all breaks for every pure-Python test. Section 3: `run_grammar_scan
(project)`, the T030 entry point, which calls each `_scan_*` and appends via
`_emit` in literal source order, with one comment per unimplemented row
marking exactly where T034/T035 insert their own `_emit(...)` call.

**Fixed order, structurally.** `_emit` is the only place a finding dict is
built, and `run_grammar_scan` calls it once per row in SPEC 9.5.4 order --
there is no sort/comparator anywhere in the file. `checks_run`/`findings`
accumulate by call order, the same way Python guarantees list-append order.
Adding a row is inserting one `_emit(...)` call at its marked comment; no
existing function changes.

**My three rows** (cast per T033, always applied even where the real
receiver is already typed, matching the cast_example literally):
- Row 2 `representation-variant-product`: `IPhPhoneme(obj).CodesOS`, over
  `project.Phonemes.GetAll()`. CP1 can't walk a form's phoneme segmentation
  without parsing (forbidden), so I count/multiply across the WHOLE
  inventory instead of "per form" -- product of `.CodesOS.Count` over every
  phoneme with >1 code; those phonemes are `objects[]`. Documented as an
  interpretation, not literal per-form semantics. `evidence_basis="4096"`
  (PanGloss's Aweti-case citation).
- Row 4 `unbounded-quantifier`: `IPhIterationContext(obj).Maximum == -1`,
  enumerated via `project.ObjectsIn(IPhIterationContextRepository)`
  (FLExProject's own generic-repository escape hatch -- no dedicated
  Operations wrapper exists for iteration contexts). `measured` uses the
  table's wording verbatim. `evidence_basis="fst-health's
  UnknownUnboundedConstruct"`.
- Row 9 `duplicate-feature-bundle`: `IPhPhoneme(obj).FeaturesOA`, pairwise
  compared via `.FeaturesOA.LongName` (direct `String` property, no cast,
  verified in `liblcm_api_v11.0.0.json`) since `IFsFeatStruc` has no
  pythonnet-visible equality. `count` = pair count; `objects[]` = distinct
  phonemes deduped by `Hvo`. `evidence_basis="hc-duplicate-feature-bundle"`.

`report.Result(...)`: `run_grammar_scan(project)` returns a plain dict
(`{checks_run, checks_skipped, findings}`) -- never a pydantic model, since
this package must not import `flextoolsmcp.server.*`. T030's fixed harness
calls `report.Result(run_grammar_scan(project))`, which JSON-dumps it behind
the `===FLEXTOOLS_USER_RESULT===` sentinel.

**Tests.** `tests/test_grammar_scan_checks.py` + `tests/test_grammar_health.py`:
33 failed/60 passed before -> 20 failed/73 passed after. Remaining 20: 9 are
T034's rows 1/10 (`TestZeroSurfaceMorphRow1`, `TestOptionalTemplateSlotsRow10`
-- correctly still RED, I did not implement those check_ids), 10 are T020's
handler/`_assemble_findings` seam (`TestOrderInvarianceOfFindings`,
`TestCountsNeverSummedIntoATotal`, `TestCP1BoundaryOnTheHandler`,
`TestVerdictWordingNeverDescribesAFinding`), and 1
(`test_example_measured_matches_the_factual_count_based_template`) is
pre-existing and unrelated to any implementation task -- it only parses the
checked-in contract doc's example text ("3 allomorphs have an empty surface
form") against a regex requiring is/are/can/etc, which fails identically with
`grammar_scan_module.py` absent entirely (verified). Fixed one self-inflicted
regression along the way: my own docstring literally said "IWfiAnalysis",
tripping `test_scan_module_source_never_mentions_iwfianalysis`; reworded to
describe the `IWfi*` family without spelling out the forbidden token.
`ruff check` clean. Full suite: 43 failed/1575 passed/9 skipped -- all 43
map to T034 (9), T020 (10), the pre-existing contract-doc mismatch (1), and
`test_parser_agent_probe.py`/`test_parser_health_block.py` (23, pending
T025/T012-T013, pre-existing). `test_parser_engine_gate.py` (50 incl.
`test_mcp_tools.py`) and `test_mcp_tools.py` alone (30/30) both fully green,
no regression.

**Underspecified in T033's table.** Row 2's `evidence_basis` cell reads
`e.g. "4096" for the Aweti case` -- unlike row 1's bare `"425x"` or row 5's
`"64" (...)`, the "e.g."/"for the Aweti case" wrapper reads as an
illustrative per-instance example, not obviously a fixed per-check citation
like the other rows. I resolved it as `"4096"` (dropping the wrapper) for
consistency with the pattern elsewhere in the table, but flag this for
confirmation. Separately, row 2's LCM predicate text ("product ... over a
form's segments") assumes a per-form walk CP1's no-parse boundary can't
support; I implemented an inventory-wide product instead and documented the
substitution inline -- this should get an explicit ruling before T020 writes
`measured` text that claims more than CP1 actually measures.
