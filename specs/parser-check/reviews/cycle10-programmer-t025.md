# T025 report — HC-agent probe (`probe_hc_agent`)

**Landed in** `src/flextoolsmcp/server/parser_probe.py`.

## AgentProbeState vs AgentProbeResult

T023's tests introspect `pp.AgentProbeState` via `typing.get_args` / `__members__`,
which conflicted with T011's existing dataclass of the same name. Resolved by
splitting the name: `AgentProbeState = Literal["present", "absent", "skipped"]`
is now the closed vocabulary itself (matching `response_models.py`'s own
`Literal["bootstrap_absent", "lookup_failed"]` convention), while the former
dataclass is renamed `AgentProbeResult` and gains `agent_name`, `probe_source`,
`hint` fields. `ParserDetector.__init__` and its docstring were updated to the
new class name; its behavior (`AgentProbeResult(state=AGENT_STATE_SKIPPED)`,
CP1-unconditional) is unchanged. Grepped `handlers/diagnostic_health.py` and
`tests/test_parser_health_block.py` first — neither imports `AgentProbeState`
by name (the health-block test uses its own `FakeAgentProbe`), so the rename
is safe.

## KeyNotFoundException handling and probe_source

`probe_hc_agent(project, active_engine)` reads exactly
`project.LangProject.DefaultParserAgent`. It catches broadly (`except
Exception as exc`) and checks `type(exc).__name__ == "KeyNotFoundException"`
by name rather than importing the real CLR type — importing `System...
KeyNotFoundException` would require a loadable CLR even on the no-exception
(`present`) path, which `TestAgentPresentSanity` exercises without a CLR
gate. Anything not named `KeyNotFoundException` re-raises unchanged. Within
the matched branch, `probe_source` is `bootstrap_absent` when the exception's
own message contains `HC_AGENT_GUID` (the documented, ordinary cause per
SPEC 12.7/error-codes.md), else `lookup_failed` as the conservative fallback.

## Independence from probe_parser_core

`probe_hc_agent` calls nothing but `project.LangProject.DefaultParserAgent`
— no reference to `probe_parser_core` anywhere in its body. The spy test
(`TestReadSpineUnaffectedByMissingAgent::test_probe_hc_agent_never_invokes_probe_parser_core`)
passes.

## skipped never a pass

`AgentProbeResult` has no `.ok` field (confirmed by
`test_skipped_result_carries_no_ok_field`). `project=None` short-circuits to
`state=AGENT_STATE_SKIPPED` before touching `project`; a skipped result's
`agent_guid`/`active_engine`/`probe_source`/`hint` are all `None`, so building
a `parser_agent_missing` payload from it fails `validate_detail()` validation
(confirmed by `test_skipped_result_does_not_validate_as_parser_agent_missing`).

## Handler wiring

Not wired into any handler. `ParserDetector` still unconditionally reports
`agent_probe=AgentProbeResult(state=AGENT_STATE_SKIPPED)` at CP1 (D2);
`probe_hc_agent` is defined but has no caller in this module or elsewhere.

## Verify

- `tests/test_parser_agent_probe.py`: before 17 failing (module didn't
  satisfy the tests) → after **16 passed, 1 skipped** (17 collected; the
  skip is `test_case_sensitive_when_backed_by_an_enum`, which self-skips by
  design since `AgentProbeState` is a `Literal`, not an `Enum` — the test's
  own fallback path).
- `tests/test_parser_probe.py` + `tests/test_parser_engine_gate.py` +
  `tests/test_mcp_tools.py`: **65 passed** (15/15, 20/20, 30/30 — all green,
  no regressions).
- `ruff check src/flextoolsmcp/server/parser_probe.py`: clean (one `B018`
  useless-expression finding fixed by assigning the property read to `_`).
- Full suite `pytest tests/ -q`: **1600 passed, 9 skipped, 19 failed** — all
  19 failures are in `test_grammar_health.py`, `test_grammar_scan_checks.py`,
  and `test_parser_health_block.py`, matching the task's declared "expected
  RED that is NOT yours" (pending T013/T019/T034/T035/T020); none reference
  `AgentProbeState`, `AgentProbeResult`, or `probe_hc_agent`.
