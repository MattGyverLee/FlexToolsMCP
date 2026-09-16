# Cycle 7 -- T006 report (programmer: test)

## Precondition check (T003 output)

Read `response_models.py` before writing anything. All four models
(`ParserEngineMismatchDetail`, `ParserCoreMissingDetail`,
`ParserAgentMissingDetail`, `ParserToolMissingDetail`) are present in
`AnyDetail` (lines 445-448). Field names and enum values match
`contracts/error-codes.md` verbatim: `signal` (absent|foreign_install|
incompatible_surface|load_failed), `component` ("hc"|"GenerateHCConfig.exe"),
`probe_source` (bootstrap_absent|lookup_failed), `agent_name` (Literal
"HermitCrab"). No blocker found -- proceeded to T006.

## New file

`tests/test_parser_error_models.py` (21 tests, 4 classes, one per model).

## What each test guards

- **Contract-example round-trip** (4 tests, one per model): builds the
  model's field-table example from `contracts/error-codes.md` and asserts
  `validate_detail(...)` returns an instance of the *specific* model class
  (not just "doesn't raise") -- this is the assertion that would fail if a
  model were dropped from `AnyDetail`.
- **Unknown field rejected** (4 tests): adds `unexpected_field` to each
  example and asserts `validate_detail(...)` raises `pydantic.ValidationError`
  (`extra="forbid"` enforced end-to-end through the discriminated union, not
  just the bare class).
- **Enum coverage**: `signal` (4 values: 1 in example + 3 parametrized accept
  cases), `probe_source` (2 values), `component` (2 values), `agent_name`
  (single literal) -- each accept-case also confirms `validate_detail`
  returns the right class.
- **Enum rejects value outside set**: one test per enum (`signal`,
  `probe_source`, `agent_name`, `component`).
- **Enum rejects case variant**: one test per enum -- `"ABSENT"` vs
  `"absent"`, `"Bootstrap_Absent"` vs `"bootstrap_absent"`, `"hermitcrab"` vs
  `"HermitCrab"`, `"HC"` vs `"hc"` -- confirming these are case-sensitive
  contract values, not just any-casing enums.

All assertions go through `validate_detail()`, never the bare model class
alone, per the task's load-bearing requirement.

## Results

- `python -m pytest tests/test_parser_error_models.py -q` -- **21 passed**.
- `python -m pytest tests/ -q` -- **1419 passed, 8 skipped, 23 warnings,
  36 subtests passed** (51.04s). No pre-existing failures encountered; the
  only warnings are pre-existing `ast.Str` deprecation warnings from
  `test_issue134_pyi_stub_return_types.py`, unrelated to this change.

No blockers. T006 complete as scoped; no other files touched.
