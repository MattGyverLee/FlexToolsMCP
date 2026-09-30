# Cycle 9 -- Programmer T008: health parser-block tests

New file: `tests/test_parser_health_block.py` (37 tests, no `src/` edits).

## Marking convention
Grepped the suite for xfail/skip-ahead-of-implementation precedent; found
none (only `pytest.mark.skipif` gates for platform/FieldWorks availability).
Wrote **plain failing tests**, matching that absence of precedent. Each
test patches lazily via a local `import server.handlers.diagnostic_health
as dh` inside a shared `_run_health()` helper (mirrors
`TestHandleFlexToolsHealth._run`'s existing local-import style), so a
missing `dh.ParserDetector` fails each test individually with a clear
`AttributeError` rather than one whole-file collection error.

## Coverage
- Exactly two states (`ready`/`unavailable`) across 7 read/write/sandbox
  combinations, plus a literal `"degraded" not in json.dumps(...)` check.
- One dead spine (sandbox, read, or write) does not blank the other two.
- `read: ready`/`write: unavailable` on `ParseFiler.ProcessParse` alone,
  cross-checked against the T002 fixtures' member-set diff.
- `reason` key-set shape: base 5 keys; write's extra `agent_probe`; write's
  extra `agent_guid`/`active_engine` only when agent is `absent`.
- `agent_probe: "skipped"` never blocks a healthy write, and is always
  visible in `write.reason` (never omitted, never coerced to `true`/
  `"present"`) even when `write` is `"ready"`.
- `active_engine` parametrized over `None`/`"XAmple"`/`"HC"` never changes
  any status; null-by-default at CP1 (T032's D-note).
- `next_step`: `"flextools_try_word"` absent from the full response for
  three degraded scenarios (read down, write down w/ read ready, agent
  missing); `"flextools_parse_sandbox"` absent when either sandbox
  component is missing; literal CP1 replacement string present for the
  write/read row; every recursively-found `"tool"` value is `null` across
  4 degraded combinations (via a placement-agnostic `_find_all()` walker,
  since the contract doesn't pin where `next_step` nests).
- `sandbox.components`: array of 2, closed enum `{"hc",
  "GenerateHCConfig.exe"}`, exact per-entry key set.
- Full `parser`/`detected` key-set shape; `detected_version` never gates
  status.
- Named SPEC 16 integration test, gated
  `skipif(not win32 or no FieldWorks or hc IS installed)` — ran (not
  skipped) on this dev box (Windows + FieldWorks + no hc), currently RED
  via `KeyError: 'parser'`.

## Contract ambiguity (documented in the test file's module docstring)
`_build_parser_block()`'s exact composition seam (how it obtains a
`ParserDetector`) isn't pinned by the contract/data-model docs. Assumed
`diagnostic_health.py` does `from ..parser_probe import ParserDetector` and
constructs it with no required args, eagerly exposing `read_probe`,
`write_probe`, `sandbox_probe`, `agent_probe`, `active_engine`, `versions`
as attributes — mirrors the existing precedent of patching
`dh.get_index_dir`/`dh.detect_installed_library_version` as names already
imported into `diagnostic_health`'s namespace. If T012 instead calls a
bare function, only `_patch_detector()` needs a rename; shape assertions
are independent of this choice. Similarly, `next_step` placement in the
JSON tree isn't pinned, so those assertions search recursively rather than
asserting a fixed path.

## Results
- `pytest tests/test_parser_health_block.py -q`: **37 failed**, all at
  `AttributeError: ... has no attribute 'ParserDetector'` or (integration
  test) `KeyError: 'parser'` — expected RED, T012/T013 not yet landed.
- `ruff check tests/test_parser_health_block.py`: all checks passed.
- `pytest tests/ -q`: **37 failed, 1437 passed, 8 skipped, 36 subtests
  passed** — exact cycle-8 baseline (1437/8/36) plus this file's 37 new
  RED tests, zero regressions elsewhere.
