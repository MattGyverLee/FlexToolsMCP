# T023 report -- agent-probe tests

**File:** `tests/test_parser_agent_probe.py` (new, 17 tests, per-test lazy imports
matching T008's convention, not T007's single top-level import).

## Tests added

- `TestAgentProbeStateClosedEnum` (2): `AgentProbeState` exposes exactly
  `{present, absent, skipped}` (tolerant of Enum-vs-`Literal` backing via a
  helper); rejects wrong-case construction when Enum-backed.
- `TestNoKeyNotFoundExceptionEscapes` (2): the core guard -- calling
  `probe_hc_agent(project, "HC")` against a fixture whose
  `LangProject.DefaultParserAgent` property raises never lets the exception
  propagate, and the result's `.state` reads `absent`.
- `TestParserAgentMissingDetailFields` (6): `agent_name == "HermitCrab"`,
  `active_engine == "HC"`, `agent_guid` populated, `probe_source` in the
  closed set, `hint` non-empty, and the full payload round-trips through
  `validate_detail()` as `ParserAgentMissingDetail` (not just the bare
  model class, per T006's precedent).
- `TestReadSpineUnaffectedByMissingAgent` (1): spies on
  `parser_probe.probe_parser_core` and asserts `probe_hc_agent` never calls
  it -- the read spine's member probe is architecturally untouched by agent
  resolution.
- `TestSkippedNeverAPass` (5): no project open -> `skipped`; `skipped !=
  present/absent`; the returned object carries no `.ok` attribute at all
  (data-model.md's explicit "modelled separately... so skipped can never be
  flattened into ok=True"); no pass-shaped coercion; a skipped result fails
  `validate_detail()` as `parser_agent_missing` (nothing to promote).
- `TestAgentPresentSanity` (1): light positive-path completeness for the
  third enum member.

## Simulating `KeyNotFoundException`

Uses the **real** `System.Collections.Generic.KeyNotFoundException` via
`clr.AddReference("mscorlib")` (pythonnet, an existing hard dependency;
needs no FieldWorks/`.fwdata`), gated behind `pytest.importorskip("clr")` so
it skips cleanly without a CLR runtime. A plain Python stand-in class of the
same name was rejected: T025's task text commits to "catching
KeyNotFoundException by name," so a correct narrow `except
System.Collections.Generic.KeyNotFoundException:` would not catch an
unrelated Python class, risking a false RED against a correct
implementation.

## Asserting `skipped` is never flattened into a pass

Four angles: state inequality (`!= present`, `!= absent`), absence of an
`.ok` attribute entirely (mirrors `ProbeResult.ok` existing only on the
*other* probe type), no pass-shaped value coercion, and failed
`validate_detail()` round-trip when a skipped result's fields are fed into
the `parser_agent_missing` payload.

## Fixtures

No changes to `tests/fixtures/parser_check.py`. Added local-only fakes
(`_FakeLangProject`, `_FakeProject`) scoped to this file -- not genuinely
shared surface, so left out of the shared fixtures module.

## Documented, not resolved

`probe_hc_agent`'s function name and `probe_source`'s exact mapping for the
canonical scenario are not pinned by any spec doc; the module docstring
documents both as tests-first assumptions (own function name invented,
`probe_source` asserted by closed-set membership only, not a specific
value) for T025 to confirm or correct.

## Results

`tests/test_parser_agent_probe.py`: 17 failed (all clean
`AttributeError: ... has no attribute 'AgentProbeState'/'probe_hc_agent'`,
zero test-logic bugs) -- RED as designed; `parser_probe.py` already exists
in-tree (T009/T010 landed concurrently) with `ProbeResult`/
`probe_parser_core`/sandbox discovery, but explicitly defers
`AgentProbeState`/`probe_hc_agent` to T024/T025 per its own scope-note
docstring.

`python -m ruff check tests/test_parser_agent_probe.py`: clean.

Full suite delta: baseline before this file **124 failed, 1478 passed, 8
skipped, 36 subtests passed**; after, **141 failed, 1478 passed, 8 skipped,
36 subtests passed** -- exactly +17 failures (this file only), zero
regressions elsewhere. (Baseline differs from the task's stated "1437
passed" because T007/T008/T032's in-flight RED and T009/T010's landed
implementation are already present on this branch.)
