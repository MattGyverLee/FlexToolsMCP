# Cycle 8 - Programmer: required-ness coverage for parser detail models

## Tests added (18, additive only, existing 21 untouched)

Per model, one parametrized "omit required field -> ValidationError" test
(asserted through `validate_detail()`), plus for `parser_core_missing` a
second parametrized "omit optional field -> validates, field is None" test.

## Required/optional split derived from `response_models.py` (no default = required)

- **ParserEngineMismatchDetail**: `configured_engine`, `supported_engines`,
  `hint` all required. No optional fields (3 new tests).
- **ParserCoreMissingDetail**: required = `signal`, `expected_path`,
  `missing_members`, `install_hint` (note: `missing_members: List[str]` has
  no `default_factory`, unlike sibling models -- genuinely required despite
  the contract example passing `[]`). Optional = `detected_version`,
  `lcmodel_install_path`, `load_error` (4 + 3 = 7 new tests).
- **ParserAgentMissingDetail**: `agent_guid`, `agent_name`, `active_engine`,
  `probe_source`, `hint` all required. No optional fields (5 new tests).
- **ParserToolMissingDetail**: `component`, `expected_path`, `install_hint`
  all required. No optional fields (3 new tests).

## Cross-check against `specs/parser-check/contracts/error-codes.md`

No divergence. The contract's field tables mark exactly
`detected_version`, `lcmodel_install_path`, `load_error` as "or null" and
every other field as a bare type -- matching the model's Optional/required
split field-for-field, including `missing_members` (contract: `list[str]`,
no "or null"; model: required, no default). No blocker.

## Verification

1. `python -m pytest tests/test_parser_error_models.py -q` -- 39 passed
   (21 original + 18 new).
2. `python -m pytest tests/ -q` -- 1437 passed, 8 skipped, 36 subtests
   passed (cycle 7 baseline: 1419 passed / 8 skipped; delta of +18 matches
   tests added, no unrelated regressions).
3. `python -m ruff check tests/test_parser_error_models.py` -- All checks
   passed.

## Blocker

None.
