# T017 report -- GrammarHealthInput / GrammarHealthFinding / FoundObject

**File:** `src/flextoolsmcp/server/models.py` (new section appended at end,
after `FlexToolsHealthInput`; `ConfigDict` added to the pydantic import).

## Models as landed

- `GrammarHealthInput(BaseModel)`: `project_name: Optional[str] = None`,
  `checks: Optional[List[str]] = None`, `limit: int = 20`. No `ConfigDict`
  (matches every other `*Input` model in the file -- open by convention,
  only the response-shaped models here are closed).
- `FoundObject(BaseModel)`: `model_config = ConfigDict(extra="forbid")`.
  Exactly `hvo: int`, `class_name: str`, `label: str`,
  `goto_url: Optional[str] = None`.
- `GrammarHealthFinding(BaseModel)`: `model_config = ConfigDict(extra="forbid")`.
  Exactly `check_id: str`, `spec_row: Optional[int] = None`, `count: int`,
  `measured: str`, `evidence_basis: Optional[str] = None`,
  `objects: List[FoundObject] = Field(default_factory=list)`.

## Closure at both nesting levels

`extra="forbid"` on both `GrammarHealthFinding` and `FoundObject` independently
-- a bad key on the top-level finding is rejected by `GrammarHealthFinding`
itself; a bad key on an `objects[]` item is rejected by `FoundObject` during
its own construction, which pydantic runs when validating the `objects: List[FoundObject]`
field, so the outer model's construction fails too. No open dict/`Any` stands
in for `FoundObject` anywhere, closing the nesting level T014 specifically
targets (`test_nested_inside_grammar_health_finding_is_closed_too`).

## `test_grammar_health.py` counts

Before (per task brief): 23 passed / 51 failed (74 total).
After landing: **60 passed / 14 failed** (74 total, unchanged).

Converted to green: `TestGrammarHealthFindingStructuralClosure` (6),
`TestFoundObjectStructuralClosure` (6), `TestRecursiveDenylistWalkOverRealModels`
(4), plus assorted contract-example tests that only needed the allowlist
constants (already green pre-T017) -- net +37.

Still RED (14), all pending later tasks, none touching models.py:
- `TestOrderInvarianceOfFindings` (6) + `TestCountsNeverSummedIntoATotal` (1) +
  `test_assembled_findings_measured_text_has_no_verdict_words` (1): need
  `server.handlers.grammar_health._assemble_findings` -> **T020**.
- `TestCP1BoundaryOnTheScanModule` (3): need `server.scan.grammar_scan_module`
  -> **T019/T034/T035**.
- `TestCP1BoundaryOnTheHandler` (2): need `server.handlers.grammar_health`
  -> **T020**.
- `test_example_measured_matches_the_factual_count_based_template` (1):
  pre-existing, fails against the checked-in contract doc's own JSON example
  text, unrelated to models.py.

## Full-suite delta

`pytest tests/ -q`: 103 failed / 1516 passed / 8 skipped. All failing files
are the ones the task brief names as expected RED (`test_parser_health_block.py`,
`test_grammar_scan_checks.py`, `test_parser_engine_gate.py`,
`test_parser_agent_probe.py`, remainder of `test_grammar_health.py`), **plus**
one unrelated file: `test_mcp_tools.py::test_tool_count` (22 vs expected 21
tools). Verified via `git stash`/pop that this is caused by a concurrent,
uncommitted change to `tool_definitions.py` (another in-flight task already
registering `flextools_grammar_health` with `GrammarHealthInput`) sharing this
working directory -- not caused by this change; `EXPECTED_TOOL_COUNT` belongs
to whichever task lands that registration.

## data-model.md vs test_grammar_health.py

No disagreement found -- both agree on `GrammarHealthInput`'s three fields,
`GrammarHealthFinding`'s six-key allowlist, and `FoundObject`'s four-key
allowlist. `ruff check` on `models.py`: all checks passed.
